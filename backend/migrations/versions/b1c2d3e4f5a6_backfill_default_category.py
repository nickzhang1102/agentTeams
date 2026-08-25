"""backfill default personal category for legacy users

Revision ID: b1c2d3e4f5a6
Revises: 5159c8bf2d21
Create Date: 2026-06-17

为本次知识库个人化改造前注册的老用户回填个人 default 分类。
新用户在注册流程（auth.py）中已自动创建；老用户缺该分类，
导致首页"加入我的知识库"（Home.vue，category='default'）入库被拒 400。
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'b1c2d3e4f5a6'
down_revision = '5159c8bf2d21'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 为每个尚无 default 个人分类的用户插入一条（幂等：NOT EXISTS 守卫）
    op.execute(sa.text("""
        INSERT INTO knowledge_categories
            (key, label, description, icon, sort_order, is_active, user_id, created_at, updated_at)
        SELECT
            'default', '未分类', '默认分类', 'Document', 0, true, u.id, now(), now()
        FROM users u
        WHERE NOT EXISTS (
            SELECT 1 FROM knowledge_categories kc
            WHERE kc.key = 'default' AND kc.user_id = u.id
        )
    """))


def downgrade() -> None:
    # 删除本次迁移回填的个人 default 分类（共享分类 user_id IS NULL 不动）
    op.execute(sa.text("""
        DELETE FROM knowledge_categories
        WHERE key = 'default' AND user_id IS NOT NULL
    """))
