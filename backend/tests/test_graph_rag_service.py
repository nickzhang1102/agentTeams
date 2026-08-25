"""GraphRAG 服务单元测试"""

import json
import os
import tempfile
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest

from services.graph_rag_service import GraphRAGService


# ==================== Fixtures ====================

SAMPLE_GRAPH = {
    "nodes": [
        {"id": "n1", "label": "工会经费", "community": 0, "source_file": "page_0001/doc.md", "file_type": "concept"},
        {"id": "n2", "label": "慰问金", "community": 0, "source_file": "page_0001/doc.md", "file_type": "concept"},
        {"id": "n3", "label": "永安期货", "community": 0, "source_file": "page_0002/doc.md", "file_type": "document"},
        {"id": "n4", "label": "生日慰问", "community": 0, "source_file": "page_0003/doc.md", "file_type": "concept"},
        {"id": "n5", "label": "期货交易规则", "community": 1, "source_file": "page_0010/doc.md", "file_type": "document"},
        {"id": "n6", "label": "保证金", "community": 1, "source_file": "page_0010/doc.md", "file_type": "concept"},
    ],
    "links": [
        {"source": "n1", "target": "n2", "relation": "contains", "confidence": "HIGH"},
        {"source": "n1", "target": "n3", "relation": "belongs_to", "confidence": "HIGH"},
        {"source": "n2", "target": "n4", "relation": "type_of", "confidence": "MEDIUM"},
        {"source": "n5", "target": "n6", "relation": "contains", "confidence": "HIGH"},
    ]
}


@pytest.fixture(autouse=True)
def reset_singleton():
    """每个测试前重置单例"""
    GraphRAGService._instance = None
    yield
    GraphRAGService._instance = None


@pytest.fixture
def graph_service(tmp_path):
    """创建带测试图谱的 GraphRAG 服务"""
    graph_path = tmp_path / "user_1_graph.json"
    graph_path.write_text(json.dumps(SAMPLE_GRAPH, ensure_ascii=False), encoding='utf-8')

    with patch('services.graph_rag_service.Config') as mock_config:
        mock_config.get_user_graph_path = lambda user_id: str(tmp_path / f"user_{user_id}_graph.json")
        service = GraphRAGService()
        yield service


# ==================== 加载测试 ====================

class TestGraphRAGLoading:

    def test_load_graph(self, graph_service):
        """能正确加载用户图谱"""
        indices = graph_service._load_user_graph(1)
        assert indices is not None
        assert len(indices['nodes']) == 6
        assert len(indices['edges']) == 4

    def test_adjacency_bidirectional(self, graph_service):
        """邻接表双向构建"""
        indices = graph_service._load_user_graph(1)
        adjacency = indices['adjacency']
        # n1 -> n2, n3
        neighbors_n1 = set(adjacency['n1'])
        assert 'n2' in neighbors_n1
        assert 'n3' in neighbors_n1
        # n2 -> n1, n4（双向）
        neighbors_n2 = set(adjacency['n2'])
        assert 'n1' in neighbors_n2
        assert 'n4' in neighbors_n2

    def test_singleton(self, graph_service):
        """单例模式"""
        instance1 = GraphRAGService.get_instance()
        instance2 = GraphRAGService.get_instance()
        assert instance1 is instance2

    def test_reload(self, graph_service):
        """用户图谱不存在时返回 None"""
        indices = graph_service._load_user_graph(999)
        assert indices is None

    def test_build_indices_normalizes_multiple_source_files(self, graph_service):
        indices = graph_service._build_indices({
            "nodes": [{
                "id": "multi",
                "label": "共享实体",
                "source_file": "page_0001/doc.md,page_0002/doc.md",
            }],
            "links": [],
        })

        assert indices["nodes"]["multi"]["source_files"] == [
            "page_0001/doc.md",
            "page_0002/doc.md",
        ]
        assert set(indices["source_index"]) == {
            "page_0001/doc.md",
            "page_0002/doc.md",
        }


# ==================== 搜索测试 ====================

class TestGraphRAGSearch:

    def test_exact_match(self, graph_service):
        """精确匹配节点"""
        result = graph_service.search('工会经费', user_id=1)
        assert result is not None
        assert '工会经费' in result

    def test_partial_match(self, graph_service):
        """部分匹配"""
        result = graph_service.search('请问工会的慰问金怎么发', user_id=1)
        assert result is not None
        assert '工会' in result or '慰问金' in result

    def test_no_match(self, graph_service):
        """无匹配结果"""
        result = graph_service.search('今天天气怎么样', user_id=1)
        assert result is None

    def test_traversal_collects_neighbors(self, graph_service):
        """图遍历收集邻居"""
        result = graph_service.search('工会经费', user_id=1)
        assert result is not None
        # 遍历应该收集到相关节点
        assert '慰问金' in result or '永安期货' in result

    def test_community_grouping(self, graph_service):
        """按 community 分组"""
        result = graph_service.search('期货交易规则', user_id=1)
        assert result is not None
        assert 'community 1' in result

    def test_source_file_in_context(self, graph_service):
        """上下文包含实体和领域信息"""
        result = graph_service.search('工会经费', user_id=1)
        assert result is not None
        # 返回实体和社区分组信息
        assert '工会经费' in result
        assert 'community' in result

    def test_empty_query(self, graph_service):
        """空查询"""
        result = graph_service.search('', user_id=1)
        assert result is None

    def test_stop_words_only(self, graph_service):
        """仅停用词"""
        result = graph_service.search('的了吗', user_id=1)
        assert result is None

    def test_context_length_limit(self, graph_service):
        """上下文长度限制"""
        result = graph_service.search('工会经费', user_id=1)
        if result:
            assert len(result) <= 3000 + 100  # MAX_CONTEXT_CHARS + buffer

    def test_user_graph_not_found(self, graph_service):
        """用户图谱不存在时返回 None"""
        result = graph_service.search('工会经费', user_id=999)
        assert result is None


