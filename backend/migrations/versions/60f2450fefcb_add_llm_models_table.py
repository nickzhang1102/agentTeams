"""add llm_models table

Revision ID: 60f2450fefcb
Revises: 8fbedefd5fa5
Create Date: 2026-06-20

"""
from alembic import op
import sqlalchemy as sa

from migrations.safe_ops import SafeOperations

# revision identifiers, used by alembic.
revision = '60f2450fefcb'
down_revision = '8fbedefd5fa5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    safe_op = SafeOperations(op)
    safe_op.create_table(
        'llm_models',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('model_id', sa.String(100), unique=True, nullable=False),
        sa.Column('display_name', sa.String(200), nullable=False),
        sa.Column('base_url', sa.String(500), nullable=False),
        sa.Column('api_key', sa.String(500), nullable=False),
        sa.Column('context_limit', sa.Integer(), nullable=False, server_default='128000'),
        sa.Column('max_output_tokens', sa.Integer(), nullable=False, server_default='32768'),
        sa.Column('provider', sa.String(100)),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_test_at', sa.DateTime()),
        sa.Column('last_test_ok', sa.Boolean()),
        sa.Column('last_test_error', sa.String(500)),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )
    safe_op.create_index('ix_llm_models_model_id', 'llm_models', ['model_id'])


def downgrade() -> None:
    op.drop_table('llm_models')
