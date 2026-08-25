"""添加集成客户端凭证轮换窗口

Revision ID: fa0b1c2d3e4f
Revises: f9c0d1e2f3a4
"""
from alembic import op
import sqlalchemy as sa

from migrations.safe_ops import SafeOperations


revision = 'fa0b1c2d3e4f'
down_revision = 'f9c0d1e2f3a4'
branch_labels = None
depends_on = None


def upgrade():
    safe_op = SafeOperations(op)
    safe_op.add_column(
        'integration_clients',
        sa.Column('previous_credential_hash', sa.String(length=128), nullable=True),
    )
    safe_op.add_column(
        'integration_clients',
        sa.Column('previous_credential_expires_at', sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_column('integration_clients', 'previous_credential_expires_at')
    op.drop_column('integration_clients', 'previous_credential_hash')
