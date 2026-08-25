"""移除用户侧商业化表（卡密、兑换尝试、购买订单）

用户侧计费与卡密体系随开源化整体移除；集成契约层的
usage_records / user_balances 保留不动。

Revision ID: a5b6c7d8e9f0
Revises: fe4f5a6b7c8d
Create Date: 2026-08-23
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a5b6c7d8e9f0'
down_revision = 'fe4f5a6b7c8d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 先删子表（FK 引用 cdkeys / users），再删父表
    op.drop_table('purchase_orders')
    op.drop_table('cdkey_redeem_attempts')
    op.drop_table('cdkeys')


def downgrade() -> None:
    # 按初始 schema（98736f6635e8）重建空表结构；历史数据不可恢复
    op.create_table(
        'cdkeys',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('code', sa.String(20), nullable=False),
        sa.Column('card_type', sa.String(20), nullable=False),
        sa.Column('times', sa.Integer(), nullable=False),
        sa.Column('price', sa.Numeric(10, 2), nullable=False),
        sa.Column('status', sa.String(20), server_default='unused'),
        sa.Column('used_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('used_at', sa.DateTime(), nullable=True),
        sa.Column('batch_no', sa.String(50), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_cdkeys_code', 'cdkeys', ['code'], unique=True)
    op.create_index('ix_cdkeys_status', 'cdkeys', ['status'], unique=False)
    op.create_index('ix_cdkeys_used_by', 'cdkeys', ['used_by'], unique=False)
    op.create_index('ix_cdkeys_batch_no', 'cdkeys', ['batch_no'], unique=False)

    op.create_table(
        'purchase_orders',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('cdkey_id', sa.Integer(), sa.ForeignKey('cdkeys.id'), nullable=True),
        sa.Column('order_type', sa.String(20), server_default='cdkey'),
        sa.Column('amount', sa.Numeric(10, 2), server_default='0.0'),
        sa.Column('times', sa.Integer(), server_default='0'),
        sa.Column('status', sa.String(20), server_default='completed'),
        sa.Column('remark', sa.String(200), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_purchase_orders_user_id', 'purchase_orders', ['user_id'], unique=False)
    op.create_index('ix_purchase_orders_cdkey_id', 'purchase_orders', ['cdkey_id'], unique=False)

    op.create_table(
        'cdkey_redeem_attempts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('attempt_code', sa.String(20), nullable=False),
        sa.Column('success', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('error_message', sa.String(200), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_cdkey_redeem_attempts_user_id', 'cdkey_redeem_attempts', ['user_id'], unique=False)
    op.create_index('ix_cdkey_redeem_attempts_ip_address', 'cdkey_redeem_attempts', ['ip_address'], unique=False)
    op.create_index('ix_cdkey_redeem_attempts_created_at', 'cdkey_redeem_attempts', ['created_at'], unique=False)
