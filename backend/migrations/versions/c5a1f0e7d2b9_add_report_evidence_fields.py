"""add report evidence fields

Revision ID: c5a1f0e7d2b9
Revises: b4f0c2d9e8a1
Create Date: 2026-06-26 00:00:01.000000

"""
from alembic import op
import sqlalchemy as sa

from migrations.safe_ops import SafeOperations


revision = 'c5a1f0e7d2b9'
down_revision = 'b4f0c2d9e8a1'
branch_labels = None
depends_on = None


def upgrade():
    safe_op = SafeOperations(op)
    safe_op.add_column('leader_agent_results', sa.Column('raw_tool_results', sa.JSON(), nullable=True))
    safe_op.add_column('leader_agent_results', sa.Column('evidence_map', sa.JSON(), nullable=True))
    safe_op.add_column('leader_final_reports', sa.Column('evidence_map', sa.JSON(), nullable=True))


def downgrade():
    op.drop_column('leader_final_reports', 'evidence_map')
    op.drop_column('leader_agent_results', 'evidence_map')
    op.drop_column('leader_agent_results', 'raw_tool_results')
