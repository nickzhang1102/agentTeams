"""add_backfill_tasks_table

Revision ID: c5e8a1b2d3f4
Revises: b4d4f03a470e
Create Date: 2026-06-22 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

from migrations.safe_ops import SafeOperations

# revision identifiers, used by Alembic.
revision = 'c5e8a1b2d3f4'
down_revision = 'b4d4f03a470e'
branch_labels = None
depends_on = None


def upgrade():
    safe_op = SafeOperations(op)
    safe_op.create_table(
        'backfill_tasks',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('task_id', sa.String(8), unique=True, nullable=False, index=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='running'),
        sa.Column('total', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('processed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('updated', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('skipped', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_table('backfill_tasks')
