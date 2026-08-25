"""DecisionRun 生命周期与投影契约测试。"""

import pytest

from leader.leader_persistence import create_leader_session
from models import (
    Conversation,
    DecisionRun,
    LeaderFinalReport,
    LeaderSession,
    User,
)
from services.decision_run_service import (
    DecisionRunService,
    DecisionRunTransitionError,
)
from utils.time_utils import utcnow_naive


def _create_session(db_session, *, username="run-owner"):
    user = User(username=username, password_hash="test-hash")
    db_session.add(user)
    db_session.flush()
    conversation = Conversation(title="Decision run", user_id=user.id, is_review_mode=True)
    db_session.add(conversation)
    db_session.flush()
    leader_session = create_leader_session(
        db_session,
        conversation.id,
        "Analyze this",
        auto_commit=False,
    )
    db_session.commit()
    return user, conversation, leader_session


def test_create_leader_session_creates_queued_decision_run(db_session):
    _, conversation, leader_session = _create_session(db_session)

    run = db_session.query(DecisionRun).one()

    assert run.leader_session_id == leader_session.id
    assert run.conversation_id == conversation.id
    assert run.state == "queued"
    assert run.quality_status == "pending"
    assert str(run.run_id)


def test_completion_waits_for_report_persisted(db_session):
    _, conversation, leader_session = _create_session(db_session)

    service = DecisionRunService(db_session)
    run = service.get_for_session(leader_session.id)
    service.mark_started(leader_session.id)
    report = LeaderFinalReport(
        conversation_id=conversation.id,
        leader_session_id=leader_session.id,
        report="Final report",
    )
    db_session.add(report)
    db_session.flush()
    service.mark_report_persisted(leader_session.id, quality_status="passed")

    assert run.state == "completed"
    assert run.completed_at is not None
    assert service.projection(run)["final_report_id"] == report.id


def test_waiting_resume_and_terminal_transitions_are_safe(db_session):
    _, _, leader_session = _create_session(db_session)
    service = DecisionRunService(db_session)
    run = service.get_for_session(leader_session.id)
    service.mark_started(leader_session.id)

    leader_session.state = "questioning"
    service.sync_from_leader_session(leader_session.id)
    assert run.state == "waiting_input"

    service.mark_started(leader_session.id)
    assert run.state == "running"

    leader_session.state = "failed"
    service.sync_from_leader_session(leader_session.id, error_code="test_failure")
    assert run.state == "failed"
    assert run.error_code == "test_failure"

    service.mark_started(leader_session.id)
    assert run.state == "failed"
    with pytest.raises(DecisionRunTransitionError):
        service.transition(
            run.run_id,
            "failed",
            "running",
            stage="assessment",
        )


def test_degraded_quality_requires_stable_reason(db_session):
    _, _, leader_session = _create_session(db_session)
    service = DecisionRunService(db_session)
    run = service.get_for_session(leader_session.id)

    with pytest.raises(ValueError):
        service.mark_quality(run, "degraded", [])

    service.mark_quality(run, "degraded", ["provider_snippet_only"])
    assert run.quality_status == "degraded"
    assert run.degradation_reasons == ["provider_snippet_only"]

    service.mark_quality(run, "passed")
    assert run.quality_status == "degraded"
    assert run.degradation_reasons == ["provider_snippet_only"]


def test_cancelled_terminal_is_idempotent(db_session):
    _, _, leader_session = _create_session(db_session, username="cancel-owner")
    service = DecisionRunService(db_session)
    run = service.get_for_session(leader_session.id)
    service.mark_started(leader_session.id)
    leader_session.state = "stopped"

    service.sync_from_leader_session(leader_session.id)
    completed_at = run.completed_at
    service.sync_from_leader_session(leader_session.id)

    assert run.state == "cancelled"
    assert run.completed_at == completed_at


def test_legacy_projection_does_not_invent_identity_or_quality(db_session):
    user = User(username="legacy-owner", password_hash="test-hash")
    db_session.add(user)
    db_session.flush()
    conversation = Conversation(title="Legacy", user_id=user.id)
    db_session.add(conversation)
    db_session.flush()
    leader_session = LeaderSession(
        conversation_id=conversation.id,
        user_message="Legacy run",
        state="completed",
        started_at=utcnow_naive(),
        completed_at=utcnow_naive(),
    )
    db_session.add(leader_session)
    db_session.commit()

    projection = DecisionRunService(db_session).projection_for_session(leader_session)

    assert projection["legacy"] is True
    assert projection["run_id"] is None
    assert projection["quality_status"] is None
    assert projection["state"] == "completed"
