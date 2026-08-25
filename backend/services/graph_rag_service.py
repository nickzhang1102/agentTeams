"""GraphRAG 服务 — 基于知识图谱的检索增强生成

从 graph.json 加载实体关系图，用户提问时：
1. 向量召回相关节点（pgvector cosine），fallback 到子串匹配
2. 图遍历收集关联实体（2 跳）
3. 读取源文档片段
4. 格式化为结构化上下文注入 LLM prompt
"""

import json
import hashlib
import logging
import math
import os
import time
from collections import defaultdict
from pathlib import Path
from typing import Optional

from config import Config

logger = logging.getLogger(__name__)

# 常量
MAX_CONTEXT_CHARS = 3000      # 注入上下文字符上限
SNIPPET_MAX_CHARS = 200       # 每段源文档最大字符数
EVIDENCE_PASSAGE_MAX_CHARS = 4000  # 可核验证据段落上限
EVIDENCE_EXCERPT_MAX_CHARS = 500   # evidence_map 列表摘要上限
SCORE_THRESHOLD = 1.0         # 最低相关性分数
VECTOR_SCORE_THRESHOLD = float(os.getenv('GRAPH_RAG_VECTOR_MIN_SIMILARITY', '0.35'))
DEFAULT_TOP_K = 8             # 返回最相关节点数
DEFAULT_HOP = 2               # 图遍历跳数
GRAPH_CACHE_TTL = 300         # 图谱缓存 TTL（秒）
GRAPH_CACHE_MAX_SIZE = 128    # 缓存条目上限，LRU 淘汰最旧条目


