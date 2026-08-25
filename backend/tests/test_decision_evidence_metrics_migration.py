"""Decision evidence quality metrics migration smoke test."""

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect

from db import Base
from migrations.versions import d8e9f0a1b2c3_add_decision_evidence_claims as evidence_migration
from migrations.versions import e9f0a1b2c3d4_add_decision_evidence_metrics as metrics_migration
from models import (
    DecisionClaim,
    DecisionClaimEvidence,
    DecisionEvidence,
    DecisionEvidenceMetrics,
)
from tests.conftest import test_engine


def test_decision_evidence_metrics_migration_upgrade_and_downgrade(db_session):
    db_session.close()
    DecisionEvidenceMetrics.__table__.drop(bind=test_engine, checkfirst=True)
    DecisionClaimEvidence.__table__.drop(bind=test_engine, checkfirst=True)
    DecisionClaim.__table__.drop(bind=test_engine, checkfirst=True)
    DecisionEvidence.__table__.drop(bind=test_engine, checkfirst=True)

    try:
        with test_engine.begin() as connection:
            context = MigrationContext.configure(connection)
            with Operations.context(context):
                evidence_migration.upgrade()
                metrics_migration.upgrade()

        inspector = inspect(test_engine)
        assert 'decision_evidence_metrics' in set(inspector.get_table_names())
        claim_columns = {
            column['name'] for column in inspector.get_columns('decision_claims')
        }
        assert {
            'evidence_ref_count',
            'resolved_evidence_ref_count',
        } <= claim_columns

        metric_columns = {
            column['name']
            for column in inspector.get_columns('decision_evidence_metrics')
        }
        assert {
            'decision_run_id',
            'evidence_candidates_total',
            'evidence_cited_total',
            'evidence_refs_total',
            'evidence_refs_resolved_total',
            'evidence_ref_resolvable_ratio',
            'supported_claim_ratio',
            'unique_source_count',
            'snippet_only_count',
            'evidence_context_dropped_count',
            'evidence_detail_load_failure_count',
        } <= metric_columns

        with test_engine.begin() as connection:
            context = MigrationContext.configure(connection)
            with Operations.context(context):
                metrics_migration.downgrade()

        inspector = inspect(test_engine)
        assert 'decision_evidence_metrics' not in set(inspector.get_table_names())
        claim_columns = {
            column['name'] for column in inspector.get_columns('decision_claims')
        }
        assert 'evidence_ref_count' not in claim_columns
        assert 'resolved_evidence_ref_count' not in claim_columns

        with test_engine.begin() as connection:
            context = MigrationContext.configure(connection)
            with Operations.context(context):
                evidence_migration.downgrade()
    finally:
        Base.metadata.create_all(bind=test_engine)
