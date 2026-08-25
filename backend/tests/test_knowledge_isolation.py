"""
多用户隔离测试

验证知识库个人化改造后的行级鉴权：
- 上传自动归属当前用户
- 列表只返回自己的文档
- 删除/下载/预览权限检查
- 分类按用户隔离（个人 + 共享）
- 状态查询按用户过滤
- knowledge_search user_id 传递
"""

import pytest
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

from models import KnowledgeDocument, KnowledgeCategory


# ==================== 辅助函数 ====================

def get_user_id_from_header(client, auth_header):
    """通过 /api/auth/me 获取用户 ID"""
    resp = client.get('/api/auth/me', headers=auth_header)
    assert resp.status_code == 200
    return resp.json()['id']


def upload_doc(client, auth_header, filename='test.txt', content=b'test content', category='default'):
    """辅助：上传一个知识库文档"""
    return client.post(
        '/api/knowledge/upload',
        headers=auth_header,
        files={'file': (filename, BytesIO(content), 'text/plain')},
        data={'category': category}
    )


# ==================== S1: 上传归属 + 列表过滤 ====================

class TestUploadOwnership:
    """上传文档自动归属当前用户"""

    def test_upload_sets_uploaded_by(self, client, auth_header, db_session):
        """上传文档后 uploaded_by = 当前用户 id"""
        user_id = get_user_id_from_header(client, auth_header)

        resp = upload_doc(client, auth_header)
        assert resp.status_code == 200

        doc = db_session.query(KnowledgeDocument).first()
        assert doc is not None
        assert doc.uploaded_by == user_id

    def test_upload_two_users_different_owner(self, client, auth_header, another_user_auth_header, db_session):
        """两个用户上传的文档归属不同"""
        user_a_id = get_user_id_from_header(client, auth_header)
        user_b_id = get_user_id_from_header(client, another_user_auth_header)

        upload_doc(client, auth_header, filename='a.txt', content=b'content A')
        upload_doc(client, another_user_auth_header, filename='b.txt', content=b'content B')

        docs = db_session.query(KnowledgeDocument).all()
        assert len(docs) == 2

        owners = {d.uploaded_by for d in docs}
        assert owners == {user_a_id, user_b_id}


class TestListFiltering:
    """列表只返回当前用户的文档"""

    def test_list_only_own_docs(self, client, auth_header, another_user_auth_header):
        """用户 A 的列表不含用户 B 的文档"""
        upload_doc(client, auth_header, filename='a.txt', content=b'content A')
        upload_doc(client, another_user_auth_header, filename='b.txt', content=b'content B')

        resp = client.get('/api/knowledge/documents', headers=auth_header)
        assert resp.status_code == 200

        docs = resp.json()['documents']
        assert len(docs) == 1
        assert docs[0]['original_filename'] == 'a.txt'

    def test_list_empty_for_new_user(self, client, auth_header, another_user_auth_header):
        """没有上传过文档的用户列表为空（只看到别人的文档不算）"""
        # another_user 上传文档
        upload_doc(client, another_user_auth_header, filename='b.txt', content=b'content B')

        # auth_header 用户没上传过任何文档
        resp = client.get('/api/knowledge/documents', headers=auth_header)
        assert resp.status_code == 200
        assert resp.json()['documents'] == []
        assert resp.json()['total'] == 0


# ==================== S2: 删除/下载/预览权限 ====================

class TestDeletePermission:
    """只能删除自己的文档"""

    def test_delete_own_doc_success(self, client, auth_header, db_session):
        """删除自己的文档成功"""
        upload_doc(client, auth_header, filename='mine.txt', content=b'mine')
        doc = db_session.query(KnowledgeDocument).first()

        resp = client.delete(f'/api/knowledge/documents/{doc.id}', headers=auth_header)
        assert resp.status_code == 204

    def test_delete_other_user_doc_forbidden(self, client, auth_header, another_user_auth_header, db_session):
        """删除别人的文档返回 403"""
        upload_doc(client, another_user_auth_header, filename='theirs.txt', content=b'theirs')
        doc = db_session.query(KnowledgeDocument).first()

        resp = client.delete(f'/api/knowledge/documents/{doc.id}', headers=auth_header)
        assert resp.status_code == 403

    def test_delete_nonexistent_doc(self, client, auth_header):
        """删除不存在的文档返回 404"""
        resp = client.delete('/api/knowledge/documents/99999', headers=auth_header)
        assert resp.status_code == 404


