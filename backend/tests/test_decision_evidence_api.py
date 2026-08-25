"""Owner and legacy decision evidence detail API tests."""

from leader.leader_persistence import _persist_agent_results, create_leader_session
from models import (
    Conversation,
    DecisionEvidenceMetrics,
    DecisionRun,
    LeaderAgentResult,
    LeaderSession,
    User,
)
from services.decision_evidence_service import DecisionEvidenceService
from tests.conftest import TestSessionLocal


def test_owner_detail_and_other_user_isolation(
    client,
    auth_header,
    another_user_auth_header,
):
    session = TestSessionLocal()
    try:
        owner = session.query(User).filter_by(username='testuser').one()
        conversation = Conversation(title='Evidence API', user_id=owner.id, is_review_mode=True)
        session.add(conversation)
        session.flush()
        leader_session = create_leader_session(
            session, conversation.id, 'Analyze', auto_commit=False
        )
        projection = DecisionEvidenceService(session).persist_for_session(
            leader_session.id,
            [{
                'evidence_id': 'ev_api',
                'source_type': 'web',
                'title': 'API source',
                'excerpt': 'Short excerpt',
                'url': 'https://example.com/api',
                'completeness': 'passage',
            }],
            raw_tool_results={'ev_api': {'passage': 'Full relevant passage'}},
        )[0]
        run_id = str(session.query(DecisionRun).filter_by(
            leader_session_id=leader_session.id
        ).one().run_id)
        session_id = leader_session.id
        session.commit()
    finally:
        session.close()

    run_response = client.get(
        f'/api/decision-runs/{run_id}/evidence/ev_api', headers=auth_header
    )
    session_response = client.get(
        f'/api/leader/sessions/{session_id}/evidence/ev_api', headers=auth_header
    )
    other_response = client.get(
        f'/api/decision-runs/{run_id}/evidence/ev_api',
        headers=another_user_auth_header,
    )
    anonymous_response = client.get(
        f'/api/decision-runs/{run_id}/evidence/ev_api'
    )

    assert projection['raw_ref'] == 'decision_evidence:ev_api'
    assert run_response.status_code == 200
    assert run_response.json()['passage'] == 'Full relevant passage'
    assert run_response.headers['cache-control'] == 'private, no-store'
    assert session_response.status_code == 200
    assert session_response.json()['content_hash'] == run_response.json()['content_hash']
    assert other_response.status_code == 403
    assert anonymous_response.status_code == 401


def test_unavailable_evidence_returns_410(client, auth_header):
    session = TestSessionLocal()
    try:
        owner = session.query(User).filter_by(username='testuser').one()
        conversation = Conversation(title='Unavailable', user_id=owner.id)
        session.add(conversation)
        session.flush()
        leader_session = create_leader_session(
            session, conversation.id, 'Analyze', auto_commit=False
        )
        DecisionEvidenceService(session).persist_for_session(
            leader_session.id,
            [{
                'evidence_id': 'ev_unavailable',
                'source_type': 'web',
                'title': 'Unavailable source',
                'excerpt': 'Summary only',
                'completeness': 'unavailable',
            }],
        )
        run_id = str(session.query(DecisionRun).filter_by(
            leader_session_id=leader_session.id
        ).one().run_id)
        session.commit()
    finally:
        session.close()

    response = client.get(
        f'/api/decision-runs/{run_id}/evidence/ev_unavailable', headers=auth_header
    )

    assert response.status_code == 410
    assert response.json()['detail']['error'] == 'decision_evidence_unavailable'

    session = TestSessionLocal()
    try:
        metrics = session.query(DecisionEvidenceMetrics).one()
        assert metrics.evidence_detail_load_failure_count == 1
    finally:
        session.close()


def test_owner_only_metrics_endpoint_returns_non_content_projection(
    client,
    auth_header,
    another_user_auth_header,
):
    session = TestSessionLocal()
    try:
        owner = session.query(User).filter_by(username='testuser').one()
        conversation = Conversation(title='Metrics API', user_id=owner.id)
        session.add(conversation)
        session.flush()
        leader_session = create_leader_session(
            session, conversation.id, 'Analyze metrics', auto_commit=False
        )
        service = DecisionEvidenceService(session)
        service.persist_for_session(
            leader_session.id,
            [{
                'evidence_id': 'ev_metrics_api',
                'source_type': 'knowledge',
                'source_id': 'private-document-42',
                'title': 'Private title',
                'excerpt': 'Private excerpt',
                'locator': {'source_file': 'users/1/private.md'},
                'completeness': 'snippet',
            }],
        )
        run_id = str(session.query(DecisionRun).one().run_id)
        session.commit()
    finally:
        session.close()

    owner_response = client.get(
        f'/api/decision-runs/{run_id}/evidence-metrics',
        headers=auth_header,
    )
    other_response = client.get(
        f'/api/decision-runs/{run_id}/evidence-metrics',
        headers=another_user_auth_header,
    )

    assert owner_response.status_code == 200
    assert owner_response.headers['cache-control'] == 'private, no-store'
    assert set(owner_response.json()) == {
        'evidence_candidates_total',
        'evidence_cited_total',
        'evidence_ref_resolvable_ratio',
        'supported_claim_ratio',
        'unique_source_count',
        'snippet_only_count',
        'evidence_context_dropped_count',
        'evidence_detail_load_failure_count',
        'updated_at',
    }
    assert owner_response.json()['evidence_candidates_total'] == 1
    assert owner_response.json()['snippet_only_count'] == 1
    assert owner_response.json()['evidence_ref_resolvable_ratio'] is None
    assert owner_response.json()['supported_claim_ratio'] is None
    serialized = owner_response.text.lower()
    for private_value in (
        'private-document-42',
        'private title',
        'private excerpt',
        'users/1/private.md',
    ):
        assert private_value not in serialized
    assert other_response.status_code == 404


