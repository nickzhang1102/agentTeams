"""Embedding 向量服务

调用 OpenAI 兼容 /v1/embeddings 端点，为 GraphRAG 语义搜索提供向量生成。
在 graphify 提取完成后自动同步节点向量到 node_embeddings 表。
"""

import hashlib
import json
import threading
import logging
import os
from pathlib import Path
from typing import Optional

from openai import OpenAI

from config import Config

logger = logging.getLogger(__name__)

# 同一用户图谱向量的并发重建互斥（上传后台线程 vs 删除文档协程）
_sync_write_lock = threading.Lock()

# 向量维度（由模型决定，首次 embed 时自动检测）
_embedding_dim: Optional[int] = None

# 模块级单例（惰性初始化）
_instance: Optional['EmbeddingService'] = None


def get_embedding_service() -> 'EmbeddingService':
    """获取 EmbeddingService 单例"""
    global _instance
    if _instance is None:
        _instance = EmbeddingService()
    return _instance


class EmbeddingService:
    """Embedding 向量生成与同步服务"""

    def __init__(self):
        base_url = Config.EMBEDDING_BASE_URL
        api_key = Config.EMBEDDING_API_KEY

        if not base_url or not api_key:
            logger.warning('EmbeddingService: EMBEDDING_BASE_URL or EMBEDDING_API_KEY not configured')
            self._client = None
            self._model = None
        else:
            self._client = OpenAI(api_key=api_key, base_url=base_url)
            self._model = Config.EMBEDDING_MODEL

    @property
    def available(self) -> bool:
        """embedding 服务是否可用"""
        return self._client is not None and self._model is not None

    def embed_text(self, text: str) -> Optional[list[float]]:
        """单条文本 embedding

        Returns:
            向量列表，失败返回 None
        """
        if not self.available:
            return None

        try:
            response = self._client.embeddings.create(
                model=self._model,
                input=text,
            )
            global _embedding_dim
            vec = response.data[0].embedding
            _embedding_dim = len(vec)
            return vec
        except Exception:
            logger.exception(f'EmbeddingService.embed_text failed for text={text[:50]}...')
            return None

    def embed_batch(self, texts: list[str], batch_size: int = 512) -> list[Optional[list[float]]]:
        """批量文本 embedding（自动分批，避免 API 限流）

        Args:
            texts: 待 embedding 的文本列表
            batch_size: 每批大小，默认 512

        Returns:
            与 texts 等长的向量列表，单条失败对应位置为 None
        """
        if not self.available or not texts:
            return [None] * len(texts)

        results: list[Optional[list[float]]] = [None] * len(texts)

        for start in range(0, len(texts), batch_size):
            end = min(start + batch_size, len(texts))
            chunk = texts[start:end]
            try:
                response = self._client.embeddings.create(
                    model=self._model,
                    input=chunk,
                )
                global _embedding_dim
                for item in response.data:
                    vec = item.embedding
                    _embedding_dim = len(vec)
                    results[start + item.index] = vec
            except Exception:
                logger.exception(
                    f'EmbeddingService.embed_batch failed for batch [{start}:{end}]'
                )

        return results

    def sync_user_embeddings(self, user_id: int) -> dict:
        """同步用户图谱节点向量到 node_embeddings 表

        读取 graph.json 所有节点 label，批量生成 embedding，UPSERT 到数据库。

        Returns:
            {'synced': int, 'failed': int, 'skipped': bool}
        """
        from db import db
        from models import NodeEmbedding

        if not self.available:
            logger.info(f'EmbeddingService: skip sync for user {user_id}, service unavailable')
            return {'synced': 0, 'failed': 0, 'skipped': True}

        # 读取用户图谱
        graph_path = Config.get_user_graph_path(user_id)
        if not graph_path or not os.path.exists(graph_path):
            logger.info(f'EmbeddingService: user {user_id} graph not found, skip sync')
            return {'synced': 0, 'failed': 0, 'skipped': True}

        try:
            data = json.loads(Path(graph_path).read_text(encoding='utf-8'))
        except Exception:
            logger.exception(f'EmbeddingService: failed to read graph for user {user_id}')
            return {'synced': 0, 'failed': 0, 'skipped': True}

        nodes = data.get('nodes', [])
        if not nodes:
            return {'synced': 0, 'failed': 0, 'skipped': True}

        # 计算 graph_version（文件内容 hash）
        graph_version = hashlib.md5(
            json.dumps(nodes, sort_keys=True).encode()
        ).hexdigest()[:16]

        # 检查是否需要重建（版本未变则跳过）
        existing = db.query(NodeEmbedding).filter(
            NodeEmbedding.user_id == user_id
        ).first()
        if existing and existing.graph_version == graph_version:
            logger.info(f'EmbeddingService: user {user_id} graph version unchanged, skip sync')
            return {'synced': 0, 'failed': 0, 'skipped': True}

        # 删除旧向量
        # 这里运行在共享的 thread-local scoped session 上（上传后台线程与删除
        # 文档协程可能并发同一用户），delete-then-insert 竞态会撞
        # uq_node_embedding_user_node。提交失败必须 rollback，否则 session
        # 进入 pending-rollback 态，同线程后续所有 DB 操作持续报错直到回收。
        # 全局锁串行化写入段，消除并发同步之间的唯一约束冲突。
        with _sync_write_lock:
            try:
                db.query(NodeEmbedding).filter(
                    NodeEmbedding.user_id == user_id
                ).delete()
                db.flush()

                # 批量生成向量
                labels = [n.get('label', '') for n in nodes]
                node_ids = [n.get('id', '') for n in nodes]

                vectors = self.embed_batch(labels)

                synced = 0
                failed = 0
                for node_id, label, vec in zip(node_ids, labels, vectors):
                    if not node_id or not label or vec is None:
                        failed += 1
                        continue
                    record = NodeEmbedding(
                        user_id=user_id,
                        node_id=node_id,
                        label=label,
                        embedding=vec,
                        graph_version=graph_version,
                    )
                    db.add(record)
                    synced += 1

                db.commit()
            except Exception:
                db.rollback()
                logger.exception(
                    f'EmbeddingService: failed to sync embeddings for user {user_id}'
                )
                return {'synced': 0, 'failed': len(nodes), 'skipped': False}

        logger.info(f'EmbeddingService: synced {synced} nodes for user {user_id}, failed {failed}')
        return {'synced': synced, 'failed': failed, 'skipped': False}
