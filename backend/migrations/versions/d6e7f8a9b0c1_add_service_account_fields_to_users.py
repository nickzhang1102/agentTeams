"""add service account fields to users

Revision ID: d6e7f8a9b0c1
Revises: a3b4c5d6e7f8
Create Date: 2026-07-08 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

from migrations.safe_ops import SafeOperations


# revision identifiers, used by Alembic.
revision = 'd6e7f8a9b0c1'
down_revision = 'a3b4c5d6e7f8'
branch_labels = None
depends_on = None


def upgrade():
    safe_op = SafeOperations(op)
    safe_op.add_column(
        'users',
        sa.Column('account_type', sa.String(length=20), nullable=False, server_default='human'),
    )
    safe_op.add_column(
        'users',
        sa.Column('login_disabled', sa.Boolean(), nullable=False, server_default='false'),
    )
    safe_op.create_index('ix_users_account_type', 'users', ['account_type'], unique=False)
    safe_op.create_index('ix_users_login_disabled', 'users', ['login_disabled'], unique=False)


def downgrade():
    op.drop_index('ix_users_login_disabled', table_name='users')
    op.drop_index('ix_users_account_type', table_name='users')
    op.drop_column('users', 'login_disabled')
    op.drop_column('users', 'account_type')
