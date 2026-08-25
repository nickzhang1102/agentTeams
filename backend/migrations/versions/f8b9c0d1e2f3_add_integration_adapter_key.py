"""为集成客户端添加稳定的适配器密钥

Revision ID: f8b9c0d1e2f3
Revises: f6a7b8c9d0e1
"""
from alembic import op
import sqlalchemy as sa

from migrations.safe_ops import SafeOperations


revision = 'f8b9c0d1e2f3'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade():
    safe_op = SafeOperations(op)
    safe_op.add_column(
        'integration_clients',
        sa.Column('adapter_key', sa.String(length=50), nullable=True, server_default='oncopath'),
    )
    op.execute(
        "UPDATE integration_clients SET adapter_key = 'oncopath' "
        "WHERE adapter_key IS NULL"
    )
    op.alter_column(
        'integration_clients',
        'adapter_key',
        existing_type=sa.String(length=50),
        nullable=False,
        server_default='oncopath',
    )
    safe_op.create_index(
        'ix_integration_clients_adapter_key',
        'integration_clients',
        ['adapter_key'],
        unique=False,
    )


def downgrade():
    op.drop_index('ix_integration_clients_adapter_key', table_name='integration_clients')
    op.drop_column('integration_clients', 'adapter_key')
