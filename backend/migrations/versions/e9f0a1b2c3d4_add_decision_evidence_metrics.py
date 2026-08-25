"""add decision evidence quality metrics

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
Create Date: 2026-08-04
"""

from alembic import op
import sqlalchemy as sa

from migrations.safe_ops import SafeOperations


revision = 'e9f0a1b2c3d4'
down_revision = 'd8e9f0a1b2c3'
branch_labels = None
depends_on = None


def upgrade():
    safe_op = SafeOperations(op)
    safe_op.add_column(
        'decision_claims',
        sa.Column('evidence_ref_count', sa.Integer(), nullable=False, server_default='0'),
    )
    safe_op.add_column(
        'decision_claims',
        sa.Column(
            'resolved_evidence_ref_count',
            sa.Integer(),
            nullable=False,
            server_default='0',
        ),
    )
    op.create_check_constraint(
        'ck_decision_claims_evidence_ref_counts',
        'decision_claims',
        'evidence_ref_count >= 0 AND resolved_evidence_ref_count >= 0 '
        'AND resolved_evidence_ref_count <= evidence_ref_count',
    )

    safe_op.create_table(
        'decision_evidence_metrics',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('decision_run_id', sa.BigInteger(), nullable=False),
        sa.Column('evidence_candidates_total', sa.Integer(), nullable=False),
        sa.Column('evidence_cited_total', sa.Integer(), nullable=False),
        sa.Column('evidence_refs_total', sa.Integer(), nullable=False),
        sa.Column('evidence_refs_resolved_total', sa.Integer(), nullable=False),
        sa.Column('evidence_ref_resolvable_ratio', sa.Float(), nullable=True),
        sa.Column('supported_claim_ratio', sa.Float(), nullable=True),
        sa.Column('unique_source_count', sa.Integer(), nullable=False),
        sa.Column('snippet_only_count', sa.Integer(), nullable=False),
        sa.Column('evidence_context_dropped_count', sa.Integer(), nullable=False),
        sa.Column('evidence_detail_load_failure_count', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            'evidence_candidates_total >= 0 AND evidence_cited_total >= 0 '
            'AND evidence_refs_total >= 0 AND evidence_refs_resolved_total >= 0 '
            'AND unique_source_count >= 0 AND snippet_only_count >= 0 '
            'AND evidence_context_dropped_count >= 0 '
            'AND evidence_detail_load_failure_count >= 0',
            name='ck_decision_evidence_metrics_nonnegative',
        ),
        sa.CheckConstraint(
            'evidence_refs_resolved_total <= evidence_refs_total',
            name='ck_decision_evidence_metrics_refs_resolved',
        ),
        sa.CheckConstraint(
            'evidence_ref_resolvable_ratio IS NULL OR '
            '(evidence_ref_resolvable_ratio >= 0 AND evidence_ref_resolvable_ratio <= 1)',
            name='ck_decision_evidence_metrics_ref_ratio',
        ),
        sa.CheckConstraint(
            'supported_claim_ratio IS NULL OR '
            '(supported_claim_ratio >= 0 AND supported_claim_ratio <= 1)',
            name='ck_decision_evidence_metrics_claim_ratio',
        ),
        sa.ForeignKeyConstraint(
            ['decision_run_id'], ['decision_runs.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('decision_run_id'),
    )


def downgrade():
    op.drop_table('decision_evidence_metrics')
    op.drop_constraint(
        'ck_decision_claims_evidence_ref_counts',
        'decision_claims',
        type_='check',
    )
    op.drop_column('decision_claims', 'resolved_evidence_ref_count')
    op.drop_column('decision_claims', 'evidence_ref_count')
