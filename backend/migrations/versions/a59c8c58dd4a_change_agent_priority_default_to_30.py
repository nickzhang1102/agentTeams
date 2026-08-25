"""change_agent_priority_default_to_30

Revision ID: a59c8c58dd4a
Revises: b5c6d7e8f9a0
Create Date: 2026-06-25 11:00:33.079390

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a59c8c58dd4a'
down_revision = 'b5c6d7e8f9a0'
branch_labels = None
depends_on = None


def upgrade():
    # 将 agent_configs.priority 的默认值从 0 改为 30（第3排）
    op.alter_column('agent_configs', 'priority',
               existing_type=sa.Integer(),
               server_default='30',
               existing_server_default='0')


def downgrade():
    op.alter_column('agent_configs', 'priority',
               existing_type=sa.Integer(),
               server_default='0',
               existing_server_default='30')
