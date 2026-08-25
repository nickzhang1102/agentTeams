"""add durable Leader workflow cancellations

Revision ID: f5c6d7e8a9b0
Revises: f4b5c6d7e8a9
Create Date: 2026-08-13
"""

from alembic import op
import sqlalchemy as sa

from migrations.safe_ops import SafeOperations


revision = 'f5c6d7e8a9b0'
down_revision = 'f4b5c6d7e8a9'
branch_labels = None
depends_on = None


def upgrade():
    safe_op = SafeOperations(op)
    safe_op.create_table(
        'leader_workflow_cancellations',
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column(
            'reason',
            sa.String(length=100),
            nullable=False,
            server_default='user_requested',
        ),
        sa.Column(
            'requested_at',
            sa.DateTime(),
            nullable=False,
            server_default=sa.text('CURRENT_TIMESTAMP'),
        ),
        sa.PrimaryKeyConstraint('session_id'),
    )
    safe_op.create_index(
        'ix_leader_workflow_cancellations_requested_at',
        'leader_workflow_cancellations',
        ['requested_at'],
        unique=False,
    )


def downgrade():
    op.drop_index(
        'ix_leader_workflow_cancellations_requested_at',
        table_name='leader_workflow_cancellations',
    )
    op.drop_table('leader_workflow_cancellations')
