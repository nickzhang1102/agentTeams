"""Admin API 测试（FastAPI TestClient）

测试管理员后台功能：
- Dashboard 统计数据
- 系统活动日志
- 权限控制

迁移自 Flask test_client，使用 conftest 提供的 fixture。
"""
import pytest
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import User, Conversation, Message, AgentConfig, LeaderSession, LeaderReportRating
from db import Base
from sqlalchemy.orm import sessionmaker


def _get_admin_user_id():
    """从测试库查询 adminuser 的 id"""
    from tests.conftest import TestSessionLocal
    session = TestSessionLocal()
    try:
        user = session.query(User).filter_by(username='adminuser').first()
        return user.id if user else None
    finally:
        session.close()


def test_dashboard_stats_requires_admin(client, auth_header):
    """测试 dashboard stats 需要管理员权限（普通用户应 403）"""
    response = client.get(
        '/api/admin/dashboard/stats',
        headers=auth_header
    )
    assert response.status_code == 403


def test_dashboard_stats_success(client, admin_auth_header):
    """测试 dashboard stats 成功返回"""
    # 创建测试数据
    from tests.conftest import TestSessionLocal
    session = TestSessionLocal()
    try:
        user = session.query(User).filter_by(username='adminuser').first()
        assert user is not None, "adminuser 应已被 conftest 创建"

        conv = Conversation(user_id=user.id, title='Test')
        session.add(conv)
        session.commit()

        msg = Message(
            conversation_id=conv.id,
            role='user',
            content={'text': 'test'}
        )
        session.add(msg)

        agent = AgentConfig(
            agent_id='test-agent',
            name='Test Agent',
            total_calls=10,
            success_calls=8
        )
        session.add(agent)
        session.commit()
    finally:
        session.close()

    response = client.get(
        '/api/admin/dashboard/stats',
        headers=admin_auth_header
    )

    assert response.status_code == 200
    data = response.json()

    # 验证返回结构
    assert 'users' in data
    assert 'conversations' in data
    assert 'messages' in data
    assert 'agents' in data

    # 验证数据
    assert data['users']['total'] >= 1
    assert data['conversations']['total'] >= 1
    assert data['messages']['total'] >= 1
    assert data['agents']['total'] >= 1


def test_dashboard_activities_requires_admin(client, auth_header):
    """测试 dashboard activities 需要管理员权限"""
    response = client.get(
        '/api/admin/dashboard/activities',
        headers=auth_header
    )
    assert response.status_code == 403


def test_dashboard_activities_success(client, admin_auth_header):
    """测试 dashboard activities 成功返回"""
    # 创建最近的消息
    from tests.conftest import TestSessionLocal
    session = TestSessionLocal()
    try:
        user = session.query(User).filter_by(username='adminuser').first()
        assert user is not None

        conv = Conversation(user_id=user.id, title='Recent')
        session.add(conv)
        session.commit()

        msg = Message(
            conversation_id=conv.id,
            role='user',
            content={'text': 'recent message'},
            created_at=datetime.now(timezone.utc)
        )
        session.add(msg)
        session.commit()
    finally:
        session.close()

    response = client.get(
        '/api/admin/dashboard/activities',
        headers=admin_auth_header
    )

    assert response.status_code == 200
    data = response.json()

    # 验证返回结构
    assert 'recent_messages' in data
    assert 'recent_activities' in data

    # 验证数据格式
    assert isinstance(data['recent_messages'], list)
    assert len(data['recent_messages']) <= 10


def test_report_quality_insights_requires_admin(client, auth_header):
    """测试报告质量洞察需要管理员权限"""
    response = client.get(
        '/api/admin/dashboard/report-quality-insights',
        headers=auth_header
    )
    assert response.status_code == 403


