"""
测试风险等级功能
"""
import pytest
from models import LeaderSession, User, Conversation


class TestRiskLevel:
    """风险等级功能测试"""

    def test_risk_level_field_default(self, db_session):
        """测试 risk_level 默认值为 medium"""
        # 创建测试用户和对话
        user = User(username='test_risk_user1')
        user.set_password('password')
        db_session.add(user)
        db_session.commit()

        conversation = Conversation(title='Test', user_id=user.id)
        db_session.add(conversation)
        db_session.commit()

        session = LeaderSession(
            conversation_id=conversation.id,
            user_message="测试消息"
        )
        db_session.add(session)
        db_session.commit()

        assert session.risk_level == 'medium'

    def test_risk_level_field_validation_valid(self, db_session):
        """测试有效的 risk_level 值"""
        # 创建测试用户和对话
        user = User(username='test_risk_user2')
        user.set_password('password')
        db_session.add(user)
        db_session.commit()

        conversation = Conversation(title='Test', user_id=user.id)
        db_session.add(conversation)
        db_session.commit()

        for level in ['low', 'medium', 'high']:
            session = LeaderSession(
                conversation_id=conversation.id,
                user_message=f"测试消息 {level}",
                risk_level=level
            )
            db_session.add(session)
        db_session.commit()

        # 所有值都应该被接受
        sessions = db_session.query(LeaderSession).filter(
            LeaderSession.user_message.like('测试消息%')
        ).all()
        assert len(sessions) == 3

    def test_risk_level_field_validation_invalid(self, db_session):
        """测试无效的 risk_level 值应该抛出异常"""
        # 创建测试用户和对话
        user = User(username='test_risk_user3')
        user.set_password('password')
        db_session.add(user)
        db_session.commit()

        conversation = Conversation(title='Test', user_id=user.id)
        db_session.add(conversation)
        db_session.commit()

        session = LeaderSession(
            conversation_id=conversation.id,
            user_message="测试无效风险等级",
            risk_level='invalid'
        )
        db_session.add(session)

        with pytest.raises(ValueError) as exc_info:
            db_session.flush()

        assert 'Invalid risk_level' in str(exc_info.value)

    def test_risk_level_in_to_dict(self, db_session):
        """测试 to_dict 方法包含 risk_level"""
        # 创建测试用户和对话
        user = User(username='test_risk_user4')
        user.set_password('password')
        db_session.add(user)
        db_session.commit()

        conversation = Conversation(title='Test', user_id=user.id)
        db_session.add(conversation)
        db_session.commit()

        session = LeaderSession(
            conversation_id=conversation.id,
            user_message="测试 to_dict",
            risk_level='high'
        )
        db_session.add(session)
        db_session.commit()

        result = session.to_dict()
        assert 'risk_level' in result
        assert result['risk_level'] == 'high'
