"""add content translations

Revision ID: b6c7d8e9f0a1
Revises: a4b5c6d7e8f9
Create Date: 2026-07-31 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from migrations.safe_ops import SafeOperations


revision = 'b6c7d8e9f0a1'
down_revision = 'a4b5c6d7e8f9'
branch_labels = None
depends_on = None


def upgrade():
    safe_op = SafeOperations(op)
    safe_op.create_table(
        'content_translations',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('conversation_id', sa.Integer(), nullable=False),
        sa.Column('source_type', sa.String(length=32), nullable=False),
        sa.Column('source_id', sa.BigInteger(), nullable=False),
        sa.Column('source_hash', sa.String(length=64), nullable=False),
        sa.Column('source_locale', sa.String(length=10), nullable=False),
        sa.Column('target_locale', sa.String(length=10), nullable=False),
        sa.Column(
            'translated_payload',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            'status',
            sa.String(length=16),
            server_default='pending',
            nullable=False,
        ),
        sa.Column('error_code', sa.String(length=32), nullable=True),
        sa.Column('model_id', sa.String(length=100), nullable=True),
        sa.Column(
            'input_tokens',
            sa.Integer(),
            server_default='0',
            nullable=False,
        ),
        sa.Column(
            'output_tokens',
            sa.Integer(),
            server_default='0',
            nullable=False,
        ),
        sa.Column(
            'attempt_count',
            sa.Integer(),
            server_default='0',
            nullable=False,
        ),
        sa.Column('lease_owner', sa.String(length=64), nullable=True),
        sa.Column('lease_expires_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "source_type IN ('message', 'leader_agent_result', "
            "'leader_final_report')",
            name='ck_content_translation_source_type',
        ),
        sa.CheckConstraint(
            "source_locale IN ('zh-CN', 'en-US')",
            name='ck_content_translation_source_locale',
        ),
        sa.CheckConstraint(
            "target_locale IN ('zh-CN', 'en-US')",
            name='ck_content_translation_target_locale',
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'ready', 'failed')",
            name='ck_content_translation_status',
        ),
        sa.ForeignKeyConstraint(
            ['conversation_id'],
            ['conversations.id'],
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['user_id'],
            ['users.id'],
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'source_type',
            'source_id',
            'target_locale',
            'source_hash',
            name='uq_content_translation_source_target_hash',
        ),
    )
    safe_op.create_index(
        'ix_content_translations_user_id',
        'content_translations',
        ['user_id'],
        unique=False,
    )
    safe_op.create_index(
        'ix_content_translations_conversation_id',
        'content_translations',
        ['conversation_id'],
        unique=False,
    )
    safe_op.create_index(
        'idx_content_translation_source',
        'content_translations',
        ['source_type', 'source_id'],
        unique=False,
    )
    safe_op.create_index(
        'idx_content_translation_recovery',
        'content_translations',
        ['status', 'lease_expires_at'],
        unique=False,
    )


def downgrade():
    op.drop_table('content_translations')
