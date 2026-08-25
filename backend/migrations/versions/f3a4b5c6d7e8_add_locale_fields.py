"""add locale persistence fields

Revision ID: f3a4b5c6d7e8
Revises: f2b3c4d5e6a7
Create Date: 2026-07-28 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

from migrations.safe_ops import SafeOperations


revision = 'f3a4b5c6d7e8'
down_revision = 'f2b3c4d5e6a7'
branch_labels = None
depends_on = None


def upgrade():
    safe = SafeOperations(op)
    default_locale = sa.text("'zh-CN'")

    safe.add_column(
        'users',
        sa.Column('preferred_locale', sa.String(length=10), nullable=False, server_default=default_locale),
    )
    safe.add_column(
        'conversations',
        sa.Column('default_locale', sa.String(length=10), nullable=False, server_default=default_locale),
    )
    safe.add_column('messages', sa.Column('content_locale', sa.String(length=10), nullable=True))
    safe.add_column(
        'leader_sessions',
        sa.Column('locale', sa.String(length=10), nullable=False, server_default=default_locale),
    )
    safe.add_column(
        'leader_agent_results',
        sa.Column('content_locale', sa.String(length=10), nullable=False, server_default=default_locale),
    )
    safe.add_column(
        'leader_final_reports',
        sa.Column('content_locale', sa.String(length=10), nullable=False, server_default=default_locale),
    )


def downgrade():
    op.drop_column('leader_final_reports', 'content_locale')
    op.drop_column('leader_agent_results', 'content_locale')
    op.drop_column('leader_sessions', 'locale')
    op.drop_column('messages', 'content_locale')
    op.drop_column('conversations', 'default_locale')
    op.drop_column('users', 'preferred_locale')