class TestDownloadPermission:
    """只能下载/预览自己的文档"""

    def test_download_own_doc(self, client, auth_header, db_session):
        """下载自己的文档成功"""
        upload_doc(client, auth_header, filename='dl.txt', content=b'download me')
        doc = db_session.query(KnowledgeDocument).first()

        resp = client.get(f'/api/knowledge/documents/{doc.id}/download', headers=auth_header)
        assert resp.status_code == 200

    def test_download_other_user_doc_forbidden(self, client, auth_header, another_user_auth_header, db_session):
        """下载别人的文档返回 403"""
        upload_doc(client, another_user_auth_header, filename='secret.txt', content=b'secret')
        doc = db_session.query(KnowledgeDocument).first()

        resp = client.get(f'/api/knowledge/documents/{doc.id}/download', headers=auth_header)
        assert resp.status_code == 403

    def test_preview_own_doc(self, client, auth_header, db_session):
        """预览自己的文档成功"""
        upload_doc(client, auth_header, filename='pv.txt', content=b'preview me')
        doc = db_session.query(KnowledgeDocument).first()

        resp = client.get(f'/api/knowledge/documents/{doc.id}/preview', headers=auth_header)
        assert resp.status_code == 200

    def test_preview_other_user_doc_forbidden(self, client, auth_header, another_user_auth_header, db_session):
        """预览别人的文档返回 403"""
        upload_doc(client, another_user_auth_header, filename='secret.txt', content=b'secret')
        doc = db_session.query(KnowledgeDocument).first()

        resp = client.get(f'/api/knowledge/documents/{doc.id}/preview', headers=auth_header)
        assert resp.status_code == 403


# ==================== S3: 分类隔离 + 状态过滤 ====================

class TestCategoryIsolation:
    """分类按用户隔离（个人 + 共享）"""

    def test_categories_include_personal_and_shared(self, client, auth_header, db_session):
        """分类列表含个人分类 + 共享分类"""
        user_id = get_user_id_from_header(client, auth_header)

        # 创建共享分类（user_id IS NULL）
        shared_cat = KnowledgeCategory(key='shared_test', label='共享测试', user_id=None, is_active=True)
        # 创建个人分类
        personal_cat = KnowledgeCategory(key='personal_test', label='个人测试', user_id=user_id, is_active=True)
        db_session.add_all([shared_cat, personal_cat])
        db_session.commit()

        resp = client.get('/api/knowledge/categories', headers=auth_header)
        assert resp.status_code == 200

        cat_keys = {c['key'] for c in resp.json()['categories']}
        assert 'shared_test' in cat_keys
        assert 'personal_test' in cat_keys

    def test_personal_category_hidden_from_other_user(self, client, auth_header, another_user_auth_header, db_session):
        """用户 A 的个人分类不出现在用户 B 的列表中"""
        user_a_id = get_user_id_from_header(client, auth_header)

        personal_cat = KnowledgeCategory(key='a_only', label='A 专属', user_id=user_a_id, is_active=True)
        db_session.add(personal_cat)
        db_session.commit()

        resp = client.get('/api/knowledge/categories', headers=another_user_auth_header)
        assert resp.status_code == 200

        cat_keys = {c['key'] for c in resp.json()['categories']}
        assert 'a_only' not in cat_keys


class TestStatusFiltering:
    """状态查询按用户过滤"""

    def test_status_only_counts_own_docs(self, client, auth_header, another_user_auth_header):
        """状态查询只计当前用户的文档数"""
        upload_doc(client, auth_header, filename='a1.txt', content=b'a1')
        upload_doc(client, auth_header, filename='a2.txt', content=b'a2')
        upload_doc(client, another_user_auth_header, filename='b1.txt', content=b'b1')

        resp = client.get('/api/knowledge/status', headers=auth_header)
        assert resp.status_code == 200

        data = resp.json()
        assert data['total_docs'] == 2  # 只计用户 A 的

        # 用户 B 只有 1 篇
        resp_b = client.get('/api/knowledge/status', headers=another_user_auth_header)
        assert resp_b.json()['total_docs'] == 1


# ==================== S4: knowledge_search user_id 传递 ====================

