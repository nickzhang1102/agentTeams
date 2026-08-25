"""统一修复：JSON→JSONB + 部分唯一索引

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'a2b3c4d5e6f7'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Message.content JSON → JSONB（支持 JSONB 索引和操作符）
    op.alter_column(
        'messages', 'content',
        type_=JSONB,
        postgresql_using='content::jsonb',
        existing_nullable=True,
    )

    # 2. ToolCallLog.tool_input/tool_output JSON → JSONB
    op.alter_column(
        'tool_call_logs', 'tool_input',
        type_=JSONB,
        postgresql_using='tool_input::jsonb',
        existing_nullable=True,
    )
    op.alter_column(
        'tool_call_logs', 'tool_output',
        type_=JSONB,
        postgresql_using='tool_output::jsonb',
        existing_nullable=True,
    )

    # 3. 部分唯一索引：系统 Pack 同名防重（NULL creator_id 时 UNIQUE 失效）
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_pack_name_system
        ON agent_packs (name)
        WHERE creator_id IS NULL AND is_system = true
    """)

    # 4. 部分唯一索引：系统 Template 同名防重
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_workflow_template_name_system
        ON workflow_templates (name)
        WHERE creator_id IS NULL AND is_system = true
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_workflow_template_name_system")
    op.execute("DROP INDEX IF EXISTS uq_agent_pack_name_system")
    op.alter_column(
        'tool_call_logs', 'tool_output',
        type_=sa.JSON,
        postgresql_using='tool_output::json',
        existing_nullable=True,
    )
    op.alter_column(
        'tool_call_logs', 'tool_input',
        type_=sa.JSON,
        postgresql_using='tool_input::json',
        existing_nullable=True,
    )
    op.alter_column(
        'messages', 'content',
        type_=sa.JSON,
        postgresql_using='content::json',
        existing_nullable=True,
    )
