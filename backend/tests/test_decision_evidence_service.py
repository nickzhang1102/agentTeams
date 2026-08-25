"""Run-scoped evidence persistence and claim validation tests."""

from leader.leader_persistence import (
    _persist_agent_results,
    _persist_final_report,
    create_leader_session,
)
from models import (
    Conversation,
    DecisionClaim,
    DecisionClaimEvidence,
    DecisionEvidence,
    DecisionEvidenceMetrics,
    DecisionRun,
    LeaderAgentResult,
    User,
)
from services.decision_evidence_service import DecisionEvidenceService
from utils.time_utils import utcnow_naive


def _create_session(db_session, username='evidence-owner'):
    user = User(username=username, password_hash='test-hash')
    db_session.add(user)
    db_session.flush()
    conversation = Conversation(title='Evidence run', user_id=user.id, is_review_mode=True)
    db_session.add(conversation)
    db_session.flush()
    leader_session = create_leader_session(
        db_session,
        conversation.id,
        'Analyze sources',
        auto_commit=False,
    )
    db_session.commit()
    return user, conversation, leader_session


def _evidence_item(evidence_id, *, rank, relation=None, url='https://example.com/source'):
    item = {
        'schema_version': 2,
        'evidence_id': evidence_id,
        'source_type': 'web',
        'source_id': url,
        'title': f'Source {rank}',
        'excerpt': f'Excerpt {rank}',
        'url': url,
        'provider': 'exa',
        'locator': {'rank': rank},
        'rank': rank,
        'relevance_score': 0.8,
        'completeness': 'passage',
        'agent_id': 'research-agent',
        'subtask_id': 'subtask_1',
    }
    if relation:
        item['relation'] = relation
    return item


def test_agent_persistence_writes_run_truth_and_compatibility_projection(db_session):
    _, conversation, leader_session = _create_session(db_session)
    item = _evidence_item('ev_result_8', rank=8)
    passage = 'Important qualifier. ' + ('x' * 4500)

    _persist_agent_results(
        db_session,
        conversation.id,
        leader_session.id,
        [{
            'agent_id': 'research-agent',
            'agent_name': 'Research Agent',
            'success': True,
            'content': 'Report [evidence_id:ev_result_8]',
            'structured_report': {
                'summary': {'one_sentence': 'Result 8 is important'},
                'markdown_report': 'Report [evidence_id:ev_result_8]',
                'claims': [{
                    'claim_id': 'research_agent_claim_fact_1',
                    'text': 'Result 8 is important',
                    'claim_type': 'fact',
                    'confidence': 0.8,
                    'evidence_relations': [{
                        'evidence_id': 'ev_result_8',
                        'relation': 'supports',
                    }],
                    'agent_refs': ['research-agent'],
                }],
            },
            'evidence_map': [item],
            'raw_tool_results': {
                'ev_result_8': {'passage': passage, 'result': passage},
            },
        }],
    )

    evidence = db_session.query(DecisionEvidence).one()
    agent_result = db_session.query(LeaderAgentResult).one()

    assert evidence.decision_run_id == db_session.query(DecisionRun).one().id
    assert evidence.evidence_id == 'ev_result_8'
    assert evidence.rank == 8
    assert len(evidence.passage) == 4000
    assert evidence.passage.endswith('...(truncated)')
    assert agent_result.evidence_map[0]['raw_ref'] == 'decision_evidence:ev_result_8'
    assert 'passage' not in agent_result.evidence_map[0]
    assert agent_result.structured_report['claims'][0]['support_status'] == 'supported'
    assert agent_result.structured_report['claims'][0]['evidence_relations'] == [{
        'evidence_id': 'ev_result_8',
        'relation': 'supports',
    }]


def test_agent_persistence_is_idempotent_per_session_and_agent(db_session):
    _, conversation, leader_session = _create_session(
        db_session,
        username='agent-result-idempotency-owner',
    )
    first = {
        'agent_id': 'research-agent',
        'agent_name': 'Research Agent',
        'success': True,
        'content': 'durable result',
    }

    _persist_agent_results(
        db_session,
        conversation.id,
        leader_session.id,
        [first],
    )
    _persist_agent_results(
        db_session,
        conversation.id,
        leader_session.id,
        [{**first, 'content': 'late duplicate'}],
    )

    results = db_session.query(LeaderAgentResult).filter_by(
        leader_session_id=leader_session.id
    ).all()
    assert len(results) == 1
    assert results[0].content == 'durable result'


