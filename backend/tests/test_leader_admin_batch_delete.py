"""Admin Leader 会话批量删除测试

测试 POST /api/admin/leader/sessions/batch-delete 端点：
- 正常批量删除
- 空数组校验
- 不存在 ID 静默跳过
- 级联数据清理
"""
import pytest
import os
import sys
from datetime import datetime, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import (
    User, Conversation, LeaderSession, LeaderAgentResult,
    LeaderWorkflowCancellation, Message,
)
from leader.leader_persistence import create_leader_session
from tests.conftest import TestSessionLocal


# ==================== Fixtures ====================

@pytest.fixture
def sample_leader_sessions(client, admin_auth_header):
    """创建测试用 Leader 会话及其关联数据"""
    session = TestSessionLocal()
    try:
        user = session.query(User).filter_by(username='adminuser').first()
        conv = Conversation(user_id=user.id, title='测试对话')
        session.add(conv)
        session.flush()

        sessions = []
        for i in range(3):
            ls = LeaderSession(
                conversation_id=conv.id,
                user_message=f'测试消息 {i + 1}',
                state='completed',
                total_tokens=1000 * (i + 1),
            )
            session.add(ls)
            session.flush()

            # 每个会话创建关联的 LeaderAgentResult
            ar = LeaderAgentResult(
                conversation_id=conv.id,
                leader_session_id=ls.id,
                agent_id=f'agent-{i}',
                agent_name=f'Agent {i}',
                status='success',
                content=f'结果 {i}',
                sequence_number=i + 1,
            )
            session.add(ar)

            # 创建关联的 Message（Leader 类型）
            Message.create_leader_message(
                conversation_id=conv.id,
                leader_session_id=ls.id,
                message_type='progress',
                content={'step': i},
                sequence_number=i + 1,
            )

            sessions.append(ls)

        session.commit()
        return [s.id for s in sessions]
    finally:
        session.close()


# ==================== 测试用例 ====================

class TestBatchDeleteLeaderSessions:

    def test_batch_delete_requires_admin(self, client, auth_header):
        """非管理员无法批量删除"""
        resp = client.post(
            '/api/admin/leader/sessions/batch-delete',
            json={'session_ids': [1, 2]},
            headers=auth_header,
        )
        assert resp.status_code == 403

    def test_batch_delete_success(self, client, admin_auth_header, sample_leader_sessions):
        """正常批量删除多条会话"""
        ids = sample_leader_sessions[:2]
        resp = client.post(
            '/api/admin/leader/sessions/batch-delete',
            json={'session_ids': ids},
            headers=admin_auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data['deleted'] == 2
        assert data['failed_ids'] == []

    def test_batch_delete_cleans_cascade_data(self, client, admin_auth_header, sample_leader_sessions):
        """删除会话后关联数据应被清理"""
        session_id = sample_leader_sessions[0]

        resp = client.post(
            '/api/admin/leader/sessions/batch-delete',
            json={'session_ids': [session_id]},
            headers=admin_auth_header,
        )
        assert resp.status_code == 200
        assert resp.json()['deleted'] == 1

        # 验证 LeaderAgentResult 已清理
        db = TestSessionLocal()
        try:
            ar_count = db.query(LeaderAgentResult).filter(
                LeaderAgentResult.leader_session_id == session_id
            ).count()
            assert ar_count == 0

            # 验证 Message 已清理
            msg_count = db.query(Message).filter(
                Message.leader_session_id == session_id
            ).count()
            assert msg_count == 0

            # 验证 LeaderSession 已删除
            ls = db.get(LeaderSession, session_id)
            assert ls is None
        finally:
            db.close()

    def test_batch_delete_nonexistent_ids(self, client, admin_auth_header, sample_leader_sessions):
        """不存在的 ID 静默跳过，返回在 failed_ids 中"""
        existing_id = sample_leader_sessions[0]
        resp = client.post(
            '/api/admin/leader/sessions/batch-delete',
            json={'session_ids': [existing_id, 99999]},
            headers=admin_auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data['deleted'] == 1
        assert 99999 in data['failed_ids']

    def test_batch_delete_stops_active_session_before_delete(
        self,
        client,
        admin_auth_header,
        sample_leader_sessions,
    ):
        """活动 Session 删除前留下跨 worker 取消墓碑并取消本进程任务。"""
        db = TestSessionLocal()
        try:
            completed = db.get(LeaderSession, sample_leader_sessions[0])
            active = create_leader_session(
                db,
                completed.conversation_id,
                "运行中的分析",
                auto_commit=False,
            )
            active_id = active.id
            db.commit()
        finally:
            db.close()

        with patch(
            'api.admin.leader_admin_api.cancel_background_task',
            return_value=True,
        ) as cancel_task:
            resp = client.post(
                '/api/admin/leader/sessions/batch-delete',
                json={'session_ids': [active_id]},
                headers=admin_auth_header,
            )

        assert resp.status_code == 200
        assert resp.json()['deleted'] == 1
        cancel_task.assert_called_once_with(active_id)

        db = TestSessionLocal()
        try:
            assert db.get(LeaderSession, active_id) is None
            marker = db.get(LeaderWorkflowCancellation, active_id)
            assert marker is not None
            assert marker.reason == 'admin_deleted'
        finally:
            db.close()

    def test_batch_delete_empty_list(self, client, admin_auth_header):
        """空数组返回 400"""
        resp = client.post(
            '/api/admin/leader/sessions/batch-delete',
            json={'session_ids': []},
            headers=admin_auth_header,
        )
        assert resp.status_code == 400

    def test_batch_delete_no_token(self, client):
        """未认证请求被拒绝"""
        resp = client.post(
            '/api/admin/leader/sessions/batch-delete',
            json={'session_ids': [1]},
        )
        assert resp.status_code in [401, 403]
