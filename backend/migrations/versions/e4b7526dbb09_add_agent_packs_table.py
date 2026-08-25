"""add_agent_packs_table

Revision ID: e4b7526dbb09
Revises: c5e8a1b2d3f4
Create Date: 2026-06-22 18:43:24.992813

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from migrations.safe_ops import SafeOperations

# revision identifiers, used by Alembic.
revision = 'e4b7526dbb09'
down_revision = 'c5e8a1b2d3f4'
branch_labels = None
depends_on = None


def upgrade():
    safe_op = SafeOperations(op)
    safe_op.create_table('agent_packs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('is_system', sa.Boolean(), nullable=False),
        sa.Column('creator_id', sa.Integer(), nullable=True),
        sa.Column('agents', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('tags', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('usage_count', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['creator_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', 'creator_id', name='uq_agent_pack_name_creator'),
    )
    safe_op.create_index('idx_agent_pack_category_system', 'agent_packs', ['category', 'is_system'], unique=False)
    safe_op.create_index('idx_agent_pack_creator', 'agent_packs', ['creator_id'], unique=False)


def downgrade():
    op.drop_index('idx_agent_pack_creator', table_name='agent_packs')
    op.drop_index('idx_agent_pack_category_system', table_name='agent_packs')
    op.drop_constraint('uq_agent_pack_name_creator', 'agent_packs', type_='unique')
    op.drop_table('agent_packs')
