"""
Models 测试 — 核心模型 CRUD（User / Conversation / Message / File）

已迁移至 FastAPI TestClient + db_session fixture。
"""
import pytest
import os
import sys

# Add parent directory to path to import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import User, Conversation, Message, File


def test_user_creation(db_session):
    user = User(username='testuser', email='test@example.com')
    user.set_password('password123')
    db_session.add(user)
    db_session.commit()

    assert user.id is not None
    assert user.username == 'testuser'
    assert user.check_password('password123')


def test_conversation_creation(db_session):
    user = User(username='testuser', email='test@example.com')
    user.set_password('password123')
    db_session.add(user)
    db_session.commit()

    conv = Conversation(title='Test Conversation', user_id=user.id)
    db_session.add(conv)
    db_session.commit()

    assert conv.id is not None
    assert conv.title == 'Test Conversation'
    assert conv.user_id == user.id


def test_message_creation(db_session):
    user = User(username='testuser', email='test@example.com')
    user.set_password('password123')
    db_session.add(user)
    db_session.commit()

    conv = Conversation(title='Test Conversation', user_id=user.id)
    db_session.add(conv)
    db_session.commit()

    message = Message(
        conversation_id=conv.id,
        role='user',
        content='Hello',
        raw_content='Hello'
    )
    db_session.add(message)
    db_session.commit()

    assert message.id is not None
    assert message.role == 'user'
    assert message.content == 'Hello'


def test_file_creation(db_session):
    user = User(username='testuser', email='test@example.com')
    user.set_password('password123')
    db_session.add(user)
    db_session.commit()

    conv = Conversation(title='Test Conversation', user_id=user.id)
    db_session.add(conv)
    db_session.commit()

    message = Message(
        conversation_id=conv.id,
        role='user',
        content='Hello',
        raw_content='Hello'
    )
    db_session.add(message)
    db_session.commit()

    file = File(
        conversation_id=conv.id,
        message_id=message.id,
        user_id=user.id,
        filename='test.py',
        file_path='/tmp/test.py',
        file_type='python',
        file_size=1024,
        version=1
    )
    db_session.add(file)
    db_session.commit()

    assert file.id is not None
    assert file.filename == 'test.py'
    assert file.version == 1


def test_user_to_dict(db_session):
    user = User(username='testuser', email='test@example.com')
    user.set_password('password123')
    db_session.add(user)
    db_session.commit()

    user_dict = user.to_dict()
    assert user_dict['username'] == 'testuser'
    assert user_dict['email'] == 'test@example.com'
    assert 'password_hash' not in user_dict


def test_conversation_relationships(db_session):
    user = User(username='testuser', email='test@example.com')
    user.set_password('password123')
    db_session.add(user)
    db_session.commit()

    conv = Conversation(title='Test Conversation', user_id=user.id)
    db_session.add(conv)
    db_session.commit()

    message = Message(
        conversation_id=conv.id,
        role='user',
        content='Hello',
        raw_content='Hello'
    )
    db_session.add(message)
    db_session.commit()

    file = File(
        conversation_id=conv.id,
        message_id=message.id,
        user_id=user.id,
        filename='test.py',
        file_path='/tmp/test.py',
        file_type='python',
        file_size=1024,
        version=1
    )
    db_session.add(file)
    db_session.commit()

    # 验证关系
    messages = conv.messages.all()
    files = conv.files.all()
    assert len(messages) == 1
    assert messages[0].content == 'Hello'
    assert len(files) == 1
    assert files[0].filename == 'test.py'


def test_conversation_model(db_session):
    """测试对话模型基本功能"""
    user = User(username='testuser', email='test@example.com')
    user.set_password('password123')
    db_session.add(user)
    db_session.commit()

    conv = Conversation(
        title='Test Conversation',
        user_id=user.id
    )
    db_session.add(conv)
    db_session.commit()

    assert conv.id is not None
    assert conv.title == 'Test Conversation'
    assert conv.user_id == user.id
    assert conv.is_archived is False
    assert conv.is_review_mode is False


def test_conversation_to_dict_includes_review_mode(db_session):
    """测试对话模型暴露会话级评审模式"""
    user = User(username='reviewuser', email='review@example.com')
    user.set_password('password123')
    db_session.add(user)
    db_session.commit()

    conv = Conversation(
        title='Review Conversation',
        user_id=user.id,
        is_review_mode=True
    )
    db_session.add(conv)
    db_session.commit()

    result = conv.to_dict()

    assert result['is_review_mode'] is True


def test_file_versioning(db_session):
    user = User(username='testuser', email='test@example.com')
    user.set_password('password123')
    db_session.add(user)
    db_session.commit()

    conv = Conversation(title='Test Conversation', user_id=user.id)
    db_session.add(conv)
    db_session.commit()

    message = Message(
        conversation_id=conv.id,
        role='user',
        content='Hello',
        raw_content='Hello'
    )
    db_session.add(message)
    db_session.commit()

    # 创建版本 1
    file1 = File(
        conversation_id=conv.id,
        message_id=message.id,
        user_id=user.id,
        filename='test.py',
        file_path='/tmp/test_v1.py',
        file_type='python',
        file_size=1024,
        version=1
    )
    db_session.add(file1)
    db_session.commit()

    # 创建版本 2
    file2 = File(
        conversation_id=conv.id,
        message_id=message.id,
        user_id=user.id,
        filename='test.py',
        file_path='/tmp/test_v2.py',
        file_type='python',
        file_size=2048,
        version=2
    )
    db_session.add(file2)
    db_session.commit()

    assert file1.version == 1
    assert file2.version == 2
