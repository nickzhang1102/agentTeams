"""在嵌入令牌上持久化集成客户端归属

Revision ID: fc2d3e4f5a6b
Revises: fb1c2d3e4f5a
"""
from alembic import op
import sqlalchemy as sa

from migrations.safe_ops import SafeOperations


revision = 'fc2d3e4f5a6b'
down_revision = 'fb1c2d3e4f5a'
branch_labels = None
depends_on = None


def upgrade():
    safe_op = SafeOperations(op)
    safe_op.add_column(
        'oncopath_embed_tokens',
        sa.Column('integration_client_key', sa.String(length=50), nullable=True, server_default='oncopath'),
    )
    op.execute(
        "UPDATE oncopath_embed_tokens SET integration_client_key = 'oncopath' "
        "WHERE integration_client_key IS NULL"
    )
    op.alter_column(
        'oncopath_embed_tokens',
        'integration_client_key',
        existing_type=sa.String(length=50),
        nullable=False,
        server_default='oncopath',
    )
    safe_op.create_index(
        'ix_oncopath_embed_tokens_integration_client_key',
        'oncopath_embed_tokens',
        ['integration_client_key'],
        unique=False,
    )


def downgrade():
    op.drop_index('ix_oncopath_embed_tokens_integration_client_key', table_name='oncopath_embed_tokens')
    op.drop_column('oncopath_embed_tokens', 'integration_client_key')
