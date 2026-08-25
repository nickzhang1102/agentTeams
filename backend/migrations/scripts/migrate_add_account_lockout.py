"""
数据库迁移：添加账户锁定字段到 users 表

添加字段：
- failed_login_attempts: 连续失败次数
- locked_until: 锁定到期时间
- lockout_reason: 锁定原因
"""
import sys
import os
from datetime import datetime

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from sqlalchemy import text

app = create_app()

def migrate():
    """执行迁移"""
    with app.app_context():
        try:
            # 检查字段是否已存在（PostgreSQL 语法）
            result = db.session.execute(text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'users'
            """))
            columns = [row[0] for row in result.fetchall()]

            changes = []

            # 添加 failed_login_attempts 字段
            if 'failed_login_attempts' not in columns:
                db.session.execute(text(
                    'ALTER TABLE users ADD COLUMN failed_login_attempts INTEGER DEFAULT 0 NOT NULL'
                ))
                changes.append('failed_login_attempts')

            # 添加 locked_until 字段
            if 'locked_until' not in columns:
                db.session.execute(text(
                    'ALTER TABLE users ADD COLUMN locked_until TIMESTAMP'
                ))
                changes.append('locked_until')

            # 添加 lockout_reason 字段
            if 'lockout_reason' not in columns:
                db.session.execute(text(
                    'ALTER TABLE users ADD COLUMN lockout_reason VARCHAR(255)'
                ))
                changes.append('lockout_reason')

            if changes:
                db.session.commit()
                print(f"[OK] Migration completed: Added columns {', '.join(changes)}")
            else:
                print("[INFO] No migration needed: All columns already exist")

        except Exception as e:
            db.session.rollback()
            print(f"[ERROR] Migration failed: {str(e)}")
            raise

if __name__ == '__main__':
    migrate()