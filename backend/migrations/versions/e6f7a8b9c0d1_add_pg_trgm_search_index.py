"""add pg_trgm index for message search

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-06-06 20:00:00.000000

"""
from alembic import op


# revision identifiers, used by alembic.
revision = 'e6f7a8b9c0d1'
down_revision = 'd5e6f7a8b9c0'
branch_labels = None
depends_on = None


def upgrade():
    # 启用 pg_trgm 扩展（幂等）
    op.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')
    # 在 raw_content 上创建 GIN trigram 索引，加速 ILIKE 查询
    op.execute('CREATE INDEX IF NOT EXISTS ix_messages_raw_content_trgm ON messages USING gin (raw_content gin_trgm_ops)')


def downgrade():
    op.execute('DROP INDEX IF EXISTS ix_messages_raw_content_trgm')
