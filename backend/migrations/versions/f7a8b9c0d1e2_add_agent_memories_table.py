"""add agent_memories table for user long-term memory

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-06-09 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from migrations.safe_ops import SafeOperations


# revision identifiers, used by alembic.
revision = 'f7a8b9c0d1e2'
down_revision = 'e6f7a8b9c0d1'
branch_labels = None
depends_on = None


def upgrade():
    safe_op = SafeOperations(op)
    safe_op.create_table(
        'agent_memories',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('metadata_', JSONB(), nullable=False, server_default='{}'),
        sa.Column('source_conversation_id', sa.Integer(), sa.ForeignKey('conversations.id'), nullable=True),
        sa.Column('source_message_id', sa.Integer(), sa.ForeignKey('messages.id'), nullable=True),
        sa.Column('importance', sa.Float(), nullable=False, server_default='0.5'),
        sa.Column('embedding', sa.Text(), nullable=True),  # 预留 pgvector，第一阶段不用
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # 索引
    safe_op.create_index('idx_memory_user_created', 'agent_memories', ['user_id', 'created_at'])
    safe_op.create_index('idx_memory_user_importance', 'agent_memories', ['user_id', sa.text('importance DESC')])
    # GIN 索引支持 JSONB @> 查询
    op.execute('CREATE INDEX IF NOT EXISTS idx_memory_metadata_type ON agent_memories USING gin (metadata_)')


def downgrade():
    op.drop_index('idx_memory_metadata_type', table_name='agent_memories')
    op.drop_index('idx_memory_user_importance', table_name='agent_memories')
    op.drop_index('idx_memory_user_created', table_name='agent_memories')
    op.drop_table('agent_memories')
