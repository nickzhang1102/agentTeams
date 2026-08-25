"""LeaderSession 增加 assessment_threshold 和 system_prompt_addition

Revision ID: b5c6d7e8f9a0
Revises: a2b3c4d5e6f7
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa

from migrations.safe_ops import SafeOperations

revision = 'b5c6d7e8f9a0'
down_revision = 'a2b3c4d5e6f7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    safe_op = SafeOperations(op)
    safe_op.add_column(
        'leader_sessions',
        sa.Column('assessment_threshold', sa.Integer(), nullable=False, server_default='60'),
    )
    safe_op.add_column(
        'leader_sessions',
        sa.Column('system_prompt_addition', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('leader_sessions', 'system_prompt_addition')
    op.drop_column('leader_sessions', 'assessment_threshold')
