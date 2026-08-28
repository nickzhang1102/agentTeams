"""
Quick Mode Execution 测试

测试 skip_to_execution + pre_selected_agents 参数校验。
SSE 流式执行跳过（需 mock LLM），仅测试 API 层校验逻辑。
"""
import pytest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['SKIP_MCP_INIT'] = 'true'

from tests.conftest import TestSessionLocal
from models import User, Conversation, AgentConfig


@pytest.fixture(autouse=True)
def mock_leader_workflow(monkeypatch):
    """Validate the API contract without starting a real LangGraph/LLM run."""

    async def fake_async_run_leader_workflow(
        *, existing_session_id=None, **_kwargs
    ):
        yield {
            'type': 'done',
            'session_id': existing_session_id,
            'message': 'Workflow completed',
        }

    monkeypatch.setattr(
        'api.leader_api.async_run_leader_workflow',
        fake_async_run_leader_workflow,
    )


@pytest.fixture
def setup_quick_mode_data(auth_header):
    """创建快速模式测试所需的数据"""
    session = TestSessionLocal()
    try:
        user = session.query(User).filter_by(username='testuser').first()
        conv = Conversation(title='快速模式测试', user_id=user.id)
        session.add(conv)
        session.commit()
        session.refresh(conv)

        agents = []
        for aid, name, enabled in [
            ('quick-agent-a', '快速A', True),
            ('quick-agent-b', '快速B', True),
            ('quick-agent-disabled', '已禁用Agent', False),
        ]:
            agent = AgentConfig(
                agent_id=aid,
                name=name,
                description=f'{name}描述',
                model='inherit',
                is_enabled=enabled,
                file_exists=True,
            )
            session.add(agent)
            agents.append(agent)
        session.commit()

        return {
            'conversation_id': conv.id,
            'user_id': user.id,
            'enabled_agents': ['quick-agent-a', 'quick-agent-b'],
            'disabled_agent': 'quick-agent-disabled',
        }
    finally:
        session.close()


# ========== 快速模式参数校验测试 ==========

def test_quick_mode_no_pre_selected_agents(client, auth_header, setup_quick_mode_data):
    """skip_to_execution=True 但 pre_selected_agents 为空 → 400"""
    data = setup_quick_mode_data
    response = client.post(
        '/api/leader/start',
        json={
            'conversation_id': data['conversation_id'],
            'message': '测试消息',
            'skip_to_execution': True,
        },
        headers=auth_header
    )
    assert response.status_code == 400
    assert '必须指定至少一个 Agent' in response.json()['detail']['error']


def test_quick_mode_empty_pre_selected_agents(client, auth_header, setup_quick_mode_data):
    """skip_to_execution=True 但 pre_selected_agents 为空列表 → 400"""
    data = setup_quick_mode_data
    response = client.post(
        '/api/leader/start',
        json={
            'conversation_id': data['conversation_id'],
            'message': '测试消息',
            'skip_to_execution': True,
            'pre_selected_agents': [],
        },
        headers=auth_header
    )
    assert response.status_code == 400
    assert '必须指定至少一个 Agent' in response.json()['detail']['error']


def test_quick_mode_invalid_agent_id(client, auth_header, setup_quick_mode_data):
    """pre_selected_agents 包含不存在的 agent_id → 400"""
    data = setup_quick_mode_data
    response = client.post(
        '/api/leader/start',
        json={
            'conversation_id': data['conversation_id'],
            'message': '测试消息',
            'skip_to_execution': True,
            'pre_selected_agents': ['不存在的agent', 'quick-agent-a'],
        },
        headers=auth_header
    )
    assert response.status_code == 400
    assert '不存在' in response.json()['detail']['error']


def test_quick_mode_disabled_agent(client, auth_header, setup_quick_mode_data):
    """pre_selected_agents 包含已禁用 agent → 400"""
    data = setup_quick_mode_data
    response = client.post(
        '/api/leader/start',
        json={
            'conversation_id': data['conversation_id'],
            'message': '测试消息',
            'skip_to_execution': True,
            'pre_selected_agents': [data['disabled_agent']],
        },
        headers=auth_header
    )
    assert response.status_code == 400
    assert '已禁用' in response.json()['detail']['error']


def test_quick_mode_rejects_duplicate_agents(client, auth_header, setup_quick_mode_data):
    data = setup_quick_mode_data
    response = client.post(
        '/api/leader/start',
        json={
            'conversation_id': data['conversation_id'],
            'message': '测试消息',
            'skip_to_execution': True,
            'pre_selected_agents': ['quick-agent-a', 'quick-agent-a'],
        },
        headers=auth_header,
    )

    assert response.status_code == 400
    assert '不能重复指定' in response.json()['detail']['error']


def test_quick_mode_valid_agents_pass_validation(client, auth_header, setup_quick_mode_data):
    """skip_to_execution=True + 有效 agent → 校验通过，进入 Leader SSE 流"""
    data = setup_quick_mode_data
    response = client.post(
        '/api/leader/start',
        json={
            'conversation_id': data['conversation_id'],
            'message': '测试消息',
            'skip_to_execution': True,
            'pre_selected_agents': data['enabled_agents'],
        },
        headers=auth_header
    )
    # 校验通过：进入 Leader SSE 流
    # 参数校验通过后进入运行依赖检查；测试环境可缺模型配置或余额。
    assert response.status_code in (200, 402, 503)
    if response.status_code == 200:
        assert response.content_type == 'text/event-stream; charset=utf-8'


def test_normal_mode_unaffected(client, auth_header, setup_quick_mode_data):
    """skip_to_execution=False（默认）→ 行为不受影响"""
    data = setup_quick_mode_data
    response = client.post(
        '/api/leader/start',
        json={
            'conversation_id': data['conversation_id'],
            'message': '测试消息',
        },
        headers=auth_header
    )
    # 不因新增字段报 400/422
    assert response.status_code not in [400, 422]


def test_quick_mode_default_false(client, auth_header, setup_quick_mode_data):
    """不传 skip_to_execution 时默认为 False"""
    data = setup_quick_mode_data
    response = client.post(
        '/api/leader/start',
        json={
            'conversation_id': data['conversation_id'],
            'message': '测试消息',
        },
        headers=auth_header
    )
    # 不触发快速模式校验
    assert response.status_code not in [400, 422]
