"""add decision evidence and claims

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-08-04
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from migrations.safe_ops import SafeOperations


revision = 'd8e9f0a1b2c3'
down_revision = 'c7d8e9f0a1b2'
branch_labels = None
depends_on = None


def upgrade():
    safe_op = SafeOperations(op)
    safe_op.create_table(
        'decision_evidences',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('decision_run_id', sa.BigInteger(), nullable=False),
        sa.Column('evidence_id', sa.String(length=100), nullable=False),
        sa.Column('source_type', sa.String(length=30), nullable=False),
        sa.Column('source_id', sa.String(length=500), nullable=True),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('url', sa.Text(), nullable=True),
        sa.Column('provider', sa.String(length=100), nullable=True),
        sa.Column('locator', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('excerpt', sa.Text(), nullable=False),
        sa.Column('passage', sa.Text(), nullable=True),
        sa.Column('completeness', sa.String(length=20), nullable=False),
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column('source_version', sa.String(length=200), nullable=True),
        sa.Column('relevance_score', sa.Float(), nullable=True),
        sa.Column('rank', sa.Integer(), nullable=True),
        sa.Column('agent_id', sa.String(length=100), nullable=True),
        sa.Column('subtask_id', sa.String(length=100), nullable=True),
        sa.Column('retrieved_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "source_type IN ('web', 'knowledge', 'memory', 'user_input', "
            "'tool_result', 'subtask_result', 'agent_report')",
            name='ck_decision_evidences_source_type',
        ),
        sa.CheckConstraint(
            "completeness IN ('passage', 'snippet', 'legacy', 'unavailable')",
            name='ck_decision_evidences_completeness',
        ),
        sa.CheckConstraint(
            'relevance_score IS NULL OR (relevance_score >= 0 AND relevance_score <= 1)',
            name='ck_decision_evidences_relevance_score',
        ),
        sa.CheckConstraint('rank IS NULL OR rank >= 0', name='ck_decision_evidences_rank'),
        sa.ForeignKeyConstraint(['decision_run_id'], ['decision_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'decision_run_id', 'evidence_id', name='uq_decision_evidences_run_evidence'
        ),
    )
    safe_op.create_index(
        'idx_decision_evidences_run_source',
        'decision_evidences',
        ['decision_run_id', 'source_type'],
    )
    safe_op.create_index(
        op.f('ix_decision_evidences_decision_run_id'),
        'decision_evidences',
        ['decision_run_id'],
    )

    safe_op.create_table(
        'decision_claims',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('decision_run_id', sa.BigInteger(), nullable=False),
        sa.Column('claim_id', sa.String(length=100), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('claim_type', sa.String(length=30), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('support_status', sa.String(length=20), nullable=False),
        sa.Column('agent_refs', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "claim_type IN ('fact', 'interpretation', 'recommendation', 'risk', 'uncertainty')",
            name='ck_decision_claims_claim_type',
        ),
        sa.CheckConstraint(
            "support_status IN ('supported', 'partial', 'unsupported', 'conflicting')",
            name='ck_decision_claims_support_status',
        ),
        sa.CheckConstraint(
            'confidence IS NULL OR (confidence >= 0 AND confidence <= 1)',
            name='ck_decision_claims_confidence',
        ),
        sa.ForeignKeyConstraint(['decision_run_id'], ['decision_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('decision_run_id', 'claim_id', name='uq_decision_claims_run_claim'),
    )
    safe_op.create_index(
        'idx_decision_claims_run_status',
        'decision_claims',
        ['decision_run_id', 'support_status'],
    )
    safe_op.create_index(
        op.f('ix_decision_claims_decision_run_id'),
        'decision_claims',
        ['decision_run_id'],
    )

    safe_op.create_table(
        'decision_claim_evidence',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('decision_claim_id', sa.BigInteger(), nullable=False),
        sa.Column('decision_evidence_id', sa.BigInteger(), nullable=False),
        sa.Column('relation', sa.String(length=20), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "relation IN ('supports', 'contradicts', 'qualifies')",
            name='ck_decision_claim_evidence_relation',
        ),
        sa.CheckConstraint('sequence >= 0', name='ck_decision_claim_evidence_sequence'),
        sa.ForeignKeyConstraint(
            ['decision_claim_id'], ['decision_claims.id'], ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['decision_evidence_id'], ['decision_evidences.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'decision_claim_id',
            'decision_evidence_id',
            'relation',
            name='uq_decision_claim_evidence_relation',
        ),
    )
    safe_op.create_index(
        op.f('ix_decision_claim_evidence_decision_claim_id'),
        'decision_claim_evidence',
        ['decision_claim_id'],
    )
    safe_op.create_index(
        op.f('ix_decision_claim_evidence_decision_evidence_id'),
        'decision_claim_evidence',
        ['decision_evidence_id'],
    )


def downgrade():
    op.drop_index(
        op.f('ix_decision_claim_evidence_decision_evidence_id'),
        table_name='decision_claim_evidence',
    )
    op.drop_index(
        op.f('ix_decision_claim_evidence_decision_claim_id'),
        table_name='decision_claim_evidence',
    )
    op.drop_table('decision_claim_evidence')

    op.drop_index(
        op.f('ix_decision_claims_decision_run_id'), table_name='decision_claims'
    )
    op.drop_index('idx_decision_claims_run_status', table_name='decision_claims')
    op.drop_table('decision_claims')

    op.drop_index(
        op.f('ix_decision_evidences_decision_run_id'), table_name='decision_evidences'
    )
    op.drop_index('idx_decision_evidences_run_source', table_name='decision_evidences')
    op.drop_table('decision_evidences')
