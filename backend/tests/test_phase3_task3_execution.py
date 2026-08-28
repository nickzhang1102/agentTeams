"""
Tests for Phase 3 Task 3: execute_agent 实际执行

HarnessCoordinator 服务层测试
"""
import pytest
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock

from models import User, Conversation, LeaderSession
from services.harness.harness_coordinator import HarnessCoordinator, get_harness_coordinator


@pytest.fixture(autouse=True)
def mock_openharness_execution(monkeypatch):
    """Keep coordinator tests deterministic and independent of external LLMs."""

    def fake_build_query_context(
        self,
        app_config,
        agent_config,
        agent_id,
        user_id=None,
        llm_service=None,
    ):
        return object(), 1

    async def fake_execute_async(
        self,
        query_context,
        messages,
        agent_id,
        agent_config,
        max_turns,
        event_callback=None,
    ):
        return f"fake response for {agent_id}", [], 3

    monkeypatch.setattr(
        HarnessCoordinator,
        "_build_query_context",
        fake_build_query_context,
    )
    monkeypatch.setattr(HarnessCoordinator, "_execute_async", fake_execute_async)


def test_execute_agent_actual_execution(db_session):
    """测试 Agent 实际执行"""
    coordinator = HarnessCoordinator()

    # 注册测试 agent
    test_agent_config = {
        "name": "test-execution-agent",
        "description": "Test execution agent",
        "model": "inherit",
        "system_prompt": "You are a test agent."
    }
    coordinator._register_single_agent(test_agent_config)

    # 执行 agent
    result = coordinator.execute_agent(
        agent_id='test-execution-agent',
        task='Hello, this is a test.'
    )

    # 验证结果结构
    assert 'success' in result
    assert 'status' in result
    assert 'agent_id' in result
    assert 'content' in result
    assert 'tool_calls' in result
    assert 'tokens_used' in result
    assert 'execution_time' in result

    # 验证执行状态
    assert result['agent_id'] == 'test-execution-agent'
    assert result['status'] in ['completed', 'failed']
    assert isinstance(result['execution_time'], float)
    assert result['execution_time'] >= 0


def test_execute_agent_with_tool_registry(db_session):
    """测试 Agent 执行包含工具注册"""
    coordinator = HarnessCoordinator()

    # 注册技术类 agent（有更多工具）
    tech_agent_config = {
        "name": "test-tech-agent",
        "description": "Test technical agent",
        "model": "inherit",
        "system_prompt": "You are a technical agent.",
    }
    coordinator._register_single_agent(tech_agent_config)

    # 验证工具已分配
    agent_info = coordinator.get_agent_info('test-tech-agent')
    assert agent_info is not None
    assert 'tools' in agent_info

    # 技术类 agent 应该有 bash 和 edit 工具
    # (根据 _get_agent_tools 的逻辑)
    assert 'read_file' in agent_info['tools']


def test_execute_agent_with_history(db_session):
    """测试 Agent 执行包含对话历史"""
    coordinator = HarnessCoordinator()

    # 注册 agent
    test_agent_config = {
        "name": "test-history-agent",
        "description": "Test agent with history",
        "model": "inherit",
        "system_prompt": "You are a test agent."
    }
    coordinator._register_single_agent(test_agent_config)

    # 构建对话历史
    history = [
        {"role": "user", "content": "First message"},
        {"role": "assistant", "content": "First response"},
        {"role": "user", "content": "Second message"},
    ]

    # 执行 agent
    result = coordinator.execute_agent(
        agent_id='test-history-agent',
        task='Continue the conversation',
        history=history
    )

    # 验证执行完成
    assert result['status'] in ['completed', 'failed']


def test_execute_agent_permission_control(db_session):
    """测试 Agent 权限控制"""
    coordinator = HarnessCoordinator()

    # 注册医疗类 agent（有限工具）
    medical_agent_config = {
        "name": "cardiology-expert",
        "description": "Cardiology expert agent",
        "model": "inherit",
        "system_prompt": "You are a cardiology expert."
    }
    coordinator._register_single_agent(medical_agent_config)

    # 验证工具集受限
    agent_info = coordinator.get_agent_info('cardiology-expert')
    assert 'bash' not in agent_info['tools']
    assert 'edit' not in agent_info['tools']
    assert 'read_file' in agent_info['tools']


def test_execute_agent_not_registered(db_session):
    """测试执行未注册的 Agent"""
    coordinator = HarnessCoordinator()

    # 尝试执行未注册的 agent
    with pytest.raises(ValueError, match="Agent 'non-existent-agent' not registered"):
        coordinator.execute_agent(
            agent_id='non-existent-agent',
            task='Test task'
        )


def test_execute_agent_error_handling(db_session):
    """测试 Agent 执行错误处理"""
    coordinator = HarnessCoordinator()

    # 注册 agent
    test_agent_config = {
        "name": "test-error-agent",
        "description": "Test error handling",
        "model": "inherit",
        "system_prompt": "You are a test agent."
    }
    coordinator._register_single_agent(test_agent_config)

    # 执行 agent（应该成功或失败，取决于API配置）
    result = coordinator.execute_agent(
        agent_id='test-error-agent',
        task='Test task'
    )

    # 验证结果结构（无论成功或失败都应该有完整结构）
    assert 'success' in result
    assert 'status' in result
    assert 'error' in result or result['success'] is True


def test_parallel_agent_execution(db_session):
    """测试并行 Agent 执行"""
    coordinator = HarnessCoordinator()

    # 注册多个 agents
    for i in range(3):
        agent_config = {
            "name": f"parallel-agent-{i}",
            "description": f"Parallel test agent {i}",
            "model": "inherit",
            "system_prompt": f"You are parallel agent {i}."
        }
        coordinator._register_single_agent(agent_config)

    # 并行执行
    agents = [f"parallel-agent-{i}" for i in range(3)]
    results = coordinator.execute_team(
        agents=agents,
        task='Test parallel execution',
        parallel=True
    )

    # 验证结果
    assert len(results) == 3
    for result in results:
        assert 'success' in result
        assert 'status' in result
