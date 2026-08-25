"""在兼容性启动记录上持久化计费策略

Revision ID: f9c0d1e2f3a4
Revises: f8b9c0d1e2f3
"""
from alembic import op
import sqlalchemy as sa

from migrations.safe_ops import SafeOperations


revision = 'f9c0d1e2f3a4'
down_revision = 'f8b9c0d1e2f3'
branch_labels = None
depends_on = None


def upgrade():
    safe_op = SafeOperations(op)
    safe_op.add_column(
        'oncopath_launches',
        sa.Column('billing_policy', sa.String(length=50), nullable=True, server_default='per_launch'),
    )
    op.execute(
        "UPDATE oncopath_launches SET billing_policy = 'per_launch' "
        "WHERE billing_policy IS NULL"
    )
    op.alter_column(
        'oncopath_launches',
        'billing_policy',
        existing_type=sa.String(length=50),
        nullable=False,
        server_default='per_launch',
    )


def downgrade():
    op.drop_column('oncopath_launches', 'billing_policy')
