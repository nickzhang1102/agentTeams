"""EmbeddingService 单元测试"""

import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from services.embedding_service import EmbeddingService


# ==================== Fixtures ====================

SAMPLE_GRAPH = {
    "nodes": [
        {"id": "n1", "label": "肝癌", "community": 0, "source_file": "p1/doc.md"},
        {"id": "n2", "label": "肝脏肿瘤", "community": 0, "source_file": "p1/doc.md"},
        {"id": "n3", "label": "慢性阻塞性肺疾病", "community": 1, "source_file": "p2/doc.md"},
    ],
    "links": [
        {"source": "n1", "target": "n2", "relation": "related_to"},
    ]
}


@pytest.fixture
def mock_config():
    """mock Config 配置"""
    with patch('services.embedding_service.Config') as mock:
        mock.EMBEDDING_BASE_URL = 'http://test-embedding/v1'
        mock.EMBEDDING_MODEL = 'test-model'
        mock.LLM_API_KEY = 'test-key'
        yield mock


@pytest.fixture
def mock_openai():
    """mock OpenAI client"""
    with patch('services.embedding_service.OpenAI') as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        def create_embedding(**kwargs):
            texts = kwargs['input']
            if isinstance(texts, str):
                texts = [texts]
            response = MagicMock()
            response.data = [
                MagicMock(index=i, embedding=[0.1 * (i + 1)] * 10)
                for i in range(len(texts))
            ]
            return response

        mock_client.embeddings.create.side_effect = create_embedding
        yield mock_client


# ==================== 可用性测试 ====================

class TestEmbeddingServiceAvailability:

    def test_unavailable_without_config(self):
        """未配置时服务不可用"""
        with patch('services.embedding_service.Config') as mock:
            mock.EMBEDDING_BASE_URL = None
            mock.EMBEDDING_MODEL = 'test'
            mock.LLM_API_KEY = 'test'
            service = EmbeddingService()
            assert service.available is False

    def test_available_with_config(self, mock_config, mock_openai):
        """配置完整时服务可用"""
        service = EmbeddingService()
        assert service.available is True


# ==================== embed_text 测试 ====================

class TestEmbedText:

    def test_returns_vector(self, mock_config, mock_openai):
        """正常返回向量"""
        service = EmbeddingService()
        vec = service.embed_text('测试文本')
        assert vec is not None
        assert len(vec) == 10

    def test_returns_none_when_unavailable(self):
        """服务不可用时返回 None"""
        with patch('services.embedding_service.Config') as mock:
            mock.EMBEDDING_BASE_URL = None
            mock.EMBEDDING_MODEL = None
            mock.LLM_API_KEY = None
            service = EmbeddingService()
            assert service.embed_text('test') is None

    def test_returns_none_on_api_error(self, mock_config, mock_openai):
        """API 报错时返回 None 不抛异常"""
        mock_openai.embeddings.create.side_effect = Exception('API error')
        service = EmbeddingService()
        result = service.embed_text('test')
        assert result is None


# ==================== embed_batch 测试 ====================

class TestEmbedBatch:

    def test_returns_batch_vectors(self, mock_config, mock_openai):
        """批量返回向量"""
        service = EmbeddingService()
        vecs = service.embed_batch(['文本A', '文本B', '文本C'])
        assert len(vecs) == 3
        assert all(v is not None for v in vecs)

    def test_returns_none_list_when_unavailable(self):
        """服务不可用时返回等长 None 列表"""
        with patch('services.embedding_service.Config') as mock:
            mock.EMBEDDING_BASE_URL = None
            mock.EMBEDDING_MODEL = None
            mock.LLM_API_KEY = None
            service = EmbeddingService()
            result = service.embed_batch(['a', 'b'])
            assert result == [None, None]

    def test_returns_none_list_on_api_error(self, mock_config, mock_openai):
        """API 报错时返回等长 None 列表"""
        mock_openai.embeddings.create.side_effect = Exception('API error')
        service = EmbeddingService()
        result = service.embed_batch(['a', 'b'])
        assert result == [None, None]

    def test_empty_input(self, mock_config, mock_openai):
        """空输入返回空列表"""
        service = EmbeddingService()
        result = service.embed_batch([])
        assert result == []


# ==================== sync_user_embeddings 测试 ====================

class TestSyncUserEmbeddings:

    def test_skip_when_unavailable(self):
        """服务不可用时跳过同步"""
        with patch('services.embedding_service.Config') as mock:
            mock.EMBEDDING_BASE_URL = None
            mock.EMBEDDING_MODEL = None
            mock.LLM_API_KEY = None
            service = EmbeddingService()
            result = service.sync_user_embeddings(1)
            assert result['skipped'] is True

    def test_skip_when_graph_not_found(self, mock_config, mock_openai, tmp_path):
        """图谱不存在时跳过"""
        mock_config.get_user_graph_path = lambda uid: str(tmp_path / f'user_{uid}_graph.json')
        mock_config.KNOWLEDGE_DATA_DIR = str(tmp_path)
        service = EmbeddingService()
        result = service.sync_user_embeddings(999)
        assert result['skipped'] is True

    @patch('db.db')
    def test_sync_writes_to_db(self, mock_db, mock_config, mock_openai, tmp_path):
        """正常同步写入数据库"""
        graph_path = tmp_path / 'user_1_graph.json'
        graph_path.write_text(json.dumps(SAMPLE_GRAPH, ensure_ascii=False), encoding='utf-8')

        mock_config.get_user_graph_path = lambda uid: str(tmp_path / f'user_{uid}_graph.json')
        mock_config.KNOWLEDGE_DATA_DIR = str(tmp_path)

        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db.query.return_value.filter.return_value.delete.return_value = None

        service = EmbeddingService()
        result = service.sync_user_embeddings(1)

        assert result['synced'] == 3
        assert result['failed'] == 0
        assert result['skipped'] is False
        assert mock_db.add.call_count == 3
        mock_db.commit.assert_called_once()

    @patch('db.db')
    def test_skip_when_version_unchanged(self, mock_db, mock_config, mock_openai, tmp_path):
        """版本未变时跳过同步"""
        graph_path = tmp_path / 'user_1_graph.json'
        graph_path.write_text(json.dumps(SAMPLE_GRAPH, ensure_ascii=False), encoding='utf-8')

        mock_config.get_user_graph_path = lambda uid: str(tmp_path / f'user_{uid}_graph.json')
        mock_config.KNOWLEDGE_DATA_DIR = str(tmp_path)

        # mock 已有记录且版本匹配
        import hashlib
        version = hashlib.md5(
            json.dumps(SAMPLE_GRAPH['nodes'], sort_keys=True).encode()
        ).hexdigest()[:16]
        existing = MagicMock()
        existing.graph_version = version
        mock_db.query.return_value.filter.return_value.first.return_value = existing

        service = EmbeddingService()
        result = service.sync_user_embeddings(1)

        assert result['skipped'] is True
        mock_db.commit.assert_not_called()
