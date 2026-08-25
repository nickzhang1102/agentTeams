"""
Leader Models 测试 — LeaderSession / Message Leader 关联

已迁移至 FastAPI TestClient + db_session fixture。
"""
import pytest
import json
import os
import sys
from datetime import datetime

# Add parent directory to path to import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import LeaderSession, Conversation, User, Message


def test_create_leader_session(db_session):
    """测试创建 LeaderSession"""
    # 创建用户和对话
    user = User(username='testuser')
    user.set_password('password')
    db_session.add(user)
    db_session.commit()

    conversation = Conversation(title='Test', user_id=user.id)
    db_session.add(conversation)
    db_session.commit()

    # 创建 LeaderSession
    session = LeaderSession(
        conversation_id=conversation.id,
        user_message='设计一个系统',
        state='idle'
    )
    db_session.add(session)
    db_session.commit()

    # 验证
    assert session.id is not None
    assert session.state == 'idle'
    assert session.locale == 'zh-CN'
    assert session.stop_requested == False
    assert session.total_tokens == 0


def test_leader_session_to_dict(db_session):
    """测试 to_dict 方法"""
    user = User(username='testuser2')
    user.set_password('password')
    db_session.add(user)
    db_session.commit()

    conversation = Conversation(title='Test2', user_id=user.id)
    db_session.add(conversation)
    db_session.commit()

    session = LeaderSession(
        conversation_id=conversation.id,
        user_message='测试消息',
        state='assessing',
        assessment_score=85,
        selected_agents='backend-expert'  # String 类型
    )
    db_session.add(session)
    db_session.commit()

    result = session.to_dict()
    assert result['locale'] == 'zh-CN'
    assert result['state'] == 'assessing'
    assert result['assessment_score'] == 85
    assert result['selected_agents'] == ['backend-expert']  # to_dict 返回列表


# ==================== 字段验证测试 ====================

def test_state_validation_valid(db_session):
    """测试 state 字段有效值"""
    user = User(username='testuser3')
    user.set_password('password')
    db_session.add(user)
    db_session.commit()

    conversation = Conversation(title='Test3', user_id=user.id)
    db_session.add(conversation)
    db_session.commit()

    # 测试所有有效状态（与设计文档一致）
    valid_states = [
        'idle',           # 空闲
        'assessing',      # 需求评估中
        'questioning',    # 生成提问中
        'forming_team',   # 团队组建中
        'monitoring',     # 执行监控中
        'summarizing',    # 结果汇总中
        'completed',      # 已完成
        'stopped',        # 已停止
        'failed'          # 失败
    ]
    for state in valid_states:
        session = LeaderSession(
            conversation_id=conversation.id,
            user_message='测试',
            state=state
        )
        db_session.add(session)
        db_session.commit()
        assert session.state == state


def test_state_validation_invalid(db_session):
    """测试 state 字段无效值应抛出异常"""
    user = User(username='testuser4')
    user.set_password('password')
    db_session.add(user)
    db_session.commit()

    conversation = Conversation(title='Test4', user_id=user.id)
    db_session.add(conversation)
    db_session.commit()

    # 创建无效状态的会话
    session = LeaderSession(
        conversation_id=conversation.id,
        user_message='测试',
        state='invalid_state'
    )
    db_session.add(session)

    # 应该抛出 ValueError
    with pytest.raises(ValueError, match="Invalid state"):
        db_session.commit()


def test_assessment_score_validation_valid(db_session):
    """测试 assessment_score 有效范围"""
    user = User(username='testuser5')
    user.set_password('password')
    db_session.add(user)
    db_session.commit()

    conversation = Conversation(title='Test5', user_id=user.id)
    db_session.add(conversation)
    db_session.commit()

    # 测试边界值
    for score in [0, 50, 100]:
        session = LeaderSession(
            conversation_id=conversation.id,
            user_message='测试',
            state='assessing',
            assessment_score=score
        )
        db_session.add(session)
        db_session.commit()
        assert session.assessment_score == score


def test_assessment_score_validation_invalid(db_session):
    """测试 assessment_score 超出范围应抛出异常"""
    user = User(username='testuser6')
    user.set_password('password')
    db_session.add(user)
    db_session.commit()

    conversation = Conversation(title='Test6', user_id=user.id)
    db_session.add(conversation)
    db_session.commit()

    # 测试超出范围的值
    for score in [-1, 101, 150]:
        session = LeaderSession(
            conversation_id=conversation.id,
            user_message='测试',
            state='assessing',
            assessment_score=score
        )
        db_session.add(session)

        # 应该抛出 ValueError
        with pytest.raises(ValueError, match="assessment_score must be between 0 and 100"):
            db_session.commit()
        db_session.rollback()


