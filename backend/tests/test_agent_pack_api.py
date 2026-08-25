"""Agent Pack API 测试

测试 Agent 组合包的 CRUD、克隆和权限控制。
"""
import pytest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import User, AgentConfig, AgentPack


# ==================== fixture ====================

@pytest.fixture
def sample_agents_for_pack(client, admin_auth_header):
    """创建测试用 Agent（用于 Pack 引用）"""
    from tests.conftest import TestSessionLocal
    session = TestSessionLocal()
    try:
        agents = []
        for aid, enabled in [
            ('pack-agent-a', True),
            ('pack-agent-b', True),
            ('pack-agent-c', False),  # 禁用
        ]:
            agent = AgentConfig(
                agent_id=aid,
                name=f'Agent {aid}',
                description=f'Test agent {aid}',
                model='inherit',
                is_enabled=enabled,
                file_exists=True,
            )
            session.add(agent)
            agents.append(aid)
        session.commit()
        return agents
    finally:
        session.close()


@pytest.fixture
def system_pack(client, sample_agents_for_pack):
    """创建系统预设 Pack"""
    from tests.conftest import TestSessionLocal
    session = TestSessionLocal()
    try:
        pack = AgentPack(
            name='系统测试包',
            description='系统预设测试',
            category='medical',
            is_system=True,
            creator_id=None,
            agents=[
                {'agent_id': 'pack-agent-a', 'role': '主分析', 'order': 1},
                {'agent_id': 'pack-agent-b', 'role': '辅助', 'order': 2},
            ],
            tags=['test'],
        )
        session.add(pack)
        session.commit()
        session.refresh(pack)
        return pack.id
    finally:
        session.close()


@pytest.fixture
def user_pack(client, sample_agents_for_pack, normal_user):
    """创建用户自建 Pack"""
    from tests.conftest import TestSessionLocal
    session = TestSessionLocal()
    try:
        pack = AgentPack(
            name='用户测试包',
            description='用户自建测试',
            category='custom',
            is_system=False,
            creator_id=normal_user['id'],
            agents=[{'agent_id': 'pack-agent-a', 'role': '分析', 'order': 1}],
            tags=['my'],
        )
        session.add(pack)
        session.commit()
        session.refresh(pack)
        return pack.id
    finally:
        session.close()


@pytest.fixture
def other_user_pack(client, sample_agents_for_pack, other_user):
    """创建其他用户的 Pack"""
    from tests.conftest import TestSessionLocal
    session = TestSessionLocal()
    try:
        pack = AgentPack(
            name='别人的包',
            description='其他用户',
            category='custom',
            is_system=False,
            creator_id=other_user['id'],
            agents=[{'agent_id': 'pack-agent-a', 'role': '分析', 'order': 1}],
        )
        session.add(pack)
        session.commit()
        session.refresh(pack)
        return pack.id
    finally:
        session.close()


@pytest.fixture
def normal_user(client, auth_header):
    """获取普通用户信息"""
    resp = client.get('/api/auth/me', headers=auth_header)
    data = resp.json()
    return {'id': data['id'], 'username': data['username']}


@pytest.fixture
def other_user(client):
    """创建另一个普通用户"""
    from tests.conftest import TestSessionLocal
    session = TestSessionLocal()
    try:
        user = User(username='other_pack_user', email='other_pack@test.com', is_admin=False)
        user.set_password('Test1234!')
        session.add(user)
        session.commit()
        session.refresh(user)
        return {'id': user.id, 'username': user.username}
    finally:
        session.close()


# ==================== 创建 ====================

