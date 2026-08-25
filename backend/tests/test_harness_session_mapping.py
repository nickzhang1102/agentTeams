"""
测试 HarnessSessionMapping 模型 - FastAPI 版

迁移自 Flask test client 到 FastAPI TestClient：
- 使用 SessionLocal 替代 db.session
- 无需 app.app_context()
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.environ['SKIP_MCP_INIT'] = 'true'

from tests.conftest import TestSessionLocal as SessionLocal
from models import User, Conversation, LeaderSession, HarnessSessionMapping


class TestHarnessSessionMapping:
    """测试 OpenHarness Session 映射模型"""

    def test_create_harness_session_mapping(self, client, auth_header):
        """测试创建映射记录"""
        db = SessionLocal()
        try:
            user = db.query(User).filter_by(username='testuser').first()

            conv = Conversation(title='Test Conversation', user_id=user.id)
            db.add(conv)
            db.commit()
            db.refresh(conv)

            leader_session = LeaderSession(
                conversation_id=conv.id,
                user_message='test message',
                state='idle'
            )
            db.add(leader_session)
            db.commit()
            db.refresh(leader_session)

            # 创建映射
            mapping = HarnessSessionMapping(
                leader_session_id=leader_session.id,
                harness_session_id='oh-session-123',
                harness_metadata={'test': 'data', 'version': '0.1.2'}
            )
            db.add(mapping)
            db.commit()
            db.refresh(mapping)

            # 验证
            assert mapping.id is not None
            assert mapping.leader_session_id == leader_session.id
            assert mapping.harness_session_id == 'oh-session-123'
            assert mapping.harness_metadata == {'test': 'data', 'version': '0.1.2'}
            assert mapping.created_at is not None
        finally:
            db.close()

    def test_harness_session_id_unique(self, client, auth_header):
        """测试 harness_session_id 唯一约束"""
        db = SessionLocal()
        try:
            user = db.query(User).filter_by(username='testuser').first()

            conv = Conversation(title='Test Conversation', user_id=user.id)
            db.add(conv)
            db.commit()
            db.refresh(conv)

            leader_session1 = LeaderSession(
                conversation_id=conv.id,
                user_message='test1',
                state='idle'
            )
            db.add(leader_session1)
            db.commit()
            db.refresh(leader_session1)

            mapping1 = HarnessSessionMapping(
                leader_session_id=leader_session1.id,
                harness_session_id='oh-session-unique',
                harness_metadata={}
            )
            db.add(mapping1)
            db.commit()

            # 创建第二个映射，使用相同的 harness_session_id
            leader_session2 = LeaderSession(
                conversation_id=conv.id,
                user_message='test2',
                state='idle'
            )
            db.add(leader_session2)
            db.commit()
            db.refresh(leader_session2)

            mapping2 = HarnessSessionMapping(
                leader_session_id=leader_session2.id,
                harness_session_id='oh-session-unique',  # 相同的 ID
                harness_metadata={}
            )
            db.add(mapping2)

            # 应该抛出唯一约束错误
            with pytest.raises(Exception):  # IntegrityError
                db.commit()
            db.rollback()
        finally:
            db.close()

    def test_leader_session_relationship(self, client, auth_header):
        """测试 LeaderSession 关系"""
        db = SessionLocal()
        try:
            user = db.query(User).filter_by(username='testuser').first()

            conv = Conversation(title='Test Conversation', user_id=user.id)
            db.add(conv)
            db.commit()
            db.refresh(conv)

            leader_session = LeaderSession(
                conversation_id=conv.id,
                user_message='test message',
                state='idle'
            )
            db.add(leader_session)
            db.commit()
            db.refresh(leader_session)

            mapping = HarnessSessionMapping(
                leader_session_id=leader_session.id,
                harness_session_id='oh-session-123',
                harness_metadata={}
            )
            db.add(mapping)
            db.commit()
            db.refresh(mapping)

            # 验证关系
            assert mapping.leader_session is not None
            assert mapping.leader_session.id == leader_session.id
            assert mapping.leader_session.user_message == 'test message'
        finally:
            db.close()

    def test_to_dict_method(self, client, auth_header):
        """测试 to_dict 方法"""
        db = SessionLocal()
        try:
            user = db.query(User).filter_by(username='testuser').first()

            conv = Conversation(title='Test Conversation', user_id=user.id)
            db.add(conv)
            db.commit()
            db.refresh(conv)

            leader_session = LeaderSession(
                conversation_id=conv.id,
                user_message='test message',
                state='idle'
            )
            db.add(leader_session)
            db.commit()
            db.refresh(leader_session)

            mapping = HarnessSessionMapping(
                leader_session_id=leader_session.id,
                harness_session_id='oh-session-123',
                harness_metadata={'key': 'value'}
            )
            db.add(mapping)
            db.commit()
            db.refresh(mapping)

            # 验证 to_dict
            result = mapping.to_dict()
            assert result['id'] == mapping.id
            assert result['leader_session_id'] == leader_session.id
            assert result['harness_session_id'] == 'oh-session-123'
            assert result['harness_metadata'] == {'key': 'value'}
            assert 'created_at' in result
        finally:
            db.close()

    @pytest.mark.skip(reason="CASCADE 删除需要完整数据库状态验证")
    def test_cascade_delete(self, client, auth_header):
        """测试级联删除"""
        pass

    def test_jsonb_metadata_storage(self, client, auth_header):
        """测试 JSONB 元数据存储"""
        db = SessionLocal()
        try:
            user = db.query(User).filter_by(username='testuser').first()

            conv = Conversation(title='Test Conversation', user_id=user.id)
            db.add(conv)
            db.commit()
            db.refresh(conv)

            leader_session = LeaderSession(
                conversation_id=conv.id,
                user_message='test message',
                state='idle'
            )
            db.add(leader_session)
            db.commit()
            db.refresh(leader_session)

            # 存储复杂 JSONB 数据
            complex_metadata = {
                'version': '0.1.2',
                'config': {
                    'model': 'claude-3',
                    'temperature': 0.7
                },
                'tags': ['tag1', 'tag2', 'tag3'],
                'nested': {
                    'deep': {
                        'value': 42
                    }
                }
            }

            mapping = HarnessSessionMapping(
                leader_session_id=leader_session.id,
                harness_session_id='oh-session-jsonb',
                harness_metadata=complex_metadata
            )
            db.add(mapping)
            db.commit()
            db.refresh(mapping)

            # 验证 JSONB 存储
            assert mapping.harness_metadata == complex_metadata
            assert mapping.harness_metadata['config']['model'] == 'claude-3'
            assert mapping.harness_metadata['tags'] == ['tag1', 'tag2', 'tag3']
        finally:
            db.close()

    def test_query_by_leader_session(self, client, auth_header):
        """测试按 leader_session_id 查询"""
        db = SessionLocal()
        try:
            user = db.query(User).filter_by(username='testuser').first()

            conv = Conversation(title='Test Conversation', user_id=user.id)
            db.add(conv)
            db.commit()
            db.refresh(conv)

            leader_session = LeaderSession(
                conversation_id=conv.id,
                user_message='test message',
                state='idle'
            )
            db.add(leader_session)
            db.commit()
            db.refresh(leader_session)

            mapping = HarnessSessionMapping(
                leader_session_id=leader_session.id,
                harness_session_id='oh-session-query',
                harness_metadata={}
            )
            db.add(mapping)
            db.commit()

            # 查询
            result = db.query(HarnessSessionMapping).filter_by(
                leader_session_id=leader_session.id
            ).first()

            assert result is not None
            assert result.harness_session_id == 'oh-session-query'
        finally:
            db.close()

    def test_repr_method(self, client, auth_header):
        """测试 __repr__ 方法"""
        db = SessionLocal()
        try:
            user = db.query(User).filter_by(username='testuser').first()

            conv = Conversation(title='Test Conversation', user_id=user.id)
            db.add(conv)
            db.commit()
            db.refresh(conv)

            leader_session = LeaderSession(
                conversation_id=conv.id,
                user_message='test message',
                state='idle'
            )
            db.add(leader_session)
            db.commit()
            db.refresh(leader_session)

            mapping = HarnessSessionMapping(
                leader_session_id=leader_session.id,
                harness_session_id='oh-session-repr',
                harness_metadata={}
            )
            db.add(mapping)
            db.commit()
            db.refresh(mapping)

            # 验证 __repr__
            repr_str = repr(mapping)
            assert 'HarnessSessionMapping' in repr_str
            assert str(mapping.id) in repr_str
        finally:
            db.close()