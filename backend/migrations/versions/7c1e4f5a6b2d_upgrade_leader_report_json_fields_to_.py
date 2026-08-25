"""upgrade leader report JSON fields to JSONB

Revision ID: 7c1e4f5a6b2d
Revises: c5a1f0e7d2b9
Create Date: 2026-06-27 08:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '7c1e4f5a6b2d'
down_revision = 'c5a1f0e7d2b9'
branch_labels = None
depends_on = None


def upgrade():
    _alter_json_to_jsonb('leader_agent_results', 'decomposition')
    _alter_json_to_jsonb('leader_agent_results', 'summary')
    _alter_json_to_jsonb('leader_agent_results', 'structured_report')
    _alter_json_to_jsonb('leader_agent_results', 'raw_tool_results')
    _alter_json_to_jsonb('leader_agent_results', 'evidence_map')
    _alter_json_to_jsonb('leader_final_reports', 'executive_summary')
    _alter_json_to_jsonb('leader_final_reports', 'structured_report')
    _alter_json_to_jsonb('leader_final_reports', 'evidence_map')


def downgrade():
    _alter_jsonb_to_json('leader_final_reports', 'evidence_map')
    _alter_jsonb_to_json('leader_final_reports', 'structured_report')
    _alter_jsonb_to_json('leader_final_reports', 'executive_summary')
    _alter_jsonb_to_json('leader_agent_results', 'evidence_map')
    _alter_jsonb_to_json('leader_agent_results', 'raw_tool_results')
    _alter_jsonb_to_json('leader_agent_results', 'structured_report')
    _alter_jsonb_to_json('leader_agent_results', 'summary')
    _alter_jsonb_to_json('leader_agent_results', 'decomposition')


def _alter_json_to_jsonb(table_name: str, column_name: str) -> None:
    op.alter_column(
        table_name,
        column_name,
        existing_type=sa.JSON(),
        type_=postgresql.JSONB(astext_type=sa.Text()),
        postgresql_using=f"{column_name}::jsonb",
        existing_nullable=True,
    )


def _alter_jsonb_to_json(table_name: str, column_name: str) -> None:
    op.alter_column(
        table_name,
        column_name,
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        type_=sa.JSON(),
        postgresql_using=f"{column_name}::json",
        existing_nullable=True,
    )
