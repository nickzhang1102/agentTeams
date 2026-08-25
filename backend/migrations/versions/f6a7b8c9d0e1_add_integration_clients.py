"""添加通用集成客户端

Revision ID: f6a7b8c9d0e1
Revises: f5c6d7e8a9b0
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from migrations.safe_ops import SafeOperations


revision = 'f6a7b8c9d0e1'
down_revision = 'f5c6d7e8a9b0'
branch_labels = None
depends_on = None


def upgrade():
    safe_op = SafeOperations(op)
    safe_op.create_table(
        'integration_clients',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('client_key', sa.String(length=50), nullable=False),
        sa.Column('display_name', sa.String(length=100), nullable=False),
        sa.Column('credential_hash', sa.String(length=128), nullable=True),
        sa.Column('service_account_id', sa.Integer(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('billing_policy', sa.String(length=50), nullable=False, server_default='per_launch'),
        sa.Column('capabilities_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['service_account_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        # client_key 的唯一性由下方唯一索引承载，与模型声明保持一致，
        # 不再重复创建同义的 UniqueConstraint。
    )
    safe_op.create_index('ix_integration_clients_client_key', 'integration_clients', ['client_key'], unique=True)
    safe_op.create_index('ix_integration_clients_enabled', 'integration_clients', ['enabled'], unique=False)
    safe_op.create_index('ix_integration_clients_service_account_id', 'integration_clients', ['service_account_id'], unique=False)


def downgrade():
    op.drop_index('ix_integration_clients_service_account_id', table_name='integration_clients')
    op.drop_index('ix_integration_clients_enabled', table_name='integration_clients')
    op.drop_index('ix_integration_clients_client_key', table_name='integration_clients')
    op.drop_table('integration_clients')
