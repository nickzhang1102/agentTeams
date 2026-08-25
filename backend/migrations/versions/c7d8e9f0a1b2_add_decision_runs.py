"""add decision runs

Revision ID: c7d8e9f0a1b2
Revises: b6c7d8e9f0a1
Create Date: 2026-08-03
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from migrations.safe_ops import SafeOperations


revision = 'c7d8e9f0a1b2'
down_revision = 'b6c7d8e9f0a1'
branch_labels = None
depends_on = None


def upgrade():
    safe_op = SafeOperations(op)
    safe_op.create_table(
        'decision_runs',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('run_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('leader_session_id', sa.Integer(), nullable=True),
        sa.Column('conversation_id', sa.Integer(), nullable=True),
        sa.Column('usage_record_id', sa.Integer(), nullable=True),
        sa.Column('source', sa.String(length=20), nullable=False),
        sa.Column('source_ref', sa.String(length=200), nullable=True),
        sa.Column('workflow_template_id', sa.Integer(), nullable=True),
        sa.Column('workflow_version_id', sa.BigInteger(), nullable=True),
        sa.Column('domain_profile_key', sa.String(length=100), nullable=False),
        sa.Column('domain_profile_version', sa.Integer(), nullable=True),
        sa.Column('state', sa.String(length=20), nullable=False),
        sa.Column('quality_status', sa.String(length=20), nullable=False),
        sa.Column('current_stage', sa.String(length=20), nullable=False),
        sa.Column('degradation_reasons', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('error_code', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("source IN ('web', 'oncopath', 'api')", name='ck_decision_runs_source'),
        sa.CheckConstraint("state IN ('queued', 'running', 'waiting_input', 'completed', 'failed', 'cancelled')", name='ck_decision_runs_state'),
        sa.CheckConstraint("quality_status IN ('pending', 'passed', 'degraded', 'blocked')", name='ck_decision_runs_quality_status'),
        sa.CheckConstraint("current_stage IN ('intake', 'assessment', 'team_form', 'execution', 'review', 'synthesis', 'persistence')", name='ck_decision_runs_current_stage'),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['leader_session_id'], ['leader_sessions.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['usage_record_id'], ['usage_records.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['workflow_template_id'], ['workflow_templates.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('leader_session_id'),
        sa.UniqueConstraint('run_id'),
        sa.UniqueConstraint('usage_record_id'),
    )
    safe_op.create_index('idx_decision_runs_source_ref', 'decision_runs', ['source', 'source_ref'])
    safe_op.create_index(op.f('ix_decision_runs_conversation_id'), 'decision_runs', ['conversation_id'])
    safe_op.create_index(op.f('ix_decision_runs_current_stage'), 'decision_runs', ['current_stage'])
    safe_op.create_index(op.f('ix_decision_runs_quality_status'), 'decision_runs', ['quality_status'])
    safe_op.create_index(op.f('ix_decision_runs_state'), 'decision_runs', ['state'])


def downgrade():
    op.drop_index(op.f('ix_decision_runs_state'), table_name='decision_runs')
    op.drop_index(op.f('ix_decision_runs_quality_status'), table_name='decision_runs')
    op.drop_index(op.f('ix_decision_runs_current_stage'), table_name='decision_runs')
    op.drop_index(op.f('ix_decision_runs_conversation_id'), table_name='decision_runs')
    op.drop_index('idx_decision_runs_source_ref', table_name='decision_runs')
    op.drop_table('decision_runs')