def test_agent_persistence_keeps_result_when_evidence_enrichment_fails(db_session):
    _, conversation, leader_session = _create_session(
        db_session,
        username='agent-evidence-failure-owner',
    )
    item = _evidence_item('ev_invalid_claim', rank=1)

    _persist_agent_results(
        db_session,
        conversation.id,
        leader_session.id,
        [
            {
                'agent_id': 'research-agent',
                'agent_name': 'Research Agent',
                'success': True,
                'content': 'Report [evidence_id:ev_invalid_claim]',
                'structured_report': {
                    'summary': {'one_sentence': 'Result remains readable'},
                    'claims': [{
                        'claim_id': 'invalid_confidence_claim',
                        'text': 'This claim triggers enrichment failure',
                        'claim_type': 'fact',
                        'confidence': 1.5,
                        'evidence_relations': [{
                            'evidence_id': 'ev_invalid_claim',
                            'relation': 'supports',
                        }],
                    }],
                },
                'evidence_map': [item],
            },
            {
                'agent_id': 'analysis-agent',
                'agent_name': 'Analysis Agent',
                'success': True,
                'content': 'Independent result also remains available',
            },
        ],
    )

    agent_results = db_session.query(LeaderAgentResult).order_by(
        LeaderAgentResult.sequence_number
    ).all()
    agent_result = agent_results[0]
    run = db_session.query(DecisionRun).one()

    assert len(agent_results) == 2
    assert agent_results[1].content == 'Independent result also remains available'
    assert db_session.query(DecisionEvidence).count() == 0
    assert db_session.query(DecisionClaim).count() == 0
    assert agent_result.content == 'Report [evidence_id:ev_invalid_claim]'
    assert agent_result.evidence_map == [item]
    assert agent_result.structured_report['source_quality_status'] == 'degraded'
    assert agent_result.structured_report['source_degradation_reasons'] == [
        'evidence_persistence_failed'
    ]
    assert run.quality_status == 'degraded'
    assert run.degradation_reasons == ['evidence_persistence_failed']


def test_claim_validation_drops_invalid_refs_and_marks_conflicts(db_session):
    _, _, leader_session = _create_session(db_session, username='claim-owner')
    service = DecisionEvidenceService(db_session)
    service.persist_for_session(
        leader_session.id,
        [_evidence_item('ev_support', rank=1), _evidence_item('ev_against', rank=2)],
        raw_tool_results={
            'ev_support': {'passage': 'The intervention improved outcomes.'},
            'ev_against': {'passage': 'The intervention did not improve outcomes.'},
        },
    )

    result = service.persist_claims_for_session(
        leader_session.id,
        [{
            'claim_id': 'claim_conflict',
            'text': 'The intervention improves outcomes.',
            'claim_type': 'fact',
            'confidence': 0.7,
            'evidence_relations': [
                {'evidence_id': 'ev_support', 'relation': 'supports'},
                {'evidence_id': 'ev_against', 'relation': 'contradicts'},
            ],
        }, {
            'claim_id': 'claim_invalid',
            'text': 'An unsupported statement.',
            'claim_type': 'fact',
            'evidence_refs': ['ev_missing'],
        }],
    )
    db_session.commit()

    claims = {
        claim.claim_id: claim
        for claim in db_session.query(DecisionClaim).order_by(DecisionClaim.claim_id)
    }
    run = db_session.query(DecisionRun).one()

    assert claims['claim_conflict'].support_status == 'conflicting'
    assert claims['claim_invalid'].support_status == 'unsupported'
    assert db_session.query(DecisionClaimEvidence).count() == 2
    assert result.invalid_evidence_refs == ('ev_missing',)
    assert set(result.degradation_reasons) == {
        'conflicting_claim',
        'invalid_evidence_reference',
        'unsupported_fact_claim',
    }
    assert run.quality_status == 'degraded'
    assert set(run.degradation_reasons) == set(result.degradation_reasons)


