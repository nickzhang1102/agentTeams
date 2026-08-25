"""add original_filename to knowledge_documents

Revision ID: a1b2c3d4e5f6
Revises: 98736f6635e8
Create Date: 2026-06-04 17:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

from migrations.safe_ops import SafeOperations


# revision identifiers, used by alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '98736f6635e8'
branch_labels = None
depends_on = None


def upgrade():
    safe_op = SafeOperations(op)
    safe_op.add_column('knowledge_documents', sa.Column('original_filename', sa.String(500), nullable=True))


def downgrade():
    op.drop_column('knowledge_documents', 'original_filename')
