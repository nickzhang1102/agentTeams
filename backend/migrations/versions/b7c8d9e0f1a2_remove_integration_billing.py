"""移除集成路径计费残留（开源自部署简化）

删除 user_balances / usage_records 两表，以及
decision_runs.usage_record_id、oncopath_launches.usage_record_id、
oncopath_launches.billing_policy、integration_clients.billing_policy
四个计费列。服务账户、幂等与 embed 契约不受影响。

Revision ID: b7c8d9e0f1a2
Revises: a5b6c7d8e9f0
Create Date: 2026-08-23
"""
from alembic import op
import sqlalchemy as sa

from migrations.safe_ops import SafeOperations


revision = 'b7c8d9e0f1a2'
down_revision = 'a5b6c7d8e9f0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    safe_op = SafeOperations(op)
    # 1. 先删引用 usage_records 的外键列（含索引/唯一约束）
    #    历史迁移未显式命名这些约束，PostgreSQL 自动命名为
    #    <table>_<col>_key / <table>_<col>_fkey。
    safe_op.drop_constraint_if_exists(
        'decision_runs',
        'decision_runs_usage_record_id_key',
        type_='unique',
        local_cols=['usage_record_id'],
    )
    safe_op.drop_constraint_if_exists(
        'decision_runs',
        'decision_runs_usage_record_id_fkey',
        type_='foreignkey',
        local_cols=['usage_record_id'],
        referent_table='usage_records',
        remote_cols=['id'],
    )
    safe_op.drop_column_if_exists('decision_runs', 'usage_record_id')

    safe_op.drop_index_if_exists(
        'ix_oncopath_launches_usage_record_id',
        'oncopath_launches',
        columns=['usage_record_id'],
    )
    safe_op.drop_constraint_if_exists(
        'oncopath_launches',
        'oncopath_launches_usage_record_id_fkey',
        type_='foreignkey',
        local_cols=['usage_record_id'],
        referent_table='usage_records',
        remote_cols=['id'],
    )
    safe_op.drop_column_if_exists('oncopath_launches', 'usage_record_id')
    # billing_policy 快照随计费语义一并移除
    safe_op.drop_column_if_exists('oncopath_launches', 'billing_policy')

    safe_op.drop_column_if_exists('integration_clients', 'billing_policy')

    # 2. 再删子表（usage_records 被 decision_runs/oncopath_launches 引用，
    #    此时引用已解除），最后删独立的 user_balances
    safe_op.drop_table_if_exists('usage_records')
    safe_op.drop_table_if_exists('user_balances')


def downgrade() -> None:
    # 按初始 schema（98736f6635e8）与后续迁移重建表结构；
    # 历史计量数据不可恢复。
    safe_op = SafeOperations(op)
    safe_op.create_table(
        'user_balances',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('balance', sa.Integer(), nullable=False),
        sa.Column('total_purchased', sa.Integer(), nullable=False),
        sa.Column('total_used', sa.Integer(), nullable=False),
        sa.Column('total_gifted', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_user_balances_user_id_users'),
        sa.PrimaryKeyConstraint('id'),
    )
    safe_op.create_index('ix_user_balances_user_id', 'user_balances', ['user_id'], unique=True)

    safe_op.create_table(
        'usage_records',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('conversation_id', sa.Integer(), nullable=True),
        sa.Column('leader_session_id', sa.Integer(), nullable=True),
        sa.Column('times_used', sa.Integer(), nullable=False),
        sa.Column('tokens_used', sa.Integer(), nullable=True),
        sa.Column('cost_estimate', sa.Numeric(10, 4), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('refund_reason', sa.String(length=200), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], name='fk_usage_records_conversation_id_conversations'),
        sa.ForeignKeyConstraint(['leader_session_id'], ['leader_sessions.id'], name='fk_usage_records_leader_session_id_leader_sessions'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_usage_records_user_id_users'),
        sa.PrimaryKeyConstraint('id'),
    )
    safe_op.create_index('ix_usage_records_user_id', 'usage_records', ['user_id'], unique=False)
    safe_op.create_index('ix_usage_records_conversation_id', 'usage_records', ['conversation_id'], unique=False)
    safe_op.create_index('ix_usage_records_leader_session_id', 'usage_records', ['leader_session_id'], unique=False)
    safe_op.create_index('idx_usage_user_created', 'usage_records', ['user_id', 'created_at'], unique=False)
    safe_op.create_index('idx_usage_status', 'usage_records', ['status'], unique=False)

    safe_op.add_column(
        'integration_clients',
        sa.Column('billing_policy', sa.String(length=50), nullable=False, server_default='per_launch'),
    )
    safe_op.add_column(
        'oncopath_launches',
        sa.Column('billing_policy', sa.String(length=50), nullable=False, server_default='per_launch'),
    )
    safe_op.add_column(
        'oncopath_launches',
        sa.Column('usage_record_id', sa.Integer(), nullable=True),
    )
    safe_op.create_index('ix_oncopath_launches_usage_record_id', 'oncopath_launches', ['usage_record_id'], unique=False)
    safe_op.create_foreign_key(
        'oncopath_launches_usage_record_id_fkey',
        'oncopath_launches', 'usage_records',
        ['usage_record_id'], ['id'],
    )

    safe_op.add_column(
        'decision_runs',
        sa.Column('usage_record_id', sa.Integer(), nullable=True),
    )
    safe_op.create_unique_constraint('decision_runs_usage_record_id_key', 'decision_runs', ['usage_record_id'])
    safe_op.create_foreign_key(
        'decision_runs_usage_record_id_fkey',
        'decision_runs', 'usage_records',
        ['usage_record_id'], ['id'],
    )
