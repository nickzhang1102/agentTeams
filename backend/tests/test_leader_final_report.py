"""测试 LeaderFinalReport 模型（FastAPI 版）"""
import pytest
from models import LeaderFinalReport, LeaderSession, Conversation, User


def test_create_final_report(db_session):
    """测试创建最终报告"""
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

    # 创建最终报告
    report = LeaderFinalReport(
        conversation_id=conv.id,
        leader_session_id=session.id,
        report='# 最终报告\n\n汇总内容...'
    )
    db_session.add(report)
    db_session.commit()

    # 验证
    assert report.id is not None
    assert report.report.startswith('# 最终报告')
    assert report.created_at is not None


def test_final_report_session_unique(db_session):
    """测试一个 session 只能有一个最终报告"""
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

    # 创建第一个报告
    report1 = LeaderFinalReport(
        conversation_id=conv.id,
        leader_session_id=session.id,
        report='Report 1'
    )
    db_session.add(report1)
    db_session.commit()

    # 尝试创建第二个报告
    report2 = LeaderFinalReport(
        conversation_id=conv.id,
        leader_session_id=session.id,
        report='Report 2'
    )
    db_session.add(report2)

    # 应该抛出异常
    with pytest.raises(Exception):  # IntegrityError
        db_session.commit()


def test_final_report_report_not_null(db_session):
    """测试 report 字段不能为空"""
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

    # 创建空报告
    report = LeaderFinalReport(
        conversation_id=conv.id,
        leader_session_id=session.id,
        report=None  # 空
    )
    db_session.add(report)

    # 应该抛出异常
    with pytest.raises(Exception):  # IntegrityError
        db_session.commit()
