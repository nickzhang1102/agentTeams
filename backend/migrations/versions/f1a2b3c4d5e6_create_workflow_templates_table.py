"""create_workflow_templates_table

Revision ID: f1a2b3c4d5e6
Revises: e4b7526dbb09
Create Date: 2026-06-22 22:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from migrations.safe_ops import SafeOperations

# revision identifiers, used by Alembic.
revision = 'f1a2b3c4d5e6'
down_revision = 'e4b7526dbb09'
branch_labels = None
depends_on = None


def upgrade():
    safe_op = SafeOperations(op)
    safe_op.create_table('workflow_templates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('is_system', sa.Boolean(), nullable=False),
        sa.Column('creator_id', sa.Integer(), nullable=True),
        sa.Column('pack_id', sa.Integer(), nullable=True),
        sa.Column('agents', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('skip_assessment', sa.Boolean(), nullable=False),
        sa.Column('assessment_threshold', sa.Integer(), nullable=False),
        sa.Column('system_prompt_addition', sa.Text(), nullable=True),
        sa.Column('usage_count', sa.Integer(), nullable=False),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['creator_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['pack_id'], ['agent_packs.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', 'creator_id', name='uq_workflow_template_name_creator'),
    )
    safe_op.create_index('idx_workflow_template_category_system', 'workflow_templates', ['category', 'is_system'], unique=False)
    safe_op.create_index('idx_workflow_template_creator', 'workflow_templates', ['creator_id'], unique=False)


def downgrade():
    op.drop_index('idx_workflow_template_creator', table_name='workflow_templates')
    op.drop_index('idx_workflow_template_category_system', table_name='workflow_templates')
    op.drop_constraint('uq_workflow_template_name_creator', 'workflow_templates', type_='unique')
    op.drop_table('workflow_templates')
