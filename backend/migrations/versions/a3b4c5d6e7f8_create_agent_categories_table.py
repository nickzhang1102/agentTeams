"""create agent_categories table

Revision ID: a3b4c5d6e7f8
Revises: 7c1e4f5a6b2d
Create Date: 2026-06-27 22:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

from migrations.safe_ops import SafeOperations

# revision identifiers, used by Alembic.
revision = 'a3b4c5d6e7f8'
down_revision = '7c1e4f5a6b2d'
branch_labels = None
depends_on = None

# 种子数据：与 agent_category_service.CATEGORY_META 一致
SEED_ROWS = [
    {'key': 'medical',     'name': '医疗专家', 'icon': '🩺', 'color': '#e74c3c', 'sort_order': 1},
    {'key': 'business',    'name': '商业角色', 'icon': '💼', 'color': '#3498db', 'sort_order': 2},
    {'key': 'finance',     'name': '期货公司', 'icon': '📈', 'color': '#2ecc71', 'sort_order': 3},
    {'key': 'securities',  'name': '证券公司', 'icon': '📊', 'color': '#9b59b6', 'sort_order': 4},
]


def upgrade():
    safe_op = SafeOperations(op)
    safe_op.create_table(
        'agent_categories',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('key', sa.String(50), unique=True, nullable=False, index=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('icon', sa.String(10), nullable=True),
        sa.Column('color', sa.String(20), nullable=True),
        sa.Column('sort_order', sa.Integer(), server_default='0', nullable=False),
        sa.Column('is_system', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # Seed CATEGORY_META 数据
    conn = op.get_bind()
    for row in SEED_ROWS:
        conn.execute(
            sa.text(
                "INSERT INTO agent_categories (key, name, icon, color, sort_order, is_system) "
                "VALUES (:key, :name, :icon, :color, :sort_order, true)"
            ),
            row,
        )


def downgrade():
    op.drop_table('agent_categories')
