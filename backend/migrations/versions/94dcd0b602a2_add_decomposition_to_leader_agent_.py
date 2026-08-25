"""add_decomposition_to_leader_agent_results

Revision ID: 94dcd0b602a2
Revises: a59c8c58dd4a
Create Date: 2026-06-25 18:47:44.914285

"""
from alembic import op
import sqlalchemy as sa

from migrations.safe_ops import SafeOperations

# revision identifiers, used by Alembic.
revision = '94dcd0b602a2'
down_revision = 'a59c8c58dd4a'
branch_labels = None
depends_on = None


def upgrade():
    safe_op = SafeOperations(op)
    safe_op.add_column('leader_agent_results', sa.Column('decomposition', sa.JSON(), nullable=True))


def downgrade():
    op.drop_column('leader_agent_results', 'decomposition')
