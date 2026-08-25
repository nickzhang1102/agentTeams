"""remove dead custom_instructions field from users

Revision ID: 489e09a8ebd5
Revises: d3cfb9455122
Create Date: 2026-06-20 19:13:52.589895

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '489e09a8ebd5'
down_revision = 'd3cfb9455122'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column('users', 'custom_instructions')


def downgrade():
    op.add_column('users', sa.Column('custom_instructions', sa.TEXT(), autoincrement=False, nullable=True))
