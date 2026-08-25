"""持久化本地集成访问治理操作状态

Revision ID: fd3e4f5a6b7c
Revises: fc2d3e4f5a6b
"""
from alembic import op
import sqlalchemy as sa

from migrations.safe_ops import SafeOperations


revision = 'fd3e4f5a6b7c'
down_revision = 'fc2d3e4f5a6b'
branch_labels = None
depends_on = None


def upgrade():
    safe_op = SafeOperations(op)
    safe_op.create_table(
        'integration_access_operations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('operation_id', sa.String(length=100), nullable=False),
        sa.Column('client_key', sa.String(length=50), nullable=False),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('request_id', sa.String(length=100), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False, server_default='requested'),
        sa.Column('reason', sa.String(length=500), nullable=True),
        sa.Column('revoked_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('remote_action', sa.String(length=30), nullable=False, server_default='not_implemented'),
        sa.Column('error_code', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'client_key', 'action', 'operation_id',
            name='uq_integration_access_operation_scope',
        ),
    )
    safe_op.create_index(
        'ix_integration_access_operations_client_key',
        'integration_access_operations', ['client_key'], unique=False,
    )
    safe_op.create_index(
        'idx_integration_access_operation_client_created',
        'integration_access_operations', ['client_key', 'created_at'], unique=False,
    )


def downgrade():
    op.drop_index('idx_integration_access_operation_client_created', table_name='integration_access_operations')
    op.drop_index('ix_integration_access_operations_client_key', table_name='integration_access_operations')
    op.drop_table('integration_access_operations')
