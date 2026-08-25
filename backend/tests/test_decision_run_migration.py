"""针对隔离测试数据库的 DecisionRun Alembic 迁移冒烟测试。"""

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Column, Integer, MetaData, Table, inspect

from db import Base
from migrations.versions import c7d8e9f0a1b2_add_decision_runs as migration
from models import (
    DecisionClaim,
    DecisionClaimEvidence,
    DecisionEvidence,
    DecisionEvidenceMetrics,
    DecisionRun,
)
from tests.conftest import test_engine

# 历史迁移 c7d8e9f0a1b2 的 decision_runs.usage_record_id 外键引用 usage_records；
# 计费移除后模型层已无该表，这里补一个仅含 id 的桩表供外键绑定
_usage_stub_metadata = MetaData()
_usage_records_stub = Table(
    'usage_records',
    _usage_stub_metadata,
    Column('id', Integer, primary_key=True),
)


def test_decision_run_migration_upgrade_and_downgrade(db_session):
    db_session.close()
    DecisionEvidenceMetrics.__table__.drop(bind=test_engine, checkfirst=True)
    DecisionClaimEvidence.__table__.drop(bind=test_engine, checkfirst=True)
    DecisionClaim.__table__.drop(bind=test_engine, checkfirst=True)
    DecisionEvidence.__table__.drop(bind=test_engine, checkfirst=True)
    DecisionRun.__table__.drop(bind=test_engine, checkfirst=True)
    _usage_records_stub.drop(bind=test_engine, checkfirst=True)
    _usage_records_stub.create(bind=test_engine)

    try:
        with test_engine.begin() as connection:
            context = MigrationContext.configure(connection)
            with Operations.context(context):
                migration.upgrade()

        inspector = inspect(test_engine)
        assert "decision_runs" in inspector.get_table_names()
        columns = {column["name"] for column in inspector.get_columns("decision_runs")}
        assert {"run_id", "leader_session_id", "state", "quality_status"} <= columns

        with test_engine.begin() as connection:
            context = MigrationContext.configure(connection)
            with Operations.context(context):
                migration.downgrade()

        assert "decision_runs" not in inspect(test_engine).get_table_names()
    finally:
        _usage_records_stub.drop(bind=test_engine, checkfirst=True)
        Base.metadata.create_all(bind=test_engine)