def test_legacy_session_detail_and_unresolvable_422(client, auth_header):
    session = TestSessionLocal()
    try:
        owner = session.query(User).filter_by(username='testuser').one()
        conversation = Conversation(title='Legacy evidence', user_id=owner.id)
        session.add(conversation)
        session.flush()
        leader_session = LeaderSession(
            conversation_id=conversation.id,
            user_message='Legacy',
            state='completed',
        )
        session.add(leader_session)
        session.flush()
        session.add(LeaderAgentResult(
            conversation_id=conversation.id,
            leader_session_id=leader_session.id,
            agent_id='legacy-agent',
            agent_name='Legacy Agent',
            status='success',
            sequence_number=1,
            evidence_map=[{
                'schema_version': 1,
                'evidence_id': 'ev_legacy_ok',
                'source_type': 'tool_result',
                'title': 'Legacy source',
                'excerpt': 'Legacy excerpt',
                'raw_ref': 'raw_tool_results.ev_legacy_ok',
            }, {
                'schema_version': 1,
                'evidence_id': 'ev_legacy_missing',
                'source_type': 'tool_result',
                'title': 'Missing legacy source',
                'excerpt': 'Only an aggregate excerpt remains',
                'raw_ref': 'raw_tool_results.ev_legacy_missing',
            }],
            raw_tool_results={
                'ev_legacy_ok': {'result': 'Legacy aggregate passage'},
            },
        ))
        session.commit()
        session_id = leader_session.id
    finally:
        session.close()

    ok_response = client.get(
        f'/api/leader/sessions/{session_id}/evidence/ev_legacy_ok',
        headers=auth_header,
    )
    missing_response = client.get(
        f'/api/leader/sessions/{session_id}/evidence/ev_legacy_missing',
        headers=auth_header,
    )

    assert ok_response.status_code == 200
    assert ok_response.json()['legacy'] is True
    assert ok_response.json()['completeness'] == 'legacy'
    assert missing_response.status_code == 422
    assert missing_response.json()['detail']['error'] == 'legacy_evidence_unresolvable'


def test_public_share_omits_private_knowledge_locator(client, auth_header):
    session = TestSessionLocal()
    try:
        owner = session.query(User).filter_by(username='testuser').one()
        conversation = Conversation(
            title='Private knowledge evidence',
            user_id=owner.id,
            share_token=Conversation.generate_share_token(),
        )
        session.add(conversation)
        session.flush()
        leader_session = create_leader_session(
            session, conversation.id, 'Analyze private knowledge', auto_commit=False
        )
        _persist_agent_results(
            session,
            conversation.id,
            leader_session.id,
            [{
                'agent_id': 'knowledge-agent',
                'agent_name': 'Knowledge Agent',
                'success': True,
                'content': 'Private finding',
                'evidence_map': [{
                    'evidence_id': 'ev_private_doc',
                    'source_type': 'knowledge',
                    'source_id': 'private-document-42',
                    'title': 'Private document',
                    'excerpt': 'Allowed summary',
                    'locator': {'source_file': 'users/1/private.md', 'page': 4},
                    'completeness': 'passage',
                }],
                'raw_tool_results': {
                    'ev_private_doc': {'passage': 'Private full passage'},
                },
            }],
        )
        share_token = conversation.share_token
        session.commit()
    finally:
        session.close()

    response = client.get(f'/api/leader/session/share/{share_token}')

    assert response.status_code == 200
    evidence = response.json()['sessions'][0]['agent_results'][0]['evidence_map'][0]
    assert evidence['excerpt'] == 'Allowed summary'
    assert 'source_id' not in evidence
    assert 'locator' not in evidence
    assert 'url' not in evidence
    assert 'raw_ref' not in evidence
