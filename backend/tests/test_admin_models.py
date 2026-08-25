"""
Admin Models 测试 — AgentConfig / SystemConfig / ToolCallLog

已迁移至 FastAPI TestClient + db_session fixture。
"""
import pytest
import os
import sys
from datetime import datetime

# Add parent directory to path to import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import AgentConfig, SystemConfig, ToolCallLog, User, Conversation


def test_agent_config_creation(db_session):
    """测试AgentConfig模型创建"""
    agent = AgentConfig(
        agent_id='test-agent',
        name='Test Agent',
        description='A test agent',
        model='claude-sonnet-4-6-20250514',
        file_path='/path/to/test-agent.md',
        file_exists=True,
        is_enabled=True,
        priority=1
    )
    db_session.add(agent)
    db_session.commit()

    assert agent.id is not None
    assert agent.agent_id == 'test-agent'
    assert agent.name == 'Test Agent'
    assert agent.is_enabled is True
    assert agent.total_calls == 0
    assert isinstance(agent.created_at, datetime)


def test_agent_config_unique_agent_id(db_session):
    """测试agent_id唯一性约束"""
    agent1 = AgentConfig(agent_id='duplicate-agent', name='Agent 1')
    agent2 = AgentConfig(agent_id='duplicate-agent', name='Agent 2')

    db_session.add(agent1)
    db_session.add(agent2)

    with pytest.raises(Exception):  # Should raise IntegrityError
        db_session.commit()


def test_system_config_creation(db_session):
    """测试SystemConfig模型创建"""
    config = SystemConfig(
        key='test_key',
        value='test_value',
        description='Test configuration'
    )
    db_session.add(config)
    db_session.commit()

    assert config.id is not None
    assert config.key == 'test_key'
    assert config.value == 'test_value'
    assert isinstance(config.updated_at, datetime)


def test_tool_call_log_creation(db_session):
    """测试ToolCallLog模型创建"""
    # 创建测试用户和对话（满足外键约束）
    user = User(username='testuser')
    user.set_password('password')
    db_session.add(user)
    db_session.commit()

    conversation = Conversation(title='Test Conversation', user_id=user.id)
    db_session.add(conversation)
    db_session.commit()

    log = ToolCallLog(
        conversation_id=conversation.id,
        agent_id='test-agent',
        tool_name='test_tool',
        tool_input={'arg1': 'value1'},
        tool_output={'result': 'success'},
        status='success',
        execution_time=0.5
    )
    db_session.add(log)
    db_session.commit()

    assert log.id is not None
    assert log.agent_id == 'test-agent'
    assert log.tool_name == 'test_tool'
    assert log.tool_input['arg1'] == 'value1'
    assert log.status == 'success'
