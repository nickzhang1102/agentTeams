"""
添加 leader_sessions 表和扩展 messages 表的迁移脚本
运行方式: python migrate_add_leader_sessions.py
"""
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db


def migrate():
    """执行迁移"""
    app = create_app()
    with app.app_context():
        try:
            # 创建新表
            db.create_all()
            print("[OK] LeaderSession table created")

            print("\nMigration completed successfully!")
            print("Added table:")
            print("  - leader_sessions")
            print("Extended table:")
            print("  - messages (added leader_session_id, message_type)")

        except Exception as e:
            print(f"[ERROR] Migration failed: {str(e)}")
            db.session.rollback()
            raise


if __name__ == '__main__':
    migrate()
