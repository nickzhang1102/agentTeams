"""
测试 Message 模型（合并后的统一消息表）

已迁移至 FastAPI TestClient + db_session fixture。
"""
import pytest
import os
import sys

# Add parent directory to path to import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import LeaderSession, Message, Conversation, User


def test_message_model_exists():
    """测试 Message 模型是否存在"""
    from models import Message
    assert Message is not None


def test_create_normal_message(db_session):
    """测试创建 Leader 用户问题的对话入口消息"""
    # 创建测试用户和对话
    user = User(username='test_user')
    user.set_password('password')
    db_session.add(user)
    db_session.commit()

    conv = Conversation(title='Test', user_id=user.id)
    db_session.add(conv)
    db_session.commit()

    # 使用静态方法创建普通消息
    msg = Message.create_normal_message(
        conversation_id=conv.id,
        role='user',
        content='Hello, this is a test message'
    )
    db_session.add(msg)
    db_session.commit()

    # 验证
    assert msg.id is not None
    assert msg.role == 'user'
    assert msg.message_type == 'normal'
    assert msg.content == {'text': 'Hello, this is a test message'}
    assert msg.get_text_content() == 'Hello, this is a test message'


def test_create_leader_message(db_session):
    """测试创建 Leader 流程消息"""
    # 创建测试用户和对话
    user = User(username='test_user2')
    user.set_password('password')
    db_session.add(user)
    db_session.commit()

    conv = Conversation(title='Test2', user_id=user.id)
    db_session.add(conv)
    db_session.commit()

    # 创建 LeaderSession
    session = LeaderSession(
        conversation_id=conv.id,
        user_message='Test message',
        state='idle'
    )
    db_session.add(session)
    db_session.commit()

    # 使用静态方法创建 Leader 消息
    msg = Message.create_leader_message(
        conversation_id=conv.id,
        leader_session_id=session.id,
        message_type='assessment',
        content={'score': 85, 'risk_level': 'high'},
        sequence_number=1
    )
    db_session.add(msg)
    db_session.commit()

    # 验证
    assert msg.id is not None
    assert msg.role is None  # Leader 消息没有 role
    assert msg.message_type == 'assessment'
    assert msg.content['score'] == 85
    assert msg.sequence_number == 1


def test_unique_sequence_number_constraint(db_session):
    """测试唯一性约束：同一个 session 内 sequence_number 必须唯一"""
    # 创建测试用户和对话
    user = User(username='test_user3')
    user.set_password('password')
    db_session.add(user)
    db_session.commit()

    conv = Conversation(title='Test3', user_id=user.id)
    db_session.add(conv)
    db_session.commit()

    # 创建 LeaderSession
    session = LeaderSession(
        conversation_id=conv.id,
        user_message='Test message',
        state='idle'
    )
    db_session.add(session)
    db_session.commit()

    # 创建第一条消息，sequence_number=1
    msg1 = Message.create_leader_message(
        conversation_id=conv.id,
        leader_session_id=session.id,
        message_type='assessment',
        content={'score': 85},
        sequence_number=1
    )
    db_session.add(msg1)
    db_session.commit()

    # 尝试创建第二条消息，使用相同的 sequence_number=1
    msg2 = Message.create_leader_message(
        conversation_id=conv.id,
        leader_session_id=session.id,
        message_type='question',
        content={'text': 'Question 1'},
        sequence_number=1  # 重复的 sequence_number
    )
    db_session.add(msg2)

    # 应该抛出异常（IntegrityError）
    with pytest.raises(Exception):  # IntegrityError 或数据库约束异常
        db_session.commit()


def test_cascade_delete_with_leader_session(db_session):
    """测试级联删除：删除 LeaderSession 时应删除关联的 Message"""
    # 创建测试用户和对话
    user = User(username='test_user4')
    user.set_password('password')
    db_session.add(user)
    db_session.commit()

    conv = Conversation(title='Test4', user_id=user.id)
    db_session.add(conv)
    db_session.commit()

    # 创建 LeaderSession
    session = LeaderSession(
        conversation_id=conv.id,
        user_message='Test message',
        state='idle'
    )
    db_session.add(session)
    db_session.commit()

    # 创建多条 Leader 消息
    msg1 = Message.create_leader_message(
        conversation_id=conv.id,
        leader_session_id=session.id,
        message_type='assessment',
        content={'score': 85},
        sequence_number=1
    )
    msg2 = Message.create_leader_message(
        conversation_id=conv.id,
        leader_session_id=session.id,
        message_type='question',
        content={'text': 'Question 1'},
        sequence_number=2
    )
    msg3 = Message.create_leader_message(
        conversation_id=conv.id,
        leader_session_id=session.id,
        message_type='progress',
        content={'text': 'Processing...'},
        sequence_number=3
    )
    db_session.add_all([msg1, msg2, msg3])
    db_session.commit()

    session_id = session.id

    # 删除 LeaderSession
    db_session.delete(session)
    db_session.commit()

    # 验证关联的 Message 也被删除
    remaining_messages = db_session.query(Message).filter(
        Message.leader_session_id == session_id,
        Message.sequence_number.isnot(None)
    ).all()
    assert len(remaining_messages) == 0


