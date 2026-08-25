"""add structured report summary fields

Revision ID: b4f0c2d9e8a1
Revises: 94dcd0b602a2
Create Date: 2026-06-26 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

from migrations.safe_ops import SafeOperations


revision = 'b4f0c2d9e8a1'
down_revision = '94dcd0b602a2'
branch_labels = None
depends_on = None


def upgrade():
    safe_op = SafeOperations(op)
    safe_op.add_column('leader_agent_results', sa.Column('summary', sa.JSON(), nullable=True))
    safe_op.add_column('leader_agent_results', sa.Column('structured_report', sa.JSON(), nullable=True))
    safe_op.add_column('leader_final_reports', sa.Column('executive_summary', sa.JSON(), nullable=True))
    safe_op.add_column('leader_final_reports', sa.Column('structured_report', sa.JSON(), nullable=True))


def downgrade():
    op.drop_column('leader_final_reports', 'structured_report')
    op.drop_column('leader_final_reports', 'executive_summary')
    op.drop_column('leader_agent_results', 'structured_report')
    op.drop_column('leader_agent_results', 'summary')
