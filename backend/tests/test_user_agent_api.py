"""用户端 Agent CRUD 测试

测试 /api/user/agents 端点的创建、更新、删除及权限控制。
"""
import pytest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['SKIP_MCP_INIT'] = 'true'

from tests.conftest import TestSessionLocal
from models import User, AgentConfig


# ==================== fixture ====================

@pytest.fixture
def created_agent(client, auth_header):
    """通过 API 创建一个用户 Agent，返回其 agent_id"""
    resp = client.post('/api/user/agents', headers=auth_header, json={
        'agent_id': 'my-custom-agent',
        'name': '我的自建 Agent',
        'description': '测试用',
        'content': '你是一个测试助手。',
        'tags': ['test'],
    })
    assert resp.status_code == 201
    return resp.json()['agent']['agent_id']


@pytest.fixture
def other_user_agent(client, another_user_auth_header):
    """另一个用户创建的 Agent"""
    resp = client.post('/api/user/agents', headers=another_user_auth_header, json={
        'agent_id': 'other-user-agent',
        'name': '别人的 Agent',
        'content': '别人写的 prompt。',
    })
    assert resp.status_code == 201
    return resp.json()['agent']['agent_id']


@pytest.fixture
def system_agent(client):
    """在 DB 中插入一条系统 Agent（is_system=True, is_enabled=True）"""
    session = TestSessionLocal()
    try:
        agent = AgentConfig(
            agent_id='system-agent-test',
            name='系统 Agent',
            description='系统内置',
            model='inherit',
            is_system=True,
            is_enabled=True,
            file_exists=True,
        )
        session.add(agent)
        session.commit()
        return 'system-agent-test'
    finally:
        session.close()


# ==================== POST 创建 ====================

def test_create_agent_success(client, auth_header):
    """成功创建自建 Agent → 201"""
    resp = client.post('/api/user/agents', headers=auth_header, json={
        'agent_id': 'new-agent-01',
        'name': '新建 Agent',
        'content': 'System prompt content.',
    })
    assert resp.status_code == 201
    data = resp.json()['agent']
    assert data['agent_id'] == 'new-agent-01'
    assert data['is_system'] is False
    assert data['is_enabled'] is False  # 用户创建默认未启用
    assert data['source'] == 'db'


def test_create_agent_missing_required_fields(client, auth_header):
    """缺少必填字段 → 422"""
    # 缺少 content
    resp = client.post('/api/user/agents', headers=auth_header, json={
        'agent_id': 'no-content-agent',
        'name': '缺 content',
    })
    assert resp.status_code == 422

    # 缺少 agent_id
    resp = client.post('/api/user/agents', headers=auth_header, json={
        'name': '缺 id',
        'content': 'some content',
    })
    assert resp.status_code == 422

    # 缺少 name
    resp = client.post('/api/user/agents', headers=auth_header, json={
        'agent_id': 'no-name-agent',
        'content': 'some content',
    })
    assert resp.status_code == 422


def test_create_agent_invalid_agent_id_format(client, auth_header):
    """agent_id 含特殊字符 → 422（Pydantic pattern 校验）"""
    resp = client.post('/api/user/agents', headers=auth_header, json={
        'agent_id': 'bad@id!',
        'name': '格式错误',
        'content': 'test',
    })
    assert resp.status_code == 422


def test_create_agent_invalid_portrait_url(client, auth_header):
    """portrait_url 非 http/https → 422"""
    resp = client.post('/api/user/agents', headers=auth_header, json={
        'agent_id': 'bad-portrait',
        'name': '头像 URL 非法',
        'content': 'test',
        'portrait_url': 'ftp://example.com/img.png',
    })
    assert resp.status_code == 422

    # javascript: 协议
    resp = client.post('/api/user/agents', headers=auth_header, json={
        'agent_id': 'bad-portrait-2',
        'name': '头像 URL 非法2',
        'content': 'test',
        'portrait_url': 'javascript:alert(1)',
    })
    assert resp.status_code == 422


def test_create_agent_unauthenticated(client):
    """未认证 → 401"""
    resp = client.post('/api/user/agents', json={
        'agent_id': 'anon-agent',
        'name': '匿名',
        'content': 'test',
    })
    assert resp.status_code == 401


def test_create_agent_duplicate_id(client, auth_header, created_agent):
    """agent_id 重复 → 409"""
    resp = client.post('/api/user/agents', headers=auth_header, json={
        'agent_id': created_agent,
        'name': '重复 ID',
        'content': 'duplicate',
    })
    assert resp.status_code == 409


# ==================== PUT 更新 ====================

def test_update_own_agent(client, auth_header, created_agent):
    """成功更新自己的 Agent → 200"""
    resp = client.put(f'/api/user/agents/{created_agent}', headers=auth_header, json={
        'name': '改名后的 Agent',
        'description': '新描述',
    })
    assert resp.status_code == 200
    data = resp.json()['agent']
    assert data['name'] == '改名后的 Agent'
    assert data['description'] == '新描述'


def test_update_other_user_agent_forbidden(client, auth_header, other_user_agent):
    """更新他人 Agent → 403"""
    resp = client.put(f'/api/user/agents/{other_user_agent}', headers=auth_header, json={
        'name': '尝试改名',
    })
    assert resp.status_code == 403


def test_update_nonexistent_agent(client, auth_header):
    """更新不存在的 Agent → 404"""
    resp = client.put('/api/user/agents/nonexistent-id', headers=auth_header, json={
        'name': '不存在',
    })
    assert resp.status_code == 404


# ==================== DELETE 删除 ====================

def test_delete_own_agent(client, auth_header, created_agent):
    """成功删除自己的 Agent → 200"""
    resp = client.delete(f'/api/user/agents/{created_agent}', headers=auth_header)
    assert resp.status_code == 200
    assert 'deleted' in resp.json()['message'].lower()


def test_delete_other_user_agent_forbidden(client, auth_header, other_user_agent):
    """删除他人 Agent → 403"""
    resp = client.delete(f'/api/user/agents/{other_user_agent}', headers=auth_header)
    assert resp.status_code == 403


def test_delete_system_agent_forbidden(client, auth_header, system_agent):
    """删除系统 Agent（is_system=True）→ 403

    注意：API 仅校验 created_by != user.id，
    系统 Agent 无 creator，必然触发 403。
    """
    resp = client.delete(f'/api/user/agents/{system_agent}', headers=auth_header)
    assert resp.status_code == 403
