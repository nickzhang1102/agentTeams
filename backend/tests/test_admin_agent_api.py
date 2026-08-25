"""Admin Agent API 测试（FastAPI TestClient）

测试管理员Agent管理功能：
- Agent列表（筛选、搜索、分页）
- Agent详情
- Agent创建、更新、删除
- Agent启停切换
- Agent文件同步
- 权限控制

迁移自 Flask test_client，使用 conftest 提供的 fixture。
"""
import pytest
import json
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import User, AgentConfig
from db import Base


# ==================== 测试数据 fixture ====================

@pytest.fixture
def sample_agents(client, admin_auth_header):
    """创建测试用 Agent 数据（通过独立 Session）"""
    from tests.conftest import TestSessionLocal
    session = TestSessionLocal()
    try:
        agents = []
        for i, (aid, name, desc) in enumerate([
            ('cardiology-expert', '心血管内科专家', '诊断心血管疾病'),
            ('respiratory-expert', '呼吸内科专家', '诊断呼吸系统疾病'),
            ('surgery-expert', '外科专家', '外科手术咨询'),
        ]):
            agent = AgentConfig(
                agent_id=aid,
                name=name,
                description=desc,
                model='inherit',
                is_enabled=(i != 2),  # 第3个禁用
                is_system=False,      # 用户创建的 Agent，允许修改/删除
                file_exists=True,
                total_calls=10 * (i + 1),
                success_calls=8 * (i + 1),
                failed_calls=2 * (i + 1),
            )
            session.add(agent)
            agents.append(agent)
        session.commit()
        return [a.agent_id for a in agents]
    finally:
        session.close()


# ==================== 权限控制测试 ====================

def test_list_agents_requires_admin(client, auth_header):
    """测试Agent列表需要管理员权限"""
    response = client.get('/api/admin/agents', headers=auth_header)
    assert response.status_code == 403


def test_get_agent_requires_admin(client, auth_header):
    """测试Agent详情需要管理员权限"""
    response = client.get('/api/admin/agents/test-agent', headers=auth_header)
    assert response.status_code == 403


def test_create_agent_requires_admin(client, auth_header):
    """测试创建Agent需要管理员权限"""
    response = client.post('/api/admin/agents',
        headers=auth_header,
        json={'agent_id': 'new', 'name': 'New'}
    )
    assert response.status_code == 403


def test_update_agent_requires_admin(client, auth_header):
    """测试更新Agent需要管理员权限"""
    response = client.put('/api/admin/agents/test-agent',
        headers=auth_header,
        json={'name': 'Updated'}
    )
    assert response.status_code == 403


def test_delete_agent_requires_admin(client, auth_header):
    """测试删除Agent需要管理员权限"""
    response = client.delete('/api/admin/agents/test-agent', headers=auth_header)
    assert response.status_code == 403


def test_toggle_agent_requires_admin(client, auth_header):
    """测试切换Agent需要管理员权限"""
    response = client.post('/api/admin/agents/test-agent/toggle', headers=auth_header)
    assert response.status_code == 403


def test_sync_agents_requires_admin(client, auth_header):
    """测试同步Agent需要管理员权限"""
    response = client.post('/api/admin/agents/sync', headers=auth_header)
    assert response.status_code == 403


# ==================== Agent列表测试 ====================

def test_list_agents_success(client, admin_auth_header, sample_agents):
    """测试获取Agent列表成功"""
    response = client.get('/api/admin/agents', headers=admin_auth_header)
    assert response.status_code == 200
    data = response.json()
    assert 'agents' in data
    assert 'total' in data
    assert 'page' in data
    assert 'per_page' in data
    assert 'pages' in data
    assert data['total'] == 3
    assert len(data['agents']) == 3


def test_list_agents_filter_enabled(client, admin_auth_header, sample_agents):
    """测试按启用状态筛选Agent"""
    response = client.get('/api/admin/agents?is_enabled=true', headers=admin_auth_header)
    assert response.status_code == 200
    data = response.json()
    assert data['total'] == 2
    for agent in data['agents']:
        assert agent['is_enabled'] is True


def test_list_agents_search(client, admin_auth_header, sample_agents):
    """测试关键词搜索Agent"""
    response = client.get('/api/admin/agents?search=心血管', headers=admin_auth_header)
    assert response.status_code == 200
    data = response.json()
    assert data['total'] == 1
    assert data['agents'][0]['agent_id'] == 'cardiology-expert'