def test_get_text_content_method(db_session):
    """测试 get_text_content 方法"""
    # 创建测试用户和对话
    user = User(username='test_user5')
    user.set_password('password')
    db_session.add(user)
    db_session.commit()

    conv = Conversation(title='Test5', user_id=user.id)
    db_session.add(conv)
    db_session.commit()

    # 测试 JSONB 格式
    msg1 = Message.create_normal_message(
        conversation_id=conv.id,
        role='assistant',
        content='This is JSONB content'
    )
    db_session.add(msg1)
    db_session.commit()
    assert msg1.get_text_content() == 'This is JSONB content'

    # 测试纯文本格式（向后兼容）
    msg2 = Message(
        conversation_id=conv.id,
        role='user',
        content='Plain text content',  # 直接赋值字符串
        message_type='normal'
    )
    db_session.add(msg2)
    db_session.commit()
    # 注意：如果是字符串，get_text_content 会直接返回
    # 但在 PostgreSQL 中，JSONB 字段不会接受字符串直接赋值


def test_to_dict_method(db_session):
    """测试 to_dict 方法"""
    # 创建测试用户和对话
    user = User(username='test_user6')
    user.set_password('password')
    db_session.add(user)
    db_session.commit()

    conv = Conversation(title='Test6', user_id=user.id)
    db_session.add(conv)
    db_session.commit()

    # 创建 LeaderSession
    session = LeaderSession(
        conversation_id=conv.id,
        user_message='Test message',
        state='assessing'
    )
    db_session.add(session)
    db_session.commit()

    # 创建 Leader 消息
    msg = Message.create_leader_message(
        conversation_id=conv.id,
        leader_session_id=session.id,
        message_type='assessment',
        content={
            'score': 85,
            'risk_level': 'high',
            'complexity': 'moderate'
        },
        sequence_number=1
    )
    db_session.add(msg)
    db_session.commit()

    # 测试 to_dict 方法
    result = msg.to_dict()

    # 验证返回的字典包含所有必要字段
    assert 'id' in result
    assert result['id'] == msg.id

    assert 'conversation_id' in result
    assert result['conversation_id'] == conv.id

    assert 'leader_session_id' in result
    assert result['leader_session_id'] == session.id

    assert 'message_type' in result
    assert result['message_type'] == 'assessment'

    assert 'content' in result
    assert result['content']['score'] == 85
    assert result['content']['risk_level'] == 'high'
    assert result['content']['complexity'] == 'moderate'

    assert 'sequence_number' in result
    assert result['sequence_number'] == 1

    assert 'created_at' in result
    assert result['created_at'] is not None


def test_sequence_number_ordering(db_session):
    """测试排序功能：sequence_number 顺序"""
    # 创建测试用户和对话
    user = User(username='test_user7')
    user.set_password('password')
    db_session.add(user)
    db_session.commit()

    conv = Conversation(title='Test7', user_id=user.id)
    db_session.add(conv)
    db_session.commit()

    # 创建 LeaderSession
    session = LeaderSession(
        conversation_id=conv.id,
        user_message='Test message',
        state='monitoring'
    )
    db_session.add(session)
    db_session.commit()

    # 创建多条消息，顺序不同
    msg1 = Message.create_leader_message(
        conversation_id=conv.id,
        leader_session_id=session.id,
        message_type='assessment',
        content={'score': 85},
        sequence_number=1
    )
    msg2 = Message.create_leader_message(
        conversation_id=conv.id,
        leader_session_id=session.id,
        message_type='question',
        content={'text': 'Question 1'},
        sequence_number=2
    )
    msg3 = Message.create_leader_message(
        conversation_id=conv.id,
        leader_session_id=session.id,
        message_type='progress',
        content={'text': 'Processing...'},
        sequence_number=3
    )
    db_session.add_all([msg1, msg2, msg3])
    db_session.commit()

    # 验证可以按 sequence_number 查询和排序
    messages = db_session.query(Message).filter(
        Message.leader_session_id == session.id,
        Message.sequence_number.isnot(None)
    ).order_by(Message.sequence_number).all()

    assert len(messages) == 3
    assert messages[0].sequence_number == 1
    assert messages[1].sequence_number == 2
    assert messages[2].sequence_number == 3
    assert messages[0].message_type == 'assessment'
    assert messages[1].message_type == 'question'
    assert messages[2].message_type == 'progress'


def test_mixed_normal_and_leader_messages(db_session):
    """测试混合存储普通消息和 Leader 消息"""
    # 创建测试用户和对话
    user = User(username='test_user8')
    user.set_password('password')
    db_session.add(user)
    db_session.commit()

    conv = Conversation(title='Test8', user_id=user.id)
    db_session.add(conv)
    db_session.commit()

    # 创建 LeaderSession
    session = LeaderSession(
        conversation_id=conv.id,
        user_message='Test message',
        state='monitoring'
    )
    db_session.add(session)
    db_session.commit()

    # 创建普通消息
    normal_msg1 = Message.create_normal_message(
        conversation_id=conv.id,
        role='user',
        content='User question'
    )
    normal_msg2 = Message.create_normal_message(
        conversation_id=conv.id,
        role='assistant',
        content='Assistant response'
    )

    # 创建 Leader 消息
    leader_msg = Message.create_leader_message(
        conversation_id=conv.id,
        leader_session_id=session.id,
        message_type='assessment',
        content={'score': 85},
        sequence_number=1
    )

    db_session.add_all([normal_msg1, normal_msg2, leader_msg])
    db_session.commit()

    # 验证可以区分查询
    # 查询所有普通消息
    normal_messages = db_session.query(Message).filter(
        Message.conversation_id == conv.id,
        Message.message_type == 'normal'
    ).all()
    assert len(normal_messages) == 2

    # 查询所有 Leader 消息
    leader_messages = db_session.query(Message).filter(
        Message.leader_session_id == session.id,
        Message.sequence_number.isnot(None)
    ).all()
    assert len(leader_messages) == 1
