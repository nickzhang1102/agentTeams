"""add token_version to users

Revision ID: b3c4d5e6f7a8
Revises: a1b2c3d4e5f6
Create Date: 2026-06-06 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

from migrations.safe_ops import SafeOperations


# revision identifiers, used by alembic.
revision = 'b3c4d5e6f7a8'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    safe_op = SafeOperations(op)
    safe_op.add_column('users', sa.Column('token_version', sa.Integer(), nullable=False, server_default='0'))


def downgrade():
    op.drop_column('users', 'token_version')
