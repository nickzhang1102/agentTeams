"""remove dead shared_with field from knowledge_documents

Revision ID: 2ba1c3410b4a
Revises: 489e09a8ebd5
Create Date: 2026-06-20 19:19:36.164660

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '2ba1c3410b4a'
down_revision = '489e09a8ebd5'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column('knowledge_documents', 'shared_with')


def downgrade():
    op.add_column('knowledge_documents', sa.Column('shared_with', sa.JSON(), autoincrement=False, nullable=True))
