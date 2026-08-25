"""DecisionRun owner-only read API tests."""

from leader.leader_persistence import create_leader_session
from models import Conversation, DecisionRun, User
from tests.conftest import TestSessionLocal


def test_owner_can_read_run_and_other_user_cannot(
    client,
    auth_header,
    another_user_auth_header,
):
    session = TestSessionLocal()
    try:
        owner = session.query(User).filter_by(username="testuser").one()
        conversation = Conversation(title="Owned run", user_id=owner.id, is_review_mode=True)
        session.add(conversation)
        session.flush()
        leader_session = create_leader_session(
            session,
            conversation.id,
            "Analyze",
            auto_commit=False,
        )
        session.commit()
        conversation_id = conversation.id
        leader_session_id = leader_session.id
        run_id = str(session.query(DecisionRun).filter_by(
            leader_session_id=leader_session.id
        ).one().run_id)
    finally:
        session.close()

    owner_response = client.get(f"/api/decision-runs/{run_id}", headers=auth_header)
    other_response = client.get(
        f"/api/decision-runs/{run_id}",
        headers=another_user_auth_header,
    )
    anonymous_response = client.get(f"/api/decision-runs/{run_id}")
    history_response = client.get(
        f"/api/leader/session/{conversation_id}",
        headers=auth_header,
    )
    status_response = client.get(
        f"/api/leader/status/{leader_session_id}",
        headers=auth_header,
    )

    assert owner_response.status_code == 200
    assert owner_response.json()["run_id"] == run_id
    assert owner_response.json()["legacy"] is False
    assert owner_response.headers["cache-control"] == "no-store"
    assert other_response.status_code == 404
    assert anonymous_response.status_code == 401
    assert history_response.status_code == 200
    assert history_response.json()["sessions"][0]["decision_run"]["run_id"] == run_id
    assert status_response.status_code == 200
    assert status_response.json()["decision_run"]["run_id"] == run_id


def test_invalid_run_id_is_not_enumerable(client, auth_header):
    response = client.get("/api/decision-runs/not-a-uuid", headers=auth_header)

    assert response.status_code == 404