def test_list_agents_pagination(client, admin_auth_header, sample_agents):
    """测试Agent列表分页"""
    response = client.get('/api/admin/agents?per_page=2&page=1', headers=admin_auth_header)
    assert response.status_code == 200
    data = response.json()
    assert len(data['agents']) == 2
    assert data['pages'] == 2

    # 第二页
    response2 = client.get('/api/admin/agents?per_page=2&page=2', headers=admin_auth_header)
    assert response2.status_code == 200
    assert len(response2.json()['agents']) == 1


# ==================== Agent详情测试 ====================

def test_get_agent_success(client, admin_auth_header, sample_agents):
    """测试获取Agent详情成功"""
    response = client.get('/api/admin/agents/cardiology-expert', headers=admin_auth_header)
    assert response.status_code == 200
    data = response.json()
    assert 'agent' in data
    agent = data['agent']
    assert agent['agent_id'] == 'cardiology-expert'
    assert agent['name'] == '心血管内科专家'
    assert agent['total_calls'] == 10
    assert agent['success_calls'] == 8


def test_get_agent_not_found(client, admin_auth_header):
    """测试获取不存在的Agent"""
    response = client.get('/api/admin/agents/non-existent', headers=admin_auth_header)
    assert response.status_code == 404


def test_get_agent_invalid_id(client, admin_auth_header):
    """测试获取格式非法的agent_id"""
    response = client.get('/api/admin/agents/invalid.agent.id', headers=admin_auth_header)
    assert response.status_code == 400


# ==================== Agent创建测试 ====================

def test_create_agent_success(client, admin_auth_header):
    """测试创建Agent成功"""
    # 清理可能残留的测试数据（DB + 文件）
    from tests.conftest import TestSessionLocal
    from api.admin.admin_helpers import get_file_manager
    session = TestSessionLocal()
    try:
        session.query(AgentConfig).filter_by(agent_id='test-new-agent').delete()
        session.commit()
    finally:
        session.close()

    # 清理残留文件（file manager 解析路径可能与 Config.AGENTS_DIR 不同）
    fm = get_file_manager()
    agent_file = fm.agents_dir / 'test-new-agent.md'
    if agent_file.exists():
        agent_file.unlink()

    payload = {
        'agent_id': 'test-new-agent',
        'name': '测试Agent',
        'description': '用于测试的Agent',
        'model': 'inherit',
        'content': '# 测试Agent\n\n## Role\n测试角色'
    }
    response = client.post('/api/admin/agents',
        headers=admin_auth_header,
        json=payload
    )
    assert response.status_code == 201
    data = response.json()
    assert 'agent' in data
    assert data['agent']['agent_id'] == 'test-new-agent'
    assert data['agent']['name'] == '测试Agent'
    assert data['agent']['is_enabled'] is True

    # 验证数据库记录
    session = TestSessionLocal()
    try:
        agent = session.query(AgentConfig).filter_by(agent_id='test-new-agent').first()
        assert agent is not None
        assert agent.name == '测试Agent'
    finally:
        session.close()


def test_create_agent_missing_fields(client, admin_auth_header):
    """测试创建Agent缺少必填字段（FastAPI Pydantic 校验返回 422）"""
    response = client.post('/api/admin/agents',
        headers=admin_auth_header,
        json={'description': '无agent_id'}
    )
    assert response.status_code == 422

    response2 = client.post('/api/admin/agents',
        headers=admin_auth_header,
        json={'agent_id': 'test-no-name'}
    )
    assert response2.status_code == 422


def test_create_agent_invalid_id(client, admin_auth_header):
    """测试创建格式非法的agent_id"""
    response = client.post('/api/admin/agents',
        headers=admin_auth_header,
        json={'agent_id': 'bad.agent', 'name': 'Bad'}
    )
    assert response.status_code == 400


def test_create_agent_duplicate(client, admin_auth_header, sample_agents):
    """测试创建重复Agent"""
    response = client.post('/api/admin/agents',
        headers=admin_auth_header,
        json={'agent_id': 'cardiology-expert', 'name': '重复'}
    )
    assert response.status_code == 409


# ==================== Agent更新测试 ====================

def test_update_agent_success(client, admin_auth_header, sample_agents):
    """测试更新Agent成功"""
    response = client.put('/api/admin/agents/cardiology-expert',
        headers=admin_auth_header,
        json={'name': '更新后名称', 'description': '更新后描述'}
    )
    assert response.status_code == 200
    data = response.json()
    assert data['agent']['name'] == '更新后名称'
    assert data['agent']['description'] == '更新后描述'

    # 验证数据库
    from tests.conftest import TestSessionLocal
    session = TestSessionLocal()
    try:
        agent = session.query(AgentConfig).filter_by(agent_id='cardiology-expert').first()
        assert agent.name == '更新后名称'
    finally:
        session.close()


