"""Decision evidence and claim migration smoke test."""

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect

from db import Base
from migrations.versions import d8e9f0a1b2c3_add_decision_evidence_claims as migration
from models import DecisionClaim, DecisionClaimEvidence, DecisionEvidence
from tests.conftest import test_engine


def test_decision_evidence_migration_upgrade_and_downgrade(db_session):
    db_session.close()
    DecisionClaimEvidence.__table__.drop(bind=test_engine, checkfirst=True)
    DecisionClaim.__table__.drop(bind=test_engine, checkfirst=True)
    DecisionEvidence.__table__.drop(bind=test_engine, checkfirst=True)

    try:
        with test_engine.begin() as connection:
            context = MigrationContext.configure(connection)
            with Operations.context(context):
                migration.upgrade()

        tables = set(inspect(test_engine).get_table_names())
        assert {
            'decision_evidences',
            'decision_claims',
            'decision_claim_evidence',
        } <= tables

        with test_engine.begin() as connection:
            context = MigrationContext.configure(connection)
            with Operations.context(context):
                migration.downgrade()

        tables = set(inspect(test_engine).get_table_names())
        assert 'decision_evidences' not in tables
        assert 'decision_claims' not in tables
        assert 'decision_claim_evidence' not in tables
    finally:
        Base.metadata.create_all(bind=test_engine)

