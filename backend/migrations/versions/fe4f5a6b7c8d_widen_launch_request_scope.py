"""加宽 OncoPath launch 请求作用域并收紧适配器声明

Revision ID: fe4f5a6b7c8d
Revises: fd3e4f5a6b7c
"""
from alembic import op
import sqlalchemy as sa

from migrations.safe_ops import SafeOperations


revision = 'fe4f5a6b7c8d'
down_revision = 'fd3e4f5a6b7c'
branch_labels = None
depends_on = None


def upgrade():
    safe_op = SafeOperations(op)
    # 幂等键加入本地归属：多个客户端租户共享同一 source 命名空间时，
    # 相同的外部 request-id 必须互不可见，而不是撞唯一约束或互相命中。
    op.drop_constraint(
        'uq_oncopath_launch_source_request',
        'oncopath_launches',
        type_='unique',
    )
    safe_op.create_unique_constraint(
        'uq_oncopath_launch_source_client_request',
        'oncopath_launches',
        ['source', 'integration_client_key', 'request_id'],
    )
    # 存储宽度覆盖外部契约上限（100）加 client 命名空间前缀（≤50+1），
    # 避免"合法外部 ID 因 client_key 长度被误拒"。
    op.alter_column(
        'oncopath_launches',
        'request_id',
        existing_type=sa.String(length=100),
        type_=sa.String(length=200),
        existing_nullable=False,
    )
    # 与模型对齐：adapter_key 不保留数据库级默认值，遗漏声明协议的
    # 写入必须显式失败（fail-closed），不得静默归入 oncopath 适配器。
    op.alter_column(
        'integration_clients',
        'adapter_key',
        existing_type=sa.String(length=50),
        server_default=None,
        existing_nullable=False,
    )


def downgrade():
    op.alter_column(
        'integration_clients',
        'adapter_key',
        existing_type=sa.String(length=50),
        server_default='oncopath',
        existing_nullable=False,
    )
    op.alter_column(
        'oncopath_launches',
        'request_id',
        existing_type=sa.String(length=200),
        type_=sa.String(length=100),
        existing_nullable=False,
    )
    op.drop_constraint(
        'uq_oncopath_launch_source_client_request',
        'oncopath_launches',
        type_='unique',
    )
    op.create_unique_constraint(
        'uq_oncopath_launch_source_request',
        'oncopath_launches',
        ['source', 'request_id'],
    )