# ==================== 匹配策略测试 ====================

class TestMatchingStrategy:

    def test_exact_label_in_query(self, graph_service):
        """label 是 query 子串（高分）"""
        result = graph_service.search('请问工会经费怎么用', user_id=1)
        assert result is not None
        assert '工会经费' in result

    def test_query_in_label(self, graph_service):
        """query 是 label 子串（中分）"""
        result = graph_service.search('工会', user_id=1)
        assert result is not None
        assert '工会经费' in result

    def test_bigram_fallback(self, graph_service):
        """双字匹配兜底"""
        result = graph_service.search('保证', user_id=1)
        assert result is not None
        assert '保证金' in result

    def test_no_match(self, graph_service):
        """无任何匹配"""
        result = graph_service.search('xyz', user_id=1)
        assert result is None

    def test_search_with_evidence_returns_per_document_passage(self, graph_service):
        passage = "A" * 350 + "关键限定条件"
        with patch.object(
            graph_service,
            "_read_snippets",
            return_value={"page_0001/doc.md": passage},
        ):
            result = graph_service.search_with_evidence("工会经费", user_id=1)

        assert result is not None
        evidence = result["evidence_items"][0]
        assert evidence["source_type"] == "knowledge"
        assert evidence["locator"] == {"source_file": "page_0001/doc.md"}
        assert "关键限定条件" in evidence["passage"]
        assert len(evidence["excerpt"]) <= 503


class TestVectorRecall:

    def test_vector_recall_returns_real_similarity_and_filters_low_scores(self, graph_service):
        embedding_service = MagicMock(available=True)
        embedding_service.embed_text.return_value = [0.1, 0.2]

        node_embedding = MagicMock()
        node_embedding.user_id = MagicMock()
        node_embedding.node_id = MagicMock()
        node_embedding.embedding.cosine_distance.return_value.label.return_value = MagicMock()

        query = MagicMock()
        query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            SimpleNamespace(node_id="n1", distance=0.2),
            SimpleNamespace(node_id="n2", distance=0.9),
        ]
        db_mock = MagicMock()
        db_mock.query.return_value = query

        fake_pgvector = types.ModuleType("pgvector")
        fake_pgvector_sqlalchemy = types.ModuleType("pgvector.sqlalchemy")
        fake_pgvector_sqlalchemy.Vector = object

        with patch.dict(sys.modules, {
            "pgvector": fake_pgvector,
            "pgvector.sqlalchemy": fake_pgvector_sqlalchemy,
        }), patch("services.embedding_service.get_embedding_service", return_value=embedding_service), \
             patch("models.NodeEmbedding", node_embedding), \
             patch("db.db", db_mock):
            result = graph_service._vector_recall(
                "工会经费", 1, {"n1": {}, "n2": {}}, top_k=8
            )

        assert result == [("n1", pytest.approx(0.8))]


class TestSnippetReading:

    def test_read_snippets_blocks_parent_traversal(self, graph_service, tmp_path):
        markdown_root = tmp_path / "markdown"
        markdown_root.mkdir()
        (markdown_root / "inside.md").write_text("允许读取", encoding="utf-8")
        (tmp_path / "secret.md").write_text("不得读取", encoding="utf-8")

        doc = MagicMock(markdown_path=str(markdown_root))
        query = MagicMock()
        query.filter.return_value.all.return_value = [doc]
        db_mock = MagicMock()
        db_mock.query.return_value = query

        with patch("db.db", db_mock):
            snippets = graph_service._read_snippets(
                {"inside.md", "../secret.md"}, user_id=1, query="允许"
            )

        assert snippets == {"inside.md": "允许读取"}

    def test_read_snippets_uses_relevant_window(self, graph_service, tmp_path):
        markdown_root = tmp_path / "markdown"
        markdown_root.mkdir()
        content = "导言内容。" * 80 + "肝癌治疗关键证据：建议结合分期评估。" + "结尾。" * 40
        (markdown_root / "case.md").write_text(content, encoding="utf-8")

        doc = MagicMock(markdown_path=str(markdown_root))
        query = MagicMock()
        query.filter.return_value.all.return_value = [doc]
        db_mock = MagicMock()
        db_mock.query.return_value = query

        with patch("db.db", db_mock):
            snippets = graph_service._read_snippets(
                {"case.md"},
                user_id=1,
                query="肝癌治疗",
                source_labels={"case.md": {"肝癌"}},
            )

        assert "肝癌治疗关键证据" in snippets["case.md"]
        assert len(snippets["case.md"]) <= 206
