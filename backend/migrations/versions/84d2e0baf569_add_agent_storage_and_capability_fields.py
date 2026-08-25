"""add_agent_storage_and_capability_fields

Revision ID: 84d2e0baf569
Revises: 60f2450fefcb
Create Date: 2026-06-22 10:59:22.997527

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from migrations.safe_ops import SafeOperations

# revision identifiers, used by Alembic.
revision = '84d2e0baf569'
down_revision = '60f2450fefcb'
branch_labels = None
depends_on = None


def upgrade():
    safe_op = SafeOperations(op)
    # Agent 存储统一 + 能力声明字段
    safe_op.add_column('agent_configs', sa.Column('source', sa.String(length=20), server_default='file', nullable=False))
    safe_op.add_column('agent_configs', sa.Column('is_system', sa.Boolean(), server_default='true', nullable=False))
    safe_op.add_column('agent_configs', sa.Column('created_by', sa.Integer(), nullable=True))
    safe_op.add_column('agent_configs', sa.Column('content', sa.Text(), nullable=True))
    safe_op.add_column('agent_configs', sa.Column('role', sa.String(length=200), nullable=True))
    safe_op.add_column('agent_configs', sa.Column('persona', sa.Text(), nullable=True))
    safe_op.add_column('agent_configs', sa.Column('expertise', sa.Text(), nullable=True))
    safe_op.add_column('agent_configs', sa.Column('approach', sa.Text(), nullable=True))
    safe_op.add_column('agent_configs', sa.Column('capabilities', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    safe_op.add_column('agent_configs', sa.Column('skill_level', sa.Integer(), server_default='3', nullable=False))
    safe_op.add_column('agent_configs', sa.Column('tags', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    safe_op.add_column('agent_configs', sa.Column('preferred_contexts', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    safe_op.add_column('agent_configs', sa.Column('portrait_url', sa.String(length=500), nullable=True))
    safe_op.create_foreign_key('fk_agent_configs_created_by', 'agent_configs', 'users', ['created_by'], ['id'], ondelete='SET NULL')


def downgrade():
    op.drop_constraint('fk_agent_configs_created_by', 'agent_configs', type_='foreignkey')
    op.drop_column('agent_configs', 'portrait_url')
    op.drop_column('agent_configs', 'preferred_contexts')
    op.drop_column('agent_configs', 'tags')
    op.drop_column('agent_configs', 'skill_level')
    op.drop_column('agent_configs', 'capabilities')
    op.drop_column('agent_configs', 'approach')
    op.drop_column('agent_configs', 'expertise')
    op.drop_column('agent_configs', 'persona')
    op.drop_column('agent_configs', 'role')
    op.drop_column('agent_configs', 'content')
    op.drop_column('agent_configs', 'created_by')
    op.drop_column('agent_configs', 'is_system')
    op.drop_column('agent_configs', 'source')
