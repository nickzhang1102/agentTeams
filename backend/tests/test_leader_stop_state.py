"""Leader 持久取消的数据库层契约测试。"""

from leader.leader_persistence import (
    _persist_final_report,
    create_leader_session,
    is_session_stop_requested,
    mark_session_failed,
    mark_session_stopped,
)
from models import (
    Conversation,
    DecisionRun,
    LeaderFinalReport,
    LeaderSession,
    LeaderWorkflowCancellation,
    User,
)
from services.decision_run_service import DecisionRunService
from utils.time_utils import utcnow_naive


def _create_running_session(db_session):
    user = User(username="stop-owner", password_hash="test-hash")
    db_session.add(user)
    db_session.flush()
    conversation = Conversation(
        title="Stop contract",
        user_id=user.id,
        is_review_mode=True,
        status="analyzing",
    )
    db_session.add(conversation)
    db_session.flush()
    leader_session = create_leader_session(
        db_session,
        conversation.id,
        "Analyze this",
        auto_commit=False,
    )
    service = DecisionRunService(db_session)
    service.mark_started(leader_session.id)
    db_session.commit()
    return user, conversation, leader_session


def test_mark_session_stopped_converges_related_state(db_session):
    _, conversation, leader_session = _create_running_session(db_session)

    assert mark_session_stopped(db_session, leader_session.id) is True
    db_session.expire_all()

    assert db_session.get(LeaderSession, leader_session.id).state == "stopped"
    assert db_session.get(Conversation, conversation.id).status == "stopped"
    assert db_session.query(DecisionRun).one().state == "cancelled"
    assert is_session_stop_requested(db_session, leader_session.id) is True

    assert mark_session_stopped(db_session, leader_session.id) is True
    db_session.expire_all()
    assert db_session.get(LeaderSession, leader_session.id).state == "stopped"


def test_cancellation_marker_survives_conversation_delete(db_session):
    _, conversation, leader_session = _create_running_session(db_session)
    session_id = leader_session.id

    mark_session_stopped(db_session, session_id, reason="conversation_deleted")
    db_session.delete(conversation)
    db_session.commit()
    db_session.expire_all()

    assert db_session.get(LeaderSession, session_id) is None
    marker = db_session.get(LeaderWorkflowCancellation, session_id)
    assert marker is not None
    assert marker.reason == "conversation_deleted"
    assert is_session_stop_requested(db_session, session_id) is True


def test_late_failure_cannot_overwrite_stopped_session(db_session):
    _, _, leader_session = _create_running_session(db_session)

    mark_session_stopped(db_session, leader_session.id)
    mark_session_failed(db_session, leader_session.id, "late worker error")
    db_session.expire_all()

    assert db_session.get(LeaderSession, leader_session.id).state == "stopped"
    assert db_session.query(DecisionRun).one().state == "cancelled"


def test_late_final_report_cannot_overwrite_stopped_session(db_session):
    """停止先提交后，迟到汇总不能写报告或恢复 completed。"""
    _, conversation, leader_session = _create_running_session(db_session)

    mark_session_stopped(db_session, leader_session.id)
    report = _persist_final_report(
        db_session,
        leader_session.id,
        "# 迟到报告",
        completed_at=utcnow_naive(),
        content_locale="zh-CN",
        state={"total_tokens": 100},
    )
    db_session.expire_all()

    assert report is None
    assert db_session.get(LeaderSession, leader_session.id).state == "stopped"
    assert db_session.get(Conversation, conversation.id).status == "stopped"
    assert db_session.query(DecisionRun).one().state == "cancelled"
    assert db_session.query(LeaderFinalReport).count() == 0
