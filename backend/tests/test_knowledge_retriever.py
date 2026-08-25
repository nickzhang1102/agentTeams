"""
KnowledgeRetriever 单元测试。

覆盖：有图谱/无图谱/异常/空图谱四场景。
"""
import pytest
from unittest.mock import MagicMock, patch

from context.knowledge_retriever import KnowledgeRetriever, MAX_CONTEXT_CHARS


class TestKnowledgeRetrieverRetrieve:
    """retrieve() 方法测试。"""

    def test_with_relevant_knowledge(self, mock_graph_rag):
        """有相关知识时返回非空列表。"""
        mock_graph_rag.search.return_value = "## 知识图谱上下文\n实体: 节日慰问"
        retriever = KnowledgeRetriever(graph_rag_service=mock_graph_rag)

        result = retriever.retrieve("节日慰问标准是多少", user_id=1)

        assert len(result) == 1
        assert "节日慰问" in result[0]
        mock_graph_rag.search.assert_called_once_with(
            query="节日慰问标准是多少", user_id=1, top_k=8, hop=2
        )

    def test_with_no_match(self, mock_graph_rag):
        """无相关知识时返回空列表。"""
        mock_graph_rag.search.return_value = None
        retriever = KnowledgeRetriever(graph_rag_service=mock_graph_rag)

        result = retriever.retrieve("完全无关的内容xyz", user_id=1)

        assert result == []

    def test_empty_query(self, mock_graph_rag):
        """空查询返回空列表，不调用 search。"""
        retriever = KnowledgeRetriever(graph_rag_service=mock_graph_rag)

        assert retriever.retrieve("", user_id=1) == []
        assert retriever.retrieve("   ", user_id=1) == []
        mock_graph_rag.search.assert_not_called()

    def test_graph_not_available(self):
        """GraphRAGService 不可用时返回空列表。"""
        retriever = KnowledgeRetriever(graph_rag_service=None)

        with patch.object(retriever, '_get_service', return_value=None):
            result = retriever.retrieve("任意查询", user_id=1)

        assert result == []

    def test_search_exception_returns_empty(self, mock_graph_rag):
        """search 抛异常时返回空列表，不抛出。"""
        mock_graph_rag.search.side_effect = RuntimeError("graph.json 损坏")
        retriever = KnowledgeRetriever(graph_rag_service=mock_graph_rag)

        result = retriever.retrieve("查询", user_id=1)

        assert result == []

    def test_truncates_long_result(self, mock_graph_rag):
        """超长结果截断到 MAX_CONTEXT_CHARS。"""
        long_text = "x" * (MAX_CONTEXT_CHARS + 500)
        mock_graph_rag.search.return_value = long_text
        retriever = KnowledgeRetriever(graph_rag_service=mock_graph_rag)

        result = retriever.retrieve("查询", user_id=1)

        assert len(result) == 1
        assert len(result[0]) <= MAX_CONTEXT_CHARS + 50  # 截断标记长度
        assert "已截断" in result[0]

    def test_custom_params(self, mock_graph_rag):
        """自定义 top_k 和 hop 透传到 search。"""
        mock_graph_rag.search.return_value = "结果"
        retriever = KnowledgeRetriever(graph_rag_service=mock_graph_rag)

        retriever.retrieve("查询", user_id=1, top_k=3, hop=1)

        mock_graph_rag.search.assert_called_once_with(
            query="查询", user_id=1, top_k=3, hop=1
        )

    def test_returns_list_of_strings(self, mock_graph_rag):
        """返回值始终是 list[str] 类型，与 shared_evidence 兼容。"""
        mock_graph_rag.search.return_value = "知识片段"
        retriever = KnowledgeRetriever(graph_rag_service=mock_graph_rag)

        result = retriever.retrieve("查询", user_id=1)

        assert isinstance(result, list)
        assert all(isinstance(item, str) for item in result)

    def test_retrieve_with_evidence_preserves_candidates(self, mock_graph_rag):
        mock_graph_rag.search_with_evidence.return_value = {
            "context": "知识上下文",
            "evidence_items": [{
                "source_type": "knowledge",
                "source_id": "page_0001/doc.md",
                "passage": "完整相关段落",
            }],
        }
        retriever = KnowledgeRetriever(graph_rag_service=mock_graph_rag)

        result = retriever.retrieve_with_evidence("查询", user_id=1)

        assert result["contexts"] == ["知识上下文"]
        assert result["evidence_items"][0]["passage"] == "完整相关段落"


@pytest.fixture
def mock_graph_rag():
    """Mock GraphRAGService 实例。"""
    service = MagicMock()
    service.search.return_value = None
    return service
