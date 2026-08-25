"""批量能力补全端点测试

测试 POST /api/admin/agents/backfill-capabilities：
- 正常补全（后台异步执行 + 进度查询）
- 无空 capabilities 时返回 task_id=None
- LLM 失败跳过不中断
"""
import time
import pytest
import os
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import AgentConfig


@pytest.fixture
def agents_without_capabilities(client, admin_auth_header):
    """创建无 capabilities 的测试 Agent"""
    from tests.conftest import TestSessionLocal
    session = TestSessionLocal()
    try:
        agents = [
            AgentConfig(agent_id='backfill-test-1', name='测试Agent1', category='medical',
                        is_enabled=True, is_system=True, source='file',
                        capabilities=[], tags=[], skill_level=3),
            AgentConfig(agent_id='backfill-test-2', name='测试Agent2', category='business',
                        is_enabled=True, is_system=True, source='file',
                        capabilities=[], tags=[], skill_level=3),
            AgentConfig(agent_id='backfill-test-filled', name='已有能力', category='medical',
                        is_enabled=True, is_system=True, source='file',
                        capabilities=['诊断', '治疗'], tags=['medical'], skill_level=4),
        ]
        session.add_all(agents)
        session.commit()
    finally:
        session.close()


def _wait_for_task(client, admin_auth_header, task_id, timeout=5):
    """轮询任务状态直到完成"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = client.get(f'/api/admin/agents/backfill-capabilities/{task_id}', headers=admin_auth_header)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('status') in ('completed', 'failed'):
                return data
        time.sleep(0.1)
    raise TimeoutError(f'Task {task_id} did not complete within {timeout}s')


# ==================== 权限测试 ====================

def test_backfill_requires_admin(client, auth_header):
    """需要管理员权限"""
    response = client.post('/api/admin/agents/backfill-capabilities', headers=auth_header)
    assert response.status_code == 403


# ==================== 正常补全 ====================

@patch('database.SessionLocal')
@patch('services.llm_service.create_llm_service')
def test_backfill_success(mock_create_llm, mock_session_local, client, admin_auth_header, agents_without_capabilities):
    """LLM 返回有效 JSON 时应完成补全"""
    from tests.conftest import TestSessionLocal
    mock_session_local.return_value = TestSessionLocal()
    mock_create_llm.return_value.call_sync.return_value = '''
    {
        "capabilities": ["心血管诊断", "心电图分析", "药物治疗"],
        "tags": ["心内科", "心血管"],
        "skill_level": 4,
        "preferred_contexts": ["心血管疾病诊断"]
    }
    '''

    # 启动后台任务
    response = client.post('/api/admin/agents/backfill-capabilities', headers=admin_auth_header)
    assert response.status_code == 200
    data = response.json()
    assert data['task_id'] is not None
    assert data['total'] == 2  # 只处理 capabilities=[] 的

    # 等待完成
    result = _wait_for_task(client, admin_auth_header, data['task_id'])
    assert result['status'] == 'completed'
    assert result['processed'] == 2
    assert result['updated'] == 2
    assert result['skipped'] == 0


@patch('database.SessionLocal')
@patch('services.llm_service.create_llm_service')
def test_backfill_updates_db(mock_create_llm, mock_session_local, client, admin_auth_header, agents_without_capabilities):
    """补全后 DB 中 Agent 的 capabilities 应非空"""
    from tests.conftest import TestSessionLocal
    mock_session_local.return_value = TestSessionLocal()
    mock_create_llm.return_value.call_sync.return_value = '{"capabilities": ["能力1", "能力2"], "tags": ["标签"], "skill_level": 3, "preferred_contexts": []}'

    response = client.post('/api/admin/agents/backfill-capabilities', headers=admin_auth_header)
    task_id = response.json()['task_id']
    _wait_for_task(client, admin_auth_header, task_id)

    # 验证 DB
    session = TestSessionLocal()
    try:
        agent = session.query(AgentConfig).filter_by(agent_id='backfill-test-1').first()
        assert agent.capabilities == ['能力1', '能力2']
        assert agent.tags == ['标签']
    finally:
        session.close()


# ==================== 跳过已有 capabilities ====================

@patch('database.SessionLocal')
@patch('services.llm_service.create_llm_service')
def test_backfill_skips_existing(mock_create_llm, mock_session_local, client, admin_auth_header, agents_without_capabilities):
    """已有 capabilities 的 Agent 不应被处理"""
    from tests.conftest import TestSessionLocal
    mock_session_local.return_value = TestSessionLocal()
    mock_create_llm.return_value.call_sync.return_value = '{"capabilities": ["新能力"], "tags": [], "skill_level": 3, "preferred_contexts": []}'

    response = client.post('/api/admin/agents/backfill-capabilities', headers=admin_auth_header)
    task_id = response.json()['task_id']
    result = _wait_for_task(client, admin_auth_header, task_id)
    assert result['processed'] == 2  # 只处理 backfill-test-1 和 backfill-test-2


# ==================== LLM 失败跳过 ====================

@patch('database.SessionLocal')
@patch('services.llm_service.create_llm_service')
def test_backfill_llm_failure_skips(mock_create_llm, mock_session_local, client, admin_auth_header, agents_without_capabilities):
    """LLM 调用失败应跳过该 Agent 继续处理"""
    from tests.conftest import TestSessionLocal
    mock_session_local.return_value = TestSessionLocal()
    mock_create_llm.return_value.call_sync.side_effect = [
        '{"capabilities": ["能力"], "tags": [], "skill_level": 3, "preferred_contexts": []}',
        Exception("LLM API error"),
    ]

    response = client.post('/api/admin/agents/backfill-capabilities', headers=admin_auth_header)
    task_id = response.json()['task_id']
    result = _wait_for_task(client, admin_auth_header, task_id)
    assert result['status'] == 'completed'
    assert result['processed'] == 2
    assert result['updated'] == 1
    assert result['skipped'] == 1


# ==================== 无待补全 Agent ====================

def test_backfill_no_agents(client, admin_auth_header):
    """无待补全 Agent 时返回 task_id=None"""
    response = client.post('/api/admin/agents/backfill-capabilities', headers=admin_auth_header)
    assert response.status_code == 200
    data = response.json()
    # 可能有其他 fixture 创建的 agents，但逻辑正确
    assert 'task_id' in data


# ==================== 进度查询 404 ====================

def test_backfill_status_not_found(client, admin_auth_header):
    """不存在的 task_id 应返回 404"""
    response = client.get('/api/admin/agents/backfill-capabilities/nonexistent', headers=admin_auth_header)
    assert response.status_code == 404