class GraphRAGService:
    """知识图谱检索增强服务（按用户动态加载，带 TTL 缓存）"""

    _instance: Optional['GraphRAGService'] = None

    def __init__(self):
        self._graph_cache: dict[int, tuple[float, dict]] = {}  # user_id -> (expire_ts, indices)

    def _evict_expired_cache(self) -> None:
        """淘汰过期缓存条目，写入前调用防止无限增长"""
        now = time.monotonic()
        expired = [uid for uid, (ts, _) in self._graph_cache.items() if ts <= now]
        for uid in expired:
            del self._graph_cache[uid]
        # 若仍超限，淘汰最早过期的条目（while 防止突发写入导致驱逐不充分）
        while len(self._graph_cache) >= GRAPH_CACHE_MAX_SIZE:
            oldest = min(self._graph_cache, key=lambda k: self._graph_cache[k][0])
            del self._graph_cache[oldest]

    @classmethod
    def get_instance(cls) -> 'GraphRAGService':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # === 加载 ===

    def _load_user_graph(self, user_id: int) -> Optional[dict]:
        """加载用户图谱（带 TTL 缓存），返回临时索引或 None

        Returns:
            {"nodes": dict, "adjacency": dict, "edges": dict, "source_index": dict} 或 None
        """
        # 检查缓存
        if user_id in self._graph_cache:
            expire_ts, cached = self._graph_cache[user_id]
            if time.monotonic() < expire_ts:
                return cached
            del self._graph_cache[user_id]

        graph_path = Config.get_user_graph_path(user_id)
        if not graph_path or not os.path.exists(graph_path):
            logger.info(f'GraphRAG: user {user_id} graph not found, skipping')
            return None

        try:
            data = json.loads(Path(graph_path).read_text(encoding='utf-8'))
            indices = self._build_indices(data)
            # 写入缓存（先淘汰过期条目，防止无限增长）
            self._evict_expired_cache()
            self._graph_cache[user_id] = (time.monotonic() + GRAPH_CACHE_TTL, indices)
            logger.info(f'GraphRAG: user {user_id} graph loaded, {len(indices["nodes"])} nodes, {len(indices["edges"])} edges')
            return indices
        except Exception:
            logger.exception(f'GraphRAG: failed to load user {user_id} graph')
            return None

    def clear_user_cache(self, user_id: int) -> None:
        """清除指定用户的图谱缓存（图谱重建后调用）"""
        self._graph_cache.pop(user_id, None)

    def _build_indices(self, data: dict) -> dict:
        """构建图索引，返回临时数据结构（不写 self）

        Returns:
            {"nodes": dict, "adjacency": dict, "edges": dict, "source_index": dict}
        """
        nodes = {}
        adjacency = defaultdict(list)
        edges = {}
        source_index = defaultdict(list)

        for node in data.get('nodes', []):
            nid = node.get('id')
            if not nid:
                continue
            label = node.get('label', '')
            source_files = self._normalize_source_files(
                node.get('source_files') or node.get('source_file')
            )
            nodes[nid] = {
                'id': nid,
                'label': label,
                'community': node.get('community'),
                'source_file': source_files[0] if source_files else None,
                'source_files': source_files,
                'file_type': node.get('file_type', ''),
            }
            for source in source_files:
                source_index[source].append(nid)

        for link in data.get('links', data.get('edges', [])):
            src = link.get('source')
            tgt = link.get('target')
            if not src or not tgt:
                continue
            adjacency[src].append(tgt)
            adjacency[tgt].append(src)
            edge_key = f'{src}::{tgt}'
            edges[edge_key] = {
                'relation': link.get('relation', 'related_to'),
                'confidence': link.get('confidence', ''),
            }

        return {
            'nodes': nodes,
            'adjacency': adjacency,
            'edges': edges,
            'source_index': source_index
        }

    @staticmethod
    def _normalize_source_files(value) -> list[str]:
        """兼容旧逗号字符串并统一为去重后的来源列表。"""
        values = value if isinstance(value, (list, tuple, set)) else [value]
        result = []
        for item in values:
            if not isinstance(item, str):
                continue
            for source in item.split(','):
                source = source.strip()
                if source and source not in result:
                    result.append(source)
        return result

    # === 搜索 ===

    def search(
        self,
        query: str,
        user_id: int,
        top_k: int = DEFAULT_TOP_K,
        hop: int = DEFAULT_HOP,
    ) -> Optional[str]:
        """搜索相关图谱上下文，返回格式化字符串或 None

        优先使用 pgvector 向量召回，fallback 到子串匹配。

        Args:
            query: 查询关键词
            user_id: 用户 ID，加载该用户的图谱文件
            top_k: 返回最相关节点数
            hop: 图遍历跳数

        Returns:
            格式化上下文字符串或 None（无图谱/无匹配）
        """
        result = self._search(query, user_id, top_k, hop, include_evidence=False)
        return result if isinstance(result, str) else None

    def search_with_evidence(
        self,
        query: str,
        user_id: int,
        top_k: int = DEFAULT_TOP_K,
        hop: int = DEFAULT_HOP,
    ) -> Optional[dict]:
        """搜索知识图谱，并返回兼容上下文与逐文档 evidence candidates。"""
        result = self._search(query, user_id, top_k, hop, include_evidence=True)
        return result if isinstance(result, dict) else None

    def _search(
        self,
        query: str,
        user_id: int,
        top_k: int,
        hop: int,
        *,
        include_evidence: bool,
    ) -> Optional[str | dict]:
        # 加载用户图谱
        indices = self._load_user_graph(user_id)
        if not indices:
            return None

        nodes = indices['nodes']
        adjacency = indices['adjacency']

        if not nodes:
            return None

        query_clean = query.strip()
        if not query_clean:
            return None

        # 节点评分：优先向量召回，fallback 子串匹配
        top_nodes = self._vector_recall(query_clean, user_id, nodes, top_k)
        vector_hit = bool(top_nodes)

        if not top_nodes:
            top_nodes = self._substring_recall(query_clean, nodes, top_k)

        if not top_nodes:
            return None

        logger.info(
            f'GraphRAG: user={user_id} query="{query_clean[:30]}" '
            f'vector_hit={vector_hit} seeds={len(top_nodes)}'
        )

        # 图遍历
        visited = set()
        related_groups: dict[int, list[dict]] = defaultdict(list)
        source_files = set()
        source_labels: dict[str, set[str]] = defaultdict(set)

        def collect_sources(node: dict) -> None:
            for source_file in node.get('source_files', []):
                source_files.add(source_file)
                if node.get('label'):
                    source_labels[source_file].add(node['label'])

        for seed_nid, _ in top_nodes:
            if seed_nid in visited:
                continue
            seed = nodes[seed_nid]
            community = seed.get('community', -1)
            related_groups[community].append(seed)
            collect_sources(seed)
            visited.add(seed_nid)

            frontier = [seed_nid]
            for _ in range(hop):
                next_frontier = []
                for nid in frontier:
                    for neighbor_id in adjacency.get(nid, []):
                        if neighbor_id in visited:
                            continue
                        visited.add(neighbor_id)
                        neighbor = nodes.get(neighbor_id)
                        if neighbor:
                            related_groups[community].append(neighbor)
                            collect_sources(neighbor)
                            next_frontier.append(neighbor_id)
                frontier = next_frontier

        # 读取源文档片段（按 user_id 隔离，防止跨用户读取同名文件）
        passages = self._read_snippets(
            source_files,
            user_id,
            query=query_clean,
            source_labels=source_labels,
            max_chars=EVIDENCE_PASSAGE_MAX_CHARS,
        )
        snippets = {
            source: self._clip_window(text, SNIPPET_MAX_CHARS)
            for source, text in passages.items()
        }

        context = self._format_context(related_groups, snippets)
        if not include_evidence:
            return context

        evidence_items = []
        for rank, (source_file, passage) in enumerate(passages.items(), 1):
            evidence_items.append({
                "source_type": "knowledge",
                "source_id": source_file,
                "title": Path(source_file).name or source_file,
                "url": None,
                "provider": "graph_rag",
                "rank": rank,
                "relevance_score": None,
                "excerpt": self._clip_window(passage, EVIDENCE_EXCERPT_MAX_CHARS),
                "passage": passage,
                "locator": {"source_file": source_file},
                "source_version": hashlib.sha256(passage.encode("utf-8")).hexdigest(),
                "completeness": "passage",
            })
        return {"context": context, "evidence_items": evidence_items}

    def _vector_recall(
        self, query: str, user_id: int, nodes: dict, top_k: int
    ) -> list[tuple[str, float]]:
        """向量召回种子节点

        Returns:
            [(node_id, score), ...] 或空列表（fallback 信号）
        """
        try:
            from services.embedding_service import get_embedding_service
            from models import NodeEmbedding
            from db import db

            # pgvector 未安装时跳过向量召回（NodeEmbedding.embedding 降级为 Text）
            try:
                from pgvector.sqlalchemy import Vector  # noqa: F401
            except ImportError:
                logger.debug('GraphRAG: pgvector not installed, skip vector recall')
                return []

            service = get_embedding_service()
            if not service.available:
                return []

            query_vec = service.embed_text(query)
            if query_vec is None:
                return []

            # pgvector cosine distance 排序（距离越小越相似），同时返回真实距离。
            distance_expr = NodeEmbedding.embedding.cosine_distance(query_vec).label('distance')
            results = db.query(NodeEmbedding.node_id, distance_expr).filter(
                NodeEmbedding.user_id == user_id
            ).order_by(
                distance_expr
            ).limit(top_k).all()

            if not results:
                return []

            # cosine_distance 返回 0~2，转为相似度分数（1 - distance）
            top_nodes = []
            for r in results:
                try:
                    score = 1.0 - float(r.distance)
                except (TypeError, ValueError):
                    continue
                if (
                    r.node_id in nodes
                    and math.isfinite(score)
                    and score >= VECTOR_SCORE_THRESHOLD
                ):
                    top_nodes.append((r.node_id, score))
            return top_nodes

        except Exception:
            logger.debug('GraphRAG: vector recall failed, falling back to substring')
            return []

    @staticmethod
    def _substring_recall(
        query: str, nodes: dict, top_k: int
    ) -> list[tuple[str, float]]:
        """子串匹配召回种子节点（fallback）

        Returns:
            [(node_id, score), ...]
        """
        scores: dict[str, float] = {}
        for nid, node in nodes.items():
            label = node['label']
            if not label:
                continue
            if label in query:
                scores[nid] = scores.get(nid, 0) + 3.0
            elif query in label:
                scores[nid] = scores.get(nid, 0) + 2.0
            else:
                for i in range(len(query) - 1):
                    bigram = query[i:i + 2]
                    if len(bigram) >= 2 and bigram.isalnum() and bigram in label:
                        scores[nid] = scores.get(nid, 0) + 1.0
                        break

        if not scores:
            return []

        ranked = sorted(scores.items(), key=lambda x: -x[1])
        return [(nid, s) for nid, s in ranked[:top_k] if s >= SCORE_THRESHOLD]

    # === 内部方法 ===

    def _read_snippets(
        self,
        source_files: set,
        user_id: int,
        query: str = '',
        source_labels: Optional[dict[str, set[str]]] = None,
        max_chars: int = SNIPPET_MAX_CHARS,
    ) -> dict[str, str]:
        """从 KnowledgeDocument 读取源文档片段（按 user_id 隔离）

        仅查询属于该用户且状态为 indexed 的文档，避免跨用户读取同名 source_file。
        """
        from models import KnowledgeDocument
        from db import db

        snippets: dict[str, str] = {}
        valid_files = {
            source
            for value in source_files
            for source in self._normalize_source_files(value)
        }

        if not valid_files:
            return snippets

        try:
            docs = db.query(KnowledgeDocument).filter(
                KnowledgeDocument.uploaded_by == user_id,
                KnowledgeDocument.status == 'indexed',
                KnowledgeDocument.markdown_path.isnot(None)
            ).all()

            for doc in docs:
                if not doc.markdown_path or not os.path.isdir(doc.markdown_path):
                    continue
                md_dir = Path(doc.markdown_path).resolve()
                # 优化：先检查该目录下是否有任何目标文件（避免无用遍历）
                remaining_files = [f for f in valid_files if f not in snippets]
                if not remaining_files:
                    break  # 所有目标文件已找到，提前退出
                for source_file in remaining_files:
                    if source_file in snippets:
                        continue
                    source_path = Path(source_file)
                    if source_path.is_absolute():
                        logger.warning('GraphRAG: rejected absolute source path %s', source_file)
                        continue
                    md_path = (md_dir / source_path).resolve()
                    try:
                        md_path.relative_to(md_dir)
                    except ValueError:
                        logger.warning('GraphRAG: rejected source path outside markdown root: %s', source_file)
                        continue
                    if md_path.is_file():
                        try:
                            text = md_path.read_text(encoding='utf-8').strip()
                            labels = (source_labels or {}).get(source_file, set())
                            text = self._extract_relevant_window(
                                text, query, labels, max_chars=max_chars
                            )
                            snippets[source_file] = text
                        except Exception:
                            pass
        except Exception:
            logger.exception('GraphRAG: 读取源文档失败')

        return snippets

    @staticmethod
    def _extract_relevant_window(
        text: str,
        query: str,
        labels,
        max_chars: int = SNIPPET_MAX_CHARS,
    ) -> str:
        """围绕查询或命中实体提取固定长度窗口，未命中时保留文档开头。"""
        if len(text) <= max_chars:
            return text

        terms = [term.strip() for term in [query, *(labels or [])] if term and term.strip()]
        lowered = text.lower()
        matches = []
        for term in terms:
            position = lowered.find(term.lower())
            if position >= 0:
                matches.append((len(term), position))

        if not matches:
            return text[:max_chars] + '...'

        _, position = max(matches, key=lambda item: (item[0], -item[1]))
        start = max(0, position - max_chars // 3)
        end = min(len(text), start + max_chars)
        start = max(0, end - max_chars)
        prefix = '...' if start > 0 else ''
        suffix = '...' if end < len(text) else ''
        return prefix + text[start:end] + suffix

    @staticmethod
    def _clip_window(text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + '...'

    @staticmethod
    def _format_context(
        related_groups: dict[int, list[dict]],
        snippets: dict[str, str],
    ) -> str:
        """格式化图谱上下文"""
        parts = ['## 知识图谱上下文\n']
        total_chars = len(parts[0])

        for community, nodes in related_groups.items():
            entities = list({n['label'] for n in nodes})
            if not entities:
                continue
            block = f'**相关领域 (community {community})**\n'
            block += '实体: ' + '、'.join(entities[:15]) + '\n'
            if total_chars + len(block) > MAX_CONTEXT_CHARS:
                break
            parts.append(block)
            total_chars += len(block)

        if snippets:
            snippet_section = '**相关文档片段**\n'
            for source, text in snippets.items():
                entry = f'- [{source}] {text}\n'
                if total_chars + len(snippet_section) + len(entry) > MAX_CONTEXT_CHARS:
                    break
                snippet_section += entry
            if snippet_section != '**相关文档片段**\n':
                parts.append(snippet_section)

        return '\n'.join(parts) if len(parts) > 1 else None
