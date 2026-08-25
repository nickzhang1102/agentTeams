"""
Custom Knowledge Search Tool - 知识图谱搜索工具

将 KnowledgeRetriever 包装为 OpenHarness Tool，供 Agent 按需调用。
替代原有的"执行前全局注入"策略，Agent 根据自身任务主动搜索知识。

参见 .codestable/issues/2026-06-12-knowledge-auto-inject/analysis.md 方案 A。
"""
import logging
from pydantic import BaseModel, Field
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult

logger = logging.getLogger(__name__)


class KnowledgeSearchInput(BaseModel):
    """知识搜索输入"""
    query: str = Field(..., description="搜索查询（与任务相关的关键词或问题）")


class KnowledgeSearchTool(BaseTool):
    """知识图谱搜索工具"""

    def __init__(self, retriever=None):
        super().__init__()
        self.name = "knowledge_search"
        self.description = "Search the project knowledge graph for relevant information"
        self.input_model = KnowledgeSearchInput
        self._retriever = retriever

    def _get_retriever(self):
        """懒加载 KnowledgeRetriever"""
        if self._retriever is not None:
            return self._retriever
        try:
            from context.knowledge_retriever import KnowledgeRetriever
            self._retriever = KnowledgeRetriever()
            return self._retriever
        except Exception:
            logger.debug("KnowledgeRetriever not available")
            return None

    async def execute(
        self,
        input_data,
        context: ToolExecutionContext
    ) -> ToolResult:
        """执行知识搜索"""
        try:
            query = input_data.query if hasattr(input_data, 'query') else str(input_data)

            # 从执行上下文读取 user_id
            user_id = context.metadata.get("user_id") if context.metadata else None
            if not user_id:
                return ToolResult(
                    output="knowledge_search unavailable: user_id not provided",
                    is_error=True,
                )

            retriever = self._get_retriever()
            if retriever is None:
                return ToolResult(
                    output="knowledge_search unavailable: GraphRAGService not initialized",
                    is_error=True,
                )

            retrieve_with_evidence = getattr(retriever, "retrieve_with_evidence", None)
            if callable(retrieve_with_evidence):
                result = retrieve_with_evidence(query=query, user_id=user_id)
            else:
                # Legacy retrievers remain readable until the structured protocol is universal.
                legacy_contexts = retriever.retrieve(query=query, user_id=user_id)
                result = {
                    "contexts": legacy_contexts,
                    "evidence_items": [],
                }
            contexts = result.get("contexts", [])
            evidence_items = result.get("evidence_items", [])
            if not contexts:
                return ToolResult(
                    output="未找到相关知识片段",
                    is_error=False,
                    metadata={"result_count": 0, "evidence_items": []}
                )

            output = "\n".join(contexts)
            return ToolResult(
                output=output,
                is_error=False,
                metadata={
                    "result_count": len(contexts),
                    "evidence_items": evidence_items,
                }
            )
        except Exception as e:
            logger.error(f"KnowledgeSearchTool exception: {e}", exc_info=True)
            return ToolResult(
                output=f"knowledge_search failed: {str(e)}",
                is_error=True,
            )