def test_evidence_url_scheme_is_restricted(db_session):
    owner, _, leader_session = _create_session(db_session, username='scheme-owner')
    service = DecisionEvidenceService(db_session)
    projection = service.persist_for_session(
        leader_session.id,
        [_evidence_item('ev_bad_url', rank=1, url='javascript:alert(1)')],
        raw_tool_results={'ev_bad_url': {'passage': 'Safe stored passage'}},
    )[0]
    db_session.commit()

    run = db_session.query(DecisionRun).one()
    detail = service.detail_for_owner(str(run.run_id), 'ev_bad_url', owner.id)

    assert projection['url'] is None
    assert detail['url'] is None
    assert detail['passage'] == 'Safe stored passage'


def test_run_delete_cascades_evidence_claims_and_repeated_persistence_is_idempotent(
    db_session,
):
    _, _, leader_session = _create_session(db_session, username='cascade-owner')
    service = DecisionEvidenceService(db_session)
    item = _evidence_item('ev_cascade', rank=1)
    raw = {'ev_cascade': {'passage': 'Cascade evidence passage'}}

    service.persist_for_session(leader_session.id, [item], raw_tool_results=raw)
    service.persist_for_session(leader_session.id, [item], raw_tool_results=raw)
    service.persist_claims_for_session(
        leader_session.id,
        [{
            'claim_id': 'claim_cascade',
            'text': 'Cascade claim',
            'claim_type': 'fact',
            'evidence_refs': ['ev_cascade'],
        }],
    )
    db_session.commit()

    assert db_session.query(DecisionEvidence).count() == 1
    assert db_session.query(DecisionClaim).count() == 1
    assert db_session.query(DecisionClaimEvidence).count() == 1
    assert db_session.query(DecisionEvidenceMetrics).count() == 1

    run = db_session.query(DecisionRun).one()
    db_session.delete(run)
    db_session.commit()

    assert db_session.query(DecisionEvidence).count() == 0
    assert db_session.query(DecisionClaim).count() == 0
    assert db_session.query(DecisionClaimEvidence).count() == 0
    assert db_session.query(DecisionEvidenceMetrics).count() == 0


def test_final_report_invalid_fact_is_persisted_unsupported_and_degrades_run(db_session):
    _, _, leader_session = _create_session(db_session, username='final-claim-owner')
    structured_report = {
        'title': 'Final report',
        'claims': [{
            'claim_id': 'final_claim_1',
            'text': 'A fact with a fabricated reference',
            'claim_type': 'fact',
            'confidence': 0.9,
            'evidence_relations': [{
                'evidence_id': 'ev_does_not_exist',
                'relation': 'supports',
            }],
        }],
    }

    report = _persist_final_report(
        db_session,
        leader_session.id,
        '# Final report',
        utcnow_naive(),
        structured_report=structured_report,
        evidence_map=[],
    )

    run = db_session.query(DecisionRun).one()
    claim = db_session.query(DecisionClaim).filter_by(claim_id='final_claim_1').one()

    assert claim.support_status == 'unsupported'
    assert report.structured_report['claims'][0]['support_status'] == 'unsupported'
    assert report.structured_report['claims'][0]['evidence_relations'] == []
    assert run.quality_status == 'degraded'
    assert set(run.degradation_reasons) == {
        'invalid_evidence_reference',
        'unsupported_fact_claim',
    }


def test_final_report_persists_when_evidence_enrichment_fails(db_session):
    _, _, leader_session = _create_session(
        db_session,
        username='final-evidence-failure-owner',
    )
    item = _evidence_item('ev_final_invalid_claim', rank=1)
    structured_report = {
        'title': 'Final report',
        'claims': [{
            'claim_id': 'final_invalid_confidence_claim',
            'text': 'The report must survive evidence failure',
            'claim_type': 'fact',
            'confidence': -0.1,
            'evidence_relations': [{
                'evidence_id': 'ev_final_invalid_claim',
                'relation': 'supports',
            }],
        }],
    }

    report = _persist_final_report(
        db_session,
        leader_session.id,
        '# Final report remains available',
        utcnow_naive(),
        structured_report=structured_report,
        evidence_map=[item],
    )

    db_session.refresh(leader_session)
    run = db_session.query(DecisionRun).one()

    assert db_session.query(DecisionEvidence).count() == 0
    assert db_session.query(DecisionClaim).count() == 0
    assert report.report == '# Final report remains available'
    assert report.evidence_map == [item]
    assert report.structured_report['source_quality_status'] == 'degraded'
    assert report.structured_report['source_degradation_reasons'] == [
        'evidence_persistence_failed'
    ]
    assert leader_session.state == 'completed'
    assert run.state == 'completed'
    assert run.quality_status == 'degraded'
    assert run.degradation_reasons == ['evidence_persistence_failed']