class TestKnowledgeSearchUserId:
    """knowledge_search 工具 user_id 传递（mock 隔离）"""

    @pytest.mark.asyncio
    async def test_no_user_id_returns_error(self):
        """无 user_id 时返回 error ToolResult"""
        from custom_knowledge_search_tool import KnowledgeSearchTool
        from openharness.tools.base import ToolExecutionContext, ToolResult

        tool = KnowledgeSearchTool(retriever=None)
        input_data = MagicMock()
        input_data.query = "test query"

        # context metadata 无 user_id
        context = ToolExecutionContext(cwd=Path('.'), metadata={})

        result = await tool.execute(input_data, context)

        assert isinstance(result, ToolResult)
        assert result.is_error is True
        assert "user_id not provided" in result.output

    @pytest.mark.asyncio
    async def test_user_id_passed_to_retriever(self):
        """有 user_id 时 retriever.retrieve 收到该 user_id"""
        from custom_knowledge_search_tool import KnowledgeSearchTool
        from openharness.tools.base import ToolExecutionContext

        mock_retriever = MagicMock()
        mock_retriever.retrieve_with_evidence.return_value = {
            "contexts": ["知识片段"],
            "evidence_items": [{"source_type": "knowledge", "source_id": "doc.md"}],
        }

        tool = KnowledgeSearchTool(retriever=mock_retriever)
        input_data = MagicMock()
        input_data.query = "test query"

        context = ToolExecutionContext(
            cwd=Path('.'),
            metadata={"user_id": 42}
        )

        await tool.execute(input_data, context)

        mock_retriever.retrieve_with_evidence.assert_called_once_with(
            query="test query", user_id=42
        )

    @pytest.mark.asyncio
    async def test_user_id_none_returns_error(self):
        """user_id 为 None 时返回 error ToolResult"""
        from custom_knowledge_search_tool import KnowledgeSearchTool
        from openharness.tools.base import ToolExecutionContext, ToolResult

        tool = KnowledgeSearchTool(retriever=None)
        input_data = MagicMock()
        input_data.query = "test query"

        context = ToolExecutionContext(cwd=Path('.'), metadata={"user_id": None})

        result = await tool.execute(input_data, context)

        assert isinstance(result, ToolResult)
        assert result.is_error is True


# ==================== S5: 分类校验隔离 + 删除跨用户保护（回归） ====================

class TestCategoryValidationScoping:
    """分类有效性校验按用户隔离（个人 + 共享）

    回归 finding-02：list/upload 的分类校验必须只接受当前用户可见的分类
    （个人 + 共享 user_id IS NULL），不得接受他人个人分类 key。
    """

    def test_upload_other_user_personal_category_rejected(self, client, auth_header, another_user_auth_header, db_session):
        """用户上传时不能使用他人个人分类 key"""
        user_a_id = get_user_id_from_header(client, auth_header)
        personal = KnowledgeCategory(
            key='a_personal_cat', label='A个人',
            user_id=user_a_id, is_active=True
        )
        db_session.add(personal)
        db_session.commit()

        # 用户 B 用 A 的个人分类 key 上传 → 应被拒（400）
        resp = upload_doc(
            client, another_user_auth_header,
            filename='b.txt', content=b'b', category='a_personal_cat'
        )
        assert resp.status_code == 400

    def test_create_category_same_key_different_users_ok(self, client, auth_header, another_user_auth_header):
        """不同用户可创建同名个人分类（key 仅用户内唯一）"""
        resp_a = client.post(
            '/api/knowledge/admin/categories', headers=auth_header,
            json={'key': 'dupkey', 'label': 'A分类'}
        )
        assert resp_a.status_code == 201

        # B 创建同名 → 应成功（不与 A 的个人分类冲突）
        resp_b = client.post(
            '/api/knowledge/admin/categories', headers=another_user_auth_header,
            json={'key': 'dupkey', 'label': 'B分类'}
        )
        assert resp_b.status_code == 201

    def test_create_category_same_key_same_user_conflict(self, client, auth_header):
        """同一用户重复同名分类应 400"""
        client.post(
            '/api/knowledge/admin/categories', headers=auth_header,
            json={'key': 'dupkey2', 'label': 'A分类'}
        )
        resp = client.post(
            '/api/knowledge/admin/categories', headers=auth_header,
            json={'key': 'dupkey2', 'label': 'A分类重名'}
        )
        assert resp.status_code == 400


class TestDeleteCategoryCrossUser:
    """删除个人分类不应影响他人文档

    回归 finding-01：删除分类置空文档 category 时必须按 user_id 收窄，
    不得跨用户静默清空。
    """

    def test_delete_category_keeps_other_user_docs(self, client, auth_header, another_user_auth_header, db_session):
        """删除自己的分类不会置空他人文档的 category"""
        user_a_id = get_user_id_from_header(client, auth_header)
        user_b_id = get_user_id_from_header(client, another_user_auth_header)

        # A 创建个人分类并上传文档
        personal = KnowledgeCategory(
            key='shared_cat_key', label='共享键',
            user_id=user_a_id, is_active=True
        )
        db_session.add(personal)
        db_session.commit()
        upload_doc(client, auth_header, filename='a.txt', content=b'a', category='shared_cat_key')

        # B 的文档直接 DB 插入，category 复用同一 key（模拟跨用户共用边界）
        b_doc = KnowledgeDocument(
            filename='b.txt', original_filename='b.txt',
            category='shared_cat_key', uploaded_by=user_b_id, status='pending'
        )
        db_session.add(b_doc)
        db_session.commit()
        b_doc_id = b_doc.id

        # A 删除自己的分类
        resp = client.delete(
            f'/api/knowledge/admin/categories/{personal.id}', headers=auth_header
        )
        assert resp.status_code == 204

        # B 的文档 category 不应被置空
        db_session.expire_all()
        refreshed_b = db_session.get(KnowledgeDocument, b_doc_id)
        assert refreshed_b.category == 'shared_cat_key'