def test_report_quality_insights_empty_success(client, admin_auth_header):
    """测试无评分时返回稳定空结构"""
    response = client.get(
        '/api/admin/dashboard/report-quality-insights',
        headers=admin_auth_header
    )

    assert response.status_code == 200
    data = response.json()

    assert data['period_days'] == 30
    assert data['summary']['total_ratings'] == 0
    assert data['summary']['positive_rate'] == 0.0
    assert data['summary']['negative_rate'] == 0.0
    assert data['problem_clusters'] == []
    assert data['recent_negative_comments'] == []
    assert {item['target_type'] for item in data['target_breakdown']} == {'agent_result', 'final_report'}


def test_report_quality_insights_aggregates_ratings_and_clusters(client, admin_auth_header):
    """测试报告质量洞察聚合评分、目标分布和差评问题聚类"""
    from tests.conftest import TestSessionLocal
    session = TestSessionLocal()
    try:
        user = session.query(User).filter_by(username='adminuser').first()
        assert user is not None

        conv = Conversation(user_id=user.id, title='Quality insights')
        session.add(conv)
        session.commit()

        leader_session = LeaderSession(
            conversation_id=conv.id,
            user_message='Analyze report quality',
            state='completed'
        )
        session.add(leader_session)
        session.commit()

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        ratings = [
            LeaderReportRating(
                target_type='agent_result',
                target_id=1,
                leader_session_id=leader_session.id,
                conversation_id=conv.id,
                user_id=user.id,
                rating=5,
                created_at=now - timedelta(days=1),
                updated_at=now - timedelta(days=1),
            ),
            LeaderReportRating(
                target_type='agent_result',
                target_id=2,
                leader_session_id=leader_session.id,
                conversation_id=conv.id,
                user_id=user.id,
                rating=1,
                comment='缺少来源，证据不够',
                created_at=now - timedelta(days=1),
                updated_at=now - timedelta(days=1),
            ),
            LeaderReportRating(
                target_type='final_report',
                target_id=3,
                leader_session_id=leader_session.id,
                conversation_id=conv.id,
                user_id=user.id,
                rating=1,
                comment='结论不清楚，建议不可执行',
                created_at=now - timedelta(hours=1),
                updated_at=now - timedelta(hours=1),
            ),
            LeaderReportRating(
                target_type='final_report',
                target_id=4,
                leader_session_id=leader_session.id,
                conversation_id=conv.id,
                user_id=user.id,
                rating=5,
                created_at=now - timedelta(days=120),
                updated_at=now - timedelta(days=120),
            ),
        ]
        session.add_all(ratings)
        session.commit()
    finally:
        session.close()

    response = client.get(
        '/api/admin/dashboard/report-quality-insights?period=30d',
        headers=admin_auth_header
    )

    assert response.status_code == 200
    data = response.json()

    assert data['summary']['total_ratings'] == 3
    assert data['summary']['positive_count'] == 1
    assert data['summary']['negative_count'] == 2
    assert data['summary']['positive_rate'] == 33.3
    assert data['summary']['negative_rate'] == 66.7

    breakdown = {item['target_type']: item for item in data['target_breakdown']}
    assert breakdown['agent_result']['total'] == 2
    assert breakdown['agent_result']['negative_count'] == 1
    assert breakdown['final_report']['total'] == 1
    assert breakdown['final_report']['negative_count'] == 1

    clusters = {item['key']: item for item in data['problem_clusters']}
    assert clusters['evidence_gap']['count'] == 1
    assert clusters['unclear_conclusion']['count'] == 1
    assert clusters['evidence_gap']['share'] == 50.0

    assert len(data['recent_negative_comments']) == 2
    assert data['recent_negative_comments'][0]['comment'] == '结论不清楚，建议不可执行'
    assert 'user_id' not in data['recent_negative_comments'][0]


def test_report_quality_insights_rejects_invalid_period(client, admin_auth_header):
    """测试 period 仅接受固定窗口"""
    response = client.get(
        '/api/admin/dashboard/report-quality-insights?period=365d',
        headers=admin_auth_header
    )
    assert response.status_code == 422