def test_quality_metrics_are_content_free_and_idempotent(db_session):
    owner, _, leader_session = _create_session(db_session, username='metrics-owner')
    service = DecisionEvidenceService(db_session)
    evidence_items = [
        _evidence_item(
            'ev_passage',
            rank=1,
            url='https://first.example.com/source',
        ),
        {
            **_evidence_item(
                'ev_snippet',
                rank=2,
                url='https://second.example.com/source',
            ),
            'title': 'Private metric title',
            'excerpt': 'Private metric excerpt',
            'locator': {'document_id': 'private-document-id'},
            'completeness': 'snippet',
        },
    ]
    raw_tool_results = {
        'ev_passage': {'passage': 'Private full passage'},
    }
    claims = [{
        'claim_id': 'claim_supported',
        'text': 'Supported fact',
        'claim_type': 'fact',
        'evidence_refs': ['ev_passage'],
    }, {
        'claim_id': 'claim_missing',
        'text': 'Unsupported fact',
        'claim_type': 'fact',
        'evidence_refs': ['ev_missing'],
    }]

    service.persist_for_session(
        leader_session.id,
        evidence_items,
        raw_tool_results=raw_tool_results,
    )
    service.persist_claims_for_session(leader_session.id, claims)
    service.record_context_dropped_for_session(leader_session.id, 3)

    # Replaying persistence refreshes the snapshot instead of accumulating totals.
    service.persist_for_session(
        leader_session.id,
        evidence_items,
        raw_tool_results=raw_tool_results,
    )
    service.persist_claims_for_session(leader_session.id, claims)
    db_session.commit()

    run = db_session.query(DecisionRun).one()
    metrics = db_session.query(DecisionEvidenceMetrics).one()
    payload = service.quality_metrics_for_owner(str(run.run_id), owner.id)

    assert metrics.evidence_refs_total == 2
    assert metrics.evidence_refs_resolved_total == 1
    assert payload == {
        'evidence_candidates_total': 2,
        'evidence_cited_total': 1,
        'evidence_ref_resolvable_ratio': 0.5,
        'supported_claim_ratio': 0.5,
        'unique_source_count': 2,
        'snippet_only_count': 1,
        'evidence_context_dropped_count': 3,
        'evidence_detail_load_failure_count': 0,
        'updated_at': payload['updated_at'],
    }
    serialized = repr(payload).lower()
    for private_value in (
        'private full passage',
        'private metric title',
        'private metric excerpt',
        'private-document-id',
        'first.example.com',
        'second.example.com',
    ):
        assert private_value not in serialized


def test_detail_failure_metrics_require_a_resolved_owner_run(db_session):
    owner, _, leader_session = _create_session(
        db_session,
        username='detail-metrics-owner',
    )
    other = User(username='detail-metrics-other', password_hash='test-hash')
    db_session.add(other)
    db_session.flush()
    service = DecisionEvidenceService(db_session)
    service.persist_for_session(
        leader_session.id,
        [{
            **_evidence_item('ev_unavailable', rank=1),
            'completeness': 'unavailable',
        }],
    )
    run = db_session.query(DecisionRun).one()

    for action in (
        lambda: service.detail_for_owner(str(run.run_id), 'ev_missing', owner.id),
        lambda: service.detail_for_owner(str(run.run_id), 'ev_unavailable', owner.id),
        lambda: service.detail_for_owner(str(run.run_id), 'ev_missing', other.id),
        lambda: service.detail_for_owner('00000000-0000-0000-0000-000000000000', 'ev_missing', owner.id),
    ):
        try:
            action()
        except LookupError:
            pass

    metrics = db_session.query(DecisionEvidenceMetrics).one()
    assert metrics.evidence_detail_load_failure_count == 2


def test_final_report_records_final_synthesis_context_drops(db_session):
    _, _, leader_session = _create_session(db_session, username='drop-count-owner')

    _persist_final_report(
        db_session,
        leader_session.id,
        '# Final report',
        utcnow_naive(),
        evidence_map=[],
        evidence_context_dropped_count=4,
    )

    metrics = db_session.query(DecisionEvidenceMetrics).one()
    assert metrics.evidence_context_dropped_count == 4
