"""在启动记录上持久化集成客户端归属

Revision ID: fb1c2d3e4f5a
Revises: fa0b1c2d3e4f
"""
from alembic import op
import sqlalchemy as sa

from migrations.safe_ops import SafeOperations


revision = 'fb1c2d3e4f5a'
down_revision = 'fa0b1c2d3e4f'
branch_labels = None
depends_on = None


def upgrade():
    safe_op = SafeOperations(op)
    safe_op.add_column(
        'oncopath_launches',
        sa.Column('integration_client_key', sa.String(length=50), nullable=True, server_default='oncopath'),
    )
    op.execute(
        "UPDATE oncopath_launches SET integration_client_key = 'oncopath' "
        "WHERE integration_client_key IS NULL"
    )
    op.alter_column(
        'oncopath_launches',
        'integration_client_key',
        existing_type=sa.String(length=50),
        nullable=False,
        server_default='oncopath',
    )
    safe_op.create_index(
        'ix_oncopath_launches_integration_client_key',
        'oncopath_launches',
        ['integration_client_key'],
        unique=False,
    )


def downgrade():
    op.drop_index('ix_oncopath_launches_integration_client_key', table_name='oncopath_launches')
    op.drop_column('oncopath_launches', 'integration_client_key')
