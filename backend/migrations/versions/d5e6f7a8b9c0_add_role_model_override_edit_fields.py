"""add role, model_override, edited_at, parent_message_id

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-06-06 19:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

from migrations.safe_ops import SafeOperations


# revision identifiers, used by alembic.
revision = 'd5e6f7a8b9c0'
down_revision = 'c4d5e6f7a8b9'
branch_labels = None
depends_on = None


def upgrade():
    safe_op = SafeOperations(op)

    # 1. users.role — RBAC 角色字段
    safe_op.add_column('users', sa.Column('role', sa.String(20), nullable=False, server_default='editor'))
    safe_op.create_index('ix_users_role', 'users', ['role'])

    # 2. conversations.model_override — 对话级模型覆盖
    safe_op.add_column('conversations', sa.Column('model_override', sa.String(100), nullable=True))

    # 3. messages.edited_at — 消息编辑时间
    safe_op.add_column('messages', sa.Column('edited_at', sa.DateTime(), nullable=True))

    # 4. messages.parent_message_id — 消息分支父节点
    safe_op.add_column('messages', sa.Column('parent_message_id', sa.Integer(), nullable=True))
    safe_op.create_foreign_key(
        'fk_messages_parent_message_id',
        'messages', 'messages',
        ['parent_message_id'], ['id']
    )


def downgrade():
    op.drop_constraint('fk_messages_parent_message_id', 'messages', type_='foreignkey')
    op.drop_column('messages', 'parent_message_id')
    op.drop_column('messages', 'edited_at')
    op.drop_column('conversations', 'model_override')
    op.drop_index('ix_users_role', 'users')
    op.drop_column('users', 'role')
