"""知识图谱检索器，封装 GraphRAGService 调用。

对外暴露 retrieve()，返回可注入 ContextPack.shared_evidence 的知识片段列表。
GraphRAGService 不可用时静默降级，不影响 Agent 执行。
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# 知识片段字符上限（与 GraphRAGService.MAX_CONTEXT_CHARS 对齐）
MAX_CONTEXT_CHARS = 3000


class KnowledgeRetriever:
    """知识图谱检索器。

    Args:
        graph_rag_service: GraphRAGService 实例（可选，默认使用单例）。
    """

    def __init__(self, graph_rag_service=None):
        self._service = graph_rag_service

    def _get_service(self):
        """懒加载 GraphRAGService 单例。"""
        if self._service is not None:
            return self._service
        try:
            from services.graph_rag_service import GraphRAGService
            return GraphRAGService.get_instance()
        except Exception:
            logger.debug("GraphRAGService not available")
            return None

    def retrieve(
        self,
        query: str,
        user_id: int,
        top_k: int = 8,
        hop: int = 2,
    ) -> list[str]:
        """查询知识图谱，返回知识片段列表。

        Args:
            query: 用户需求文本。
            user_id: 用户 ID，指定查询哪个用户的图谱。
            top_k: 返回最相关节点数。
            hop: 图遍历跳数。

        Returns:
            有结果时返回 ["## 知识图谱\\n{格式化片段}"]；
            无结果或异常时返回空列表。
        """
        if not query or not query.strip():
            return []

        service = self._get_service()
        if service is None:
            logger.info("Knowledge retrieval skipped: GraphRAGService not available")
            return []

        try:
            result = service.search(query=query, user_id=user_id, top_k=top_k, hop=hop)
            if not result:
                return []

            # 截断超长结果
            if len(result) > MAX_CONTEXT_CHARS:
                logger.warning(
                    "Knowledge context truncated: %d > %d chars",
                    len(result), MAX_CONTEXT_CHARS,
                )
                result = result[:MAX_CONTEXT_CHARS] + "\n...(已截断)"

            return [result]

        except Exception:
            logger.warning("Knowledge retrieval failed, skipping", exc_info=True)
            return []

    def retrieve_with_evidence(
        self,
        query: str,
        user_id: int,
        top_k: int = 8,
        hop: int = 2,
    ) -> dict:
        """Return bounded context plus per-document evidence candidates."""
        if not query or not query.strip():
            return {"contexts": [], "evidence_items": []}

        service = self._get_service()
        if service is None:
            logger.info("Knowledge retrieval skipped: GraphRAGService not available")
            return {"contexts": [], "evidence_items": []}

        try:
            result = service.search_with_evidence(
                query=query, user_id=user_id, top_k=top_k, hop=hop
            )
            if not result:
                return {"contexts": [], "evidence_items": []}
            context = str(result.get("context") or "")
            if len(context) > MAX_CONTEXT_CHARS:
                context = context[:MAX_CONTEXT_CHARS] + "\n...(已截断)"
            return {
                "contexts": [context] if context else [],
                "evidence_items": list(result.get("evidence_items") or []),
            }
        except Exception:
            logger.warning("Knowledge retrieval with evidence failed, skipping", exc_info=True)
            return {"contexts": [], "evidence_items": []}