# ==================== JSON 辅助方法测试 ====================

def test_json_helper_methods(db_session):
    """测试 JSON 字段的 get/set 辅助方法"""
    user = User(username='testuser7')
    user.set_password('password')
    db_session.add(user)
    db_session.commit()

    conversation = Conversation(title='Test7', user_id=user.id)
    db_session.add(conversation)
    db_session.commit()

    session = LeaderSession(
        conversation_id=conversation.id,
        user_message='测试',
        state='forming_team'
    )
    db_session.add(session)
    db_session.commit()

    # 测试 selected_agents
    agents = ['backend-expert', 'frontend-expert', 'database-specialist']
    session.set_selected_agents_list(agents)
    db_session.commit()

    assert session.get_selected_agents_list() == agents
    assert session.selected_agents == ','.join(agents)  # String 类型，逗号分隔


def test_json_helper_methods_empty(db_session):
    """测试 JSON 辅助方法处理空值"""
    user = User(username='testuser8')
    user.set_password('password')
    db_session.add(user)
    db_session.commit()

    conversation = Conversation(title='Test8', user_id=user.id)
    db_session.add(conversation)
    db_session.commit()

    session = LeaderSession(
        conversation_id=conversation.id,
        user_message='测试',
        state='idle'
    )
    db_session.add(session)
    db_session.commit()

    # 测试空值
    assert session.get_selected_agents_list() == []


# ==================== Message 与 LeaderSession 关联测试 ====================

def test_message_leader_session_relationship(db_session):
    """测试 Message 与 LeaderSession 的关联关系"""
    user = User(username='testuser9')
    user.set_password('password')
    db_session.add(user)
    db_session.commit()

    conversation = Conversation(title='Test9', user_id=user.id)
    db_session.add(conversation)
    db_session.commit()

    # 创建 LeaderSession
    session = LeaderSession(
        conversation_id=conversation.id,
        user_message='设计系统',
        state='monitoring'
    )
    db_session.add(session)
    db_session.commit()

    # 创建关联的 Message
    message1 = Message(
        conversation_id=conversation.id,
        role='assistant',
        content='Leader 正在思考...',
        leader_session_id=session.id,
        message_type='leader_thinking'
    )
    message2 = Message(
        conversation_id=conversation.id,
        role='assistant',
        content='Backend Agent 结果',
        leader_session_id=session.id,
        message_type='agent_result'
    )
    db_session.add_all([message1, message2])
    db_session.commit()

    # 验证关联
    assert message1.leader_session_id == session.id
    assert message1.message_type == 'leader_thinking'
    assert message2.leader_session_id == session.id
    assert message2.message_type == 'agent_result'


def test_message_to_dict_includes_leader_fields(db_session):
    """测试 Message.to_dict() 包含 leader_session_id 和 message_type"""
    user = User(username='testuser10')
    user.set_password('password')
    db_session.add(user)
    db_session.commit()

    conversation = Conversation(title='Test10', user_id=user.id)
    db_session.add(conversation)
    db_session.commit()

    # 创建 LeaderSession
    session = LeaderSession(
        conversation_id=conversation.id,
        user_message='测试',
        state='summarizing'
    )
    db_session.add(session)
    db_session.commit()

    # 创建 Message
    message = Message(
        conversation_id=conversation.id,
        role='assistant',
        content='总结报告',
        content_locale='zh-CN',
        leader_session_id=session.id,
        message_type='leader_summary'
    )
    db_session.add(message)
    db_session.commit()

    # 验证 to_dict() 包含新字段
    result = message.to_dict()
    assert 'leader_session_id' in result
    assert result['leader_session_id'] == session.id
    assert 'message_type' in result
    assert result['message_type'] == 'leader_summary'
    assert result['content_locale'] == 'zh-CN'


def test_message_default_values(db_session):
    """测试 Message 默认值"""
    user = User(username='testuser11')
    user.set_password('password')
    db_session.add(user)
    db_session.commit()

    conversation = Conversation(title='Test11', user_id=user.id)
    db_session.add(conversation)
    db_session.commit()

    # 创建普通消息（不指定 leader_session_id 和 message_type）
    message = Message(
        conversation_id=conversation.id,
        role='user',
        content='普通消息'
    )
    db_session.add(message)
    db_session.commit()

    # 验证默认值
    assert message.leader_session_id is None
    assert message.message_type == 'normal'

    # 验证 to_dict()
    result = message.to_dict()
    assert result['leader_session_id'] is None
    assert result['message_type'] == 'normal'
