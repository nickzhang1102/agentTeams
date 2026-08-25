"""测试 LeaderAgentResult 模型（FastAPI 版）"""
import pytest
from models import LeaderAgentResult, LeaderSession, Conversation, User


def test_create_agent_result(db_session):
    """测试创建 Agent 结果"""
    # 创建测试数据
    user = User(username='test', email='test@test.com')
    user.set_password('test123')
    db_session.add(user)
    db_session.commit()

    conv = Conversation(user_id=user.id, title='Test')
    db_session.add(conv)
    db_session.commit()

    session = LeaderSession(conversation_id=conv.id, user_message='Test')
    db_session.add(session)
    db_session.commit()

    # 创建 Agent 结果
    result = LeaderAgentResult(
        conversation_id=conv.id,
        leader_session_id=session.id,
        agent_id='backend-expert',
        agent_name='后端专家',
        status='success',
        content='建议使用微服务架构...',
        sequence_number=1
    )
    db_session.add(result)
    db_session.commit()

    # 验证
    assert result.id is not None
    assert result.agent_id == 'backend-expert'
    assert result.status == 'success'
    assert result.sequence_number == 1


def test_agent_result_sequence_unique(db_session):
    """测试同一 session 内 sequence_number 唯一"""
    user = User(username='test2', email='test2@test.com')
    user.set_password('test123')
    db_session.add(user)
    db_session.commit()

    conv = Conversation(user_id=user.id, title='Test')
    db_session.add(conv)
    db_session.commit()

    session = LeaderSession(conversation_id=conv.id, user_message='Test')
    db_session.add(session)
    db_session.commit()

    # 创建第一个结果
    result1 = LeaderAgentResult(
        conversation_id=conv.id,
        leader_session_id=session.id,
        agent_id='agent1',
        agent_name='Agent 1',
        status='success',
        content='Result 1',
        sequence_number=1
    )
    db_session.add(result1)
    db_session.commit()

    # 尝试创建相同 sequence_number 的结果
    result2 = LeaderAgentResult(
        conversation_id=conv.id,
        leader_session_id=session.id,
        agent_id='agent2',
        agent_name='Agent 2',
        status='success',
        content='Result 2',
        sequence_number=1  # 重复
    )
    db_session.add(result2)

    # 应该抛出异常
    with pytest.raises(Exception):  # IntegrityError
        db_session.commit()


def test_agent_result_status_validation(db_session):
    """测试 status 字段验证"""
    user = User(username='test3', email='test3@test.com')
    user.set_password('test123')
    db_session.add(user)
    db_session.commit()

    conv = Conversation(user_id=user.id, title='Test')
    db_session.add(conv)
    db_session.commit()

    session = LeaderSession(conversation_id=conv.id, user_message='Test')
    db_session.add(session)
    db_session.commit()

    # 测试无效 status - 验证器在对象创建时就会抛出 ValueError
    with pytest.raises(ValueError, match="Invalid status: invalid"):
        result = LeaderAgentResult(
            conversation_id=conv.id,
            leader_session_id=session.id,
            agent_id='agent1',
            agent_name='Agent 1',
            status='invalid',  # 无效值
            content='Result',
            sequence_number=1
        )