def test_update_agent_not_found(client, admin_auth_header):
    """测试更新不存在的Agent"""
    response = client.put('/api/admin/agents/non-existent',
        headers=admin_auth_header,
        json={'name': '不存在的'}
    )
    assert response.status_code == 404


# ==================== Agent删除测试 ====================

def test_delete_agent_soft(client, admin_auth_header, sample_agents):
    """测试软删除Agent"""
    response = client.delete('/api/admin/agents/cardiology-expert?soft=true',
                             headers=admin_auth_header)
    assert response.status_code == 200

    # 验证数据库记录仍在，但已禁用
    from tests.conftest import TestSessionLocal
    session = TestSessionLocal()
    try:
        agent = session.query(AgentConfig).filter_by(agent_id='cardiology-expert').first()
        assert agent is not None
        assert agent.is_enabled is False
        assert agent.file_exists is False
    finally:
        session.close()


def test_delete_agent_hard(client, admin_auth_header, sample_agents):
    """测试硬删除Agent"""
    response = client.delete('/api/admin/agents/cardiology-expert?soft=false',
                             headers=admin_auth_header)
    assert response.status_code == 200

    # 验证数据库记录已删除
    from tests.conftest import TestSessionLocal
    session = TestSessionLocal()
    try:
        agent = session.query(AgentConfig).filter_by(agent_id='cardiology-expert').first()
        assert agent is None
    finally:
        session.close()


def test_delete_agent_not_found(client, admin_auth_header):
    """测试删除不存在的Agent"""
    response = client.delete('/api/admin/agents/non-existent', headers=admin_auth_header)
    assert response.status_code == 404


# ==================== Agent切换测试 ====================

def test_toggle_agent_enable(client, admin_auth_header, sample_agents):
    """测试切换禁用Agent为启用"""
    # surgery-expert 初始为禁用
    response = client.post('/api/admin/agents/surgery-expert/toggle',
                           headers=admin_auth_header)
    assert response.status_code == 200
    data = response.json()
    assert data['agent']['is_enabled'] is True

    # 验证数据库
    from tests.conftest import TestSessionLocal
    session = TestSessionLocal()
    try:
        agent = session.query(AgentConfig).filter_by(agent_id='surgery-expert').first()
        assert agent.is_enabled is True
    finally:
        session.close()


def test_toggle_agent_disable(client, admin_auth_header, sample_agents):
    """测试切换启用Agent为禁用"""
    # cardiology-expert 初始为启用
    response = client.post('/api/admin/agents/cardiology-expert/toggle',
                           headers=admin_auth_header)
    assert response.status_code == 200
    data = response.json()
    assert data['agent']['is_enabled'] is False


def test_toggle_agent_not_found(client, admin_auth_header):
    """测试切换不存在的Agent"""
    response = client.post('/api/admin/agents/non-existent/toggle',
                           headers=admin_auth_header)
    assert response.status_code == 404


# ==================== Agent同步测试 ====================

def test_sync_agents_success(client, admin_auth_header):
    """测试同步Agent成功"""
    response = client.post('/api/admin/agents/sync', headers=admin_auth_header)
    assert response.status_code == 200
    data = response.json()
    assert 'synced' in data
    assert 'created' in data
    assert 'updated' in data
    assert 'removed' in data


def test_sync_agents_with_files(client, admin_auth_header):
    """测试同步包含文件的Agent目录"""
    # 使用 file manager 的 agents_dir（与 Config.AGENTS_DIR 可能不同）
    from api.admin.admin_helpers import get_file_manager
    fm = get_file_manager()
    agents_dir = fm.agents_dir
    if not agents_dir.exists():
        pytest.skip("agents_dir 不存在")

    os.makedirs(agents_dir, exist_ok=True)
    test_file = agents_dir / 'sync-test-agent.md'
    try:
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write('---\nname: sync-test-agent\ndescription: "同步测试Agent"\nmodel: inherit\n---\n\n# 同步测试Agent\n\n## Role\n测试')

        response = client.post('/api/admin/agents/sync', headers=admin_auth_header)
        assert response.status_code == 200
        data = response.json()
        assert data['created'] >= 1

        # 验证数据库记录
        from tests.conftest import TestSessionLocal
        session = TestSessionLocal()
        try:
            agent = session.query(AgentConfig).filter_by(agent_id='sync-test-agent').first()
            assert agent is not None
            assert agent.file_exists is True
        finally:
            session.close()
    finally:
        # 清理测试文件
        if test_file.exists():
            test_file.unlink()
