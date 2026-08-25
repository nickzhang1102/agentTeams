"""add oncopath launch and embed tables

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-07-08 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from migrations.safe_ops import SafeOperations


# revision identifiers, used by Alembic.
revision = 'e7f8a9b0c1d2'
down_revision = 'd6e7f8a9b0c1'
branch_labels = None
depends_on = None


def upgrade():
    safe_op = SafeOperations(op)
    safe_op.create_table(
        'oncopath_launches',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(length=50), nullable=False),
        sa.Column('request_id', sa.String(length=100), nullable=False),
        sa.Column('source_user_id', sa.String(length=100), nullable=True),
        sa.Column('source_patient_id', sa.String(length=100), nullable=True),
        sa.Column('source_conversation_id', sa.String(length=100), nullable=True),
        sa.Column('agentteams_conversation_id', sa.Integer(), nullable=True),
        sa.Column('agentteams_leader_session_id', sa.Integer(), nullable=True),
        sa.Column('usage_record_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('error_code', sa.String(length=100), nullable=True),
        sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['agentteams_conversation_id'], ['conversations.id']),
        sa.ForeignKeyConstraint(['agentteams_leader_session_id'], ['leader_sessions.id']),
        sa.ForeignKeyConstraint(['usage_record_id'], ['usage_records.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source', 'request_id', name='uq_oncopath_launch_source_request'),
    )
    safe_op.create_index('ix_oncopath_launches_agentteams_conversation_id', 'oncopath_launches', ['agentteams_conversation_id'], unique=False)
    safe_op.create_index('ix_oncopath_launches_agentteams_leader_session_id', 'oncopath_launches', ['agentteams_leader_session_id'], unique=False)
    safe_op.create_index('ix_oncopath_launches_status', 'oncopath_launches', ['status'], unique=False)
    safe_op.create_index('ix_oncopath_launches_usage_record_id', 'oncopath_launches', ['usage_record_id'], unique=False)
    safe_op.create_index('idx_oncopath_launch_source_conversation', 'oncopath_launches', ['source', 'source_conversation_id'], unique=False)

    safe_op.create_table(
        'oncopath_embed_tokens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('conversation_id', sa.Integer(), nullable=False),
        sa.Column('leader_session_id', sa.Integer(), nullable=True),
        sa.Column('source', sa.String(length=50), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id']),
        sa.ForeignKeyConstraint(['leader_session_id'], ['leader_sessions.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    safe_op.create_index('ix_oncopath_embed_tokens_conversation_id', 'oncopath_embed_tokens', ['conversation_id'], unique=False)
    safe_op.create_index('ix_oncopath_embed_tokens_expires_at', 'oncopath_embed_tokens', ['expires_at'], unique=False)
    safe_op.create_index('ix_oncopath_embed_tokens_leader_session_id', 'oncopath_embed_tokens', ['leader_session_id'], unique=False)
    safe_op.create_index('ix_oncopath_embed_tokens_source', 'oncopath_embed_tokens', ['source'], unique=False)
    safe_op.create_index('ix_oncopath_embed_tokens_token_hash', 'oncopath_embed_tokens', ['token_hash'], unique=True)


def downgrade():
    op.drop_index('ix_oncopath_embed_tokens_token_hash', table_name='oncopath_embed_tokens')
    op.drop_index('ix_oncopath_embed_tokens_source', table_name='oncopath_embed_tokens')
    op.drop_index('ix_oncopath_embed_tokens_leader_session_id', table_name='oncopath_embed_tokens')
    op.drop_index('ix_oncopath_embed_tokens_expires_at', table_name='oncopath_embed_tokens')
    op.drop_index('ix_oncopath_embed_tokens_conversation_id', table_name='oncopath_embed_tokens')
    op.drop_table('oncopath_embed_tokens')

    op.drop_index('idx_oncopath_launch_source_conversation', table_name='oncopath_launches')
    op.drop_index('ix_oncopath_launches_usage_record_id', table_name='oncopath_launches')
    op.drop_index('ix_oncopath_launches_status', table_name='oncopath_launches')
    op.drop_index('ix_oncopath_launches_agentteams_leader_session_id', table_name='oncopath_launches')
    op.drop_index('ix_oncopath_launches_agentteams_conversation_id', table_name='oncopath_launches')
    op.drop_table('oncopath_launches')