def test_create_pack(client, auth_header, sample_agents_for_pack):
    """c1: 创建 User Pack → 201, is_system=False"""
    resp = client.post('/api/agent-packs', headers=auth_header, json={
        'name': '我的测试包',
        'category': 'custom',
        'agents': [
            {'agent_id': 'pack-agent-a', 'role': '分析', 'order': 1},
            {'agent_id': 'pack-agent-b', 'role': '辅助', 'order': 2},
        ],
        'tags': ['test'],
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data['name'] == '我的测试包'
    assert data['is_system'] is False
    assert data['creator_id'] is not None
    assert len(data['agents']) == 2


def test_create_pack_empty_agents(client, auth_header):
    """c8: agents 为空 → 422"""
    resp = client.post('/api/agent-packs', headers=auth_header, json={
        'name': '空包',
        'agents': [],
    })
    assert resp.status_code == 422


def test_create_pack_too_many_agents(client, auth_header, sample_agents_for_pack):
    """c9: agents 超过 10 个 → 422"""
    agents = [{'agent_id': 'pack-agent-a', 'order': i} for i in range(1, 12)]
    resp = client.post('/api/agent-packs', headers=auth_header, json={
        'name': '大包',
        'agents': agents,
    })
    assert resp.status_code == 422


def test_create_pack_invalid_agent(client, auth_header):
    """c10: 引用不存在的 agent_id → 400"""
    resp = client.post('/api/agent-packs', headers=auth_header, json={
        'name': '无效引用',
        'agents': [{'agent_id': '不存在的agent', 'order': 1}],
    })
    assert resp.status_code == 400
    assert 'invalid_agents' in resp.json()['detail']


def test_create_pack_disabled_agent(client, auth_header, sample_agents_for_pack):
    """c11: 引用已禁用 Agent → 400"""
    resp = client.post('/api/agent-packs', headers=auth_header, json={
        'name': '禁用引用',
        'agents': [{'agent_id': 'pack-agent-c', 'order': 1}],
    })
    assert resp.status_code == 400
    assert 'pack-agent-c' in resp.json()['detail']['invalid_agents']


# ==================== 列表 ====================

def test_list_packs(client, auth_header, system_pack, user_pack):
    """c2: 列表查询返回系统预设 + 用户自建"""
    resp = client.get('/api/agent-packs', headers=auth_header)
    assert resp.status_code == 200
    data = resp.json()
    assert data['total'] >= 2
    ids = [p['id'] for p in data['items']]
    assert system_pack in ids
    assert user_pack in ids


def test_list_packs_filter_category(client, auth_header, system_pack, user_pack):
    """c3: 按 category 筛选"""
    resp = client.get('/api/agent-packs?category=medical', headers=auth_header)
    assert resp.status_code == 200
    for p in resp.json()['items']:
        assert p['category'] == 'medical'


# ==================== 更新 ====================

def test_update_own_pack(client, auth_header, user_pack):
    """c5: 更新自己的 Pack → 200"""
    resp = client.put(f'/api/agent-packs/{user_pack}', headers=auth_header, json={
        'name': '改名后的包',
    })
    assert resp.status_code == 200
    assert resp.json()['name'] == '改名后的包'


def test_update_system_pack_forbidden(client, auth_header, system_pack):
    """c13: 修改系统 Pack → 403"""
    resp = client.put(f'/api/agent-packs/{system_pack}', headers=auth_header, json={
        'name': '尝试改名',
    })
    assert resp.status_code == 403


def test_update_other_user_pack_forbidden(client, auth_header, other_user_pack):
    """c15: 修改别人的 Pack → 403"""
    resp = client.put(f'/api/agent-packs/{other_user_pack}', headers=auth_header, json={
        'name': '尝试改名',
    })
    assert resp.status_code == 403


# ==================== 删除 ====================

def test_delete_own_pack(client, auth_header, user_pack):
    """c6: 删除自己的 Pack → 204"""
    resp = client.delete(f'/api/agent-packs/{user_pack}', headers=auth_header)
    assert resp.status_code == 204


def test_delete_system_pack_forbidden(client, auth_header, system_pack):
    """c14: 删除系统 Pack → 403"""
    resp = client.delete(f'/api/agent-packs/{system_pack}', headers=auth_header)
    assert resp.status_code == 403


def test_delete_other_user_pack_forbidden(client, auth_header, other_user_pack):
    """c16: 删除别人的 Pack → 403"""
    resp = client.delete(f'/api/agent-packs/{other_user_pack}', headers=auth_header)
    assert resp.status_code == 403


# ==================== 克隆 ====================

def test_clone_system_pack(client, auth_header, system_pack):
    """c4: 克隆系统 Pack → 201, is_system=False, name 带后缀"""
    resp = client.post(f'/api/agent-packs/{system_pack}/clone', headers=auth_header)
    assert resp.status_code == 201
    data = resp.json()
    assert data['is_system'] is False
    assert '副本' in data['name']
    assert data['creator_id'] is not None


def test_clone_other_user_pack_forbidden(client, auth_header, other_user_pack):
    """c12: 克隆别人的 User Pack → 403"""
    resp = client.post(f'/api/agent-packs/{other_user_pack}/clone', headers=auth_header)
    assert resp.status_code == 403


def test_clone_nonexistent_pack(client, auth_header):
    """克隆不存在的 Pack → 404"""
    resp = client.post('/api/agent-packs/99999/clone', headers=auth_header)
    assert resp.status_code == 404


# ==================== 详情 ====================

def test_get_pack(client, auth_header, system_pack):
    """获取 Pack 详情"""
    resp = client.get(f'/api/agent-packs/{system_pack}', headers=auth_header)
    assert resp.status_code == 200
    assert resp.json()['id'] == system_pack


def test_get_nonexistent_pack(client, auth_header):
    """获取不存在的 Pack → 404"""
    resp = client.get('/api/agent-packs/99999', headers=auth_header)
    assert resp.status_code == 404


# ==================== 反向核对 ====================

def test_agents_field_has_no_nested_pack(client, auth_header, sample_agents_for_pack):
    """c18: agents 字段中不存在 pack_id 引用"""
    resp = client.post('/api/agent-packs', headers=auth_header, json={
        'name': '结构核对',
        'agents': [{'agent_id': 'pack-agent-a', 'order': 1}],
    })
    assert resp.status_code == 201
    agents = resp.json()['agents']
    for a in agents:
        assert 'pack_id' not in a
        assert 'agent_id' in a
