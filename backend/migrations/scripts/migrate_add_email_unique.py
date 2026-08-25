"""
迁移脚本：为 User.email 添加唯一约束

解决的问题：
- D001: User.email 无唯一约束，允许多用户注册相同邮箱

执行步骤：
1. 检查是否存在重复邮箱（已由上一步确认无重复）
2. 添加 unique 约束到 email 字段
3. 创建索引优化查询

使用方法：
    python migrate_add_email_unique.py
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import create_app, db
from sqlalchemy import text


def migrate_add_email_unique():
    """为 User.email 添加唯一约束"""
    app = create_app()

    with app.app_context():
        print("=" * 60)
        print("迁移脚本：添加 User.email 唯一约束")
        print("=" * 60)

        # Step 1: 检查重复邮箱
        print("\n[Step 1] 检查重复邮箱...")
        duplicates = db.session.execute(
            text("SELECT email, COUNT(*) as cnt FROM users WHERE email IS NOT NULL AND email != '' GROUP BY email HAVING COUNT(*) > 1")
        ).fetchall()

        if duplicates:
            print(f"❌ 发现重复邮箱 {len(duplicates)} 组：")
            for email, count in duplicates:
                print(f"   - {email}: {count} 个用户")
            print("\n请先清理重复邮箱后再执行迁移")
            return False
        else:
            print("✅ 无重复邮箱，可以安全添加约束")

        # Step 2: 检查约束是否已存在
        print("\n[Step 2] 检查约束是否已存在...")

        # PostgreSQL: 查询唯一约束
        existing_constraint = db.session.execute(
            text("""
                SELECT constraint_name
                FROM information_schema.table_constraints
                WHERE table_name = 'users'
                AND constraint_type = 'UNIQUE'
                AND constraint_name LIKE '%email%'
            """)
        ).fetchone()

        if existing_constraint:
            print(f"✅ 唯一约束已存在：{existing_constraint[0]}")
            return True

        # Step 3: 添加唯一约束
        print("\n[Step 3] 添加唯一约束...")

        try:
            # 添加唯一约束
            db.session.execute(
                text('ALTER TABLE users ADD CONSTRAINT uq_users_email UNIQUE (email)')
            )
            db.session.commit()
            print("✅ 唯一约束已添加：uq_users_email")

            # 添加索引（如果不存在）
            db.session.execute(
                text('CREATE INDEX IF NOT EXISTS ix_users_email ON users (email)')
            )
            db.session.commit()
            print("✅ 索引已创建：ix_users_email")

        except Exception as e:
            db.session.rollback()
            print(f"❌ 添加约束失败：{e}")
            return False

        # Step 4: 验证约束
        print("\n[Step 4] 验证约束...")

        constraint = db.session.execute(
            text("""
                SELECT constraint_name
                FROM information_schema.table_constraints
                WHERE table_name = 'users'
                AND constraint_type = 'UNIQUE'
                AND constraint_name = 'uq_users_email'
            """)
        ).fetchone()

        if constraint:
            print(f"✅ 验证成功：约束 {constraint[0]} 存在")
        else:
            print("❌ 验证失败：约束不存在")
            return False

        print("\n" + "=" * 60)
        print("迁移完成！User.email 现在有唯一约束")
        print("=" * 60)

        return True


if __name__ == '__main__':
    success = migrate_add_email_unique()
    sys.exit(0 if success else 1)