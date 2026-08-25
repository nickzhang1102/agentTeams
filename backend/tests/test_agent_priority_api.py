"""Agent Priority API 测试

测试 PATCH /api/agents/priority 端点的权限、校验和批量更新逻辑。
"""
import pytest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import User, AgentConfig


# ==================== fixture ====================

@pytest.fixture
def normal_user(client, auth_header):
    """获取普通用户信息"""
    resp = client.get('/api/auth/me', headers=auth_header)
    data = resp.json()
    return {'id': data['id'], 'username': data['username']}


@pytest.fixture
def system_agents(client, admin_auth_header):
    """创建系统 Agent"""
    from tests.conftest import TestSessionLocal
    session = TestSessionLocal()
    try:
        agents = []
        for aid, pri in [('sys-agent-a', 50), ('sys-agent-b', 50), ('sys-agent-c', 50)]:
            agent = AgentConfig(
                agent_id=aid,
                name=f'System {aid}',
                description='test',
                model='inherit',
                is_system=True,
                is_enabled=True,
                priority=pri,
            )
            session.add(agent)
            agents.append(aid)
        session.commit()
        return agents
    finally:
        session.close()


@pytest.fixture
def user_agents(client, auth_header, normal_user):
    """创建普通用户的自建 Agent"""
    from tests.conftest import TestSessionLocal
    session = TestSessionLocal()
    try:
        agents = []
        for aid, pri in [('user-agent-a', 50), ('user-agent-b', 50)]:
            agent = AgentConfig(
                agent_id=aid,
                name=f'User {aid}',
                description='test',
                model='inherit',
                source='db',
                is_system=False,
                created_by=normal_user['id'],
                is_enabled=True,
                priority=pri,
            )
            session.add(agent)
            agents.append(aid)
        session.commit()
        return agents
    finally:
        session.close()


# ==================== 正常更新 ====================

class TestPriorityUpdateNormal:
    """正常批量更新场景"""

    def test_admin_update_system_agents(self, client, admin_auth_header, system_agents):
        """admin 可以更新系统 agent 的 priority"""
        resp = client.patch('/api/agents/priority', json={
            'items': [
                {'agent_id': 'sys-agent-a', 'priority': 10},
                {'agent_id': 'sys-agent-b', 'priority': 20},
            ]
        }, headers=admin_auth_header)
        assert resp.status_code == 200
        assert resp.json()['updated'] == 2

    def test_admin_update_user_agents(self, client, admin_auth_header, user_agents):
        """admin 可以更新用户自建 agent 的 priority"""
        resp = client.patch('/api/agents/priority', json={
            'items': [{'agent_id': 'user-agent-a', 'priority': 30}]
        }, headers=admin_auth_header)
        assert resp.status_code == 200
        assert resp.json()['updated'] == 1

    def test_user_update_own_agents(self, client, auth_header, user_agents):
        """普通用户可以更新自己创建的 agent"""
        resp = client.patch('/api/agents/priority', json={
            'items': [
                {'agent_id': 'user-agent-a', 'priority': 10},
                {'agent_id': 'user-agent-b', 'priority': 40},
            ]
        }, headers=auth_header)
        assert resp.status_code == 200
        assert resp.json()['updated'] == 2

    def test_update_skips_unchanged(self, client, admin_auth_header, system_agents):
        """priority 未变的 agent 不计入 updated"""
        # sys-agent-c 的初始 priority 是 50
        resp = client.patch('/api/agents/priority', json={
            'items': [
                {'agent_id': 'sys-agent-a', 'priority': 10},  # changed
                {'agent_id': 'sys-agent-c', 'priority': 50},  # unchanged
            ]
        }, headers=admin_auth_header)
        assert resp.status_code == 200
        assert resp.json()['updated'] == 1

    def test_update_persists(self, client, admin_auth_header, system_agents):
        """更新后重新查询应返回新 priority"""
        client.patch('/api/agents/priority', json={
            'items': [{'agent_id': 'sys-agent-a', 'priority': 10}]
        }, headers=admin_auth_header)

        from tests.conftest import TestSessionLocal
        session = TestSessionLocal()
        try:
            agent = session.query(AgentConfig).filter_by(agent_id='sys-agent-a').first()
            assert agent.priority == 10
        finally:
            session.close()


# ==================== 权限拦截 ====================

class TestPriorityPermission:
    """权限控制场景"""

    def test_user_cannot_update_system_agent(self, client, auth_header, system_agents):
        """普通用户不能更新系统 agent"""
        resp = client.patch('/api/agents/priority', json={
            'items': [{'agent_id': 'sys-agent-a', 'priority': 10}]
        }, headers=auth_header)
        assert resp.status_code == 403
        assert '自建' in resp.json()['detail']

    def test_user_cannot_update_others_agent(self, client, another_user_auth_header, user_agents):
        """普通用户不能更新别人创建的 agent"""
        resp = client.patch('/api/agents/priority', json={
            'items': [{'agent_id': 'user-agent-a', 'priority': 10}]
        }, headers=another_user_auth_header)
        assert resp.status_code == 403

    def test_unauthenticated_request_rejected(self, client, system_agents):
        """未认证请求返回 401"""
        resp = client.patch('/api/agents/priority', json={
            'items': [{'agent_id': 'sys-agent-a', 'priority': 10}]
        })
        assert resp.status_code == 401


# ==================== 输入校验 ====================

class TestPriorityValidation:
    """输入校验场景"""

    def test_empty_items_rejected(self, client, admin_auth_header):
        """空 items 列表应返回 422"""
        resp = client.patch('/api/agents/priority', json={
            'items': []
        }, headers=admin_auth_header)
        assert resp.status_code == 422

    def test_over_100_items_rejected(self, client, admin_auth_header):
        """超过 100 条应返回 422"""
        items = [{'agent_id': f'agent-{i}', 'priority': 10} for i in range(101)]
        resp = client.patch('/api/agents/priority', json={
            'items': items
        }, headers=admin_auth_header)
        assert resp.status_code == 422

    def test_priority_out_of_range_rejected(self, client, admin_auth_header):
        """priority 超出 0-100 应返回 422"""
        resp = client.patch('/api/agents/priority', json={
            'items': [{'agent_id': 'some-agent', 'priority': 150}]
        }, headers=admin_auth_header)
        assert resp.status_code == 422

    def test_negative_priority_rejected(self, client, admin_auth_header):
        """负 priority 应返回 422"""
        resp = client.patch('/api/agents/priority', json={
            'items': [{'agent_id': 'some-agent', 'priority': -1}]
        }, headers=admin_auth_header)
        assert resp.status_code == 422

    def test_missing_agent_id_rejected(self, client, admin_auth_header):
        """缺少 agent_id 应返回 422"""
        resp = client.patch('/api/agents/priority', json={
            'items': [{'priority': 10}]
        }, headers=admin_auth_header)
        assert resp.status_code == 422

    def test_nonexistent_agent_silent_skip(self, client, admin_auth_header):
        """不存在的 agent_id 静默跳过，不报错"""
        resp = client.patch('/api/agents/priority', json={
            'items': [{'agent_id': 'nonexistent-agent', 'priority': 10}]
        }, headers=admin_auth_header)
        assert resp.status_code == 200
        assert resp.json()['updated'] == 0
