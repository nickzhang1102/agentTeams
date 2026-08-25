"""
数据库迁移脚本：为 messages 表添加 is_review_mode 字段
"""
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from sqlalchemy import text

def migrate():
    """执行迁移"""
    app = create_app()

    with app.app_context():
        print("开始迁移：为 messages 表添加 is_review_mode 字段...")

        try:
            # 检查字段是否已存在
            result = db.session.execute(text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name='messages'
                AND column_name='is_review_mode'
            """))

            if result.fetchone():
                print("字段 is_review_mode 已存在于 messages 表，跳过迁移")
                return

            # 添加字段
            db.session.execute(text("""
                ALTER TABLE messages
                ADD COLUMN is_review_mode BOOLEAN DEFAULT FALSE
            """))

            print("字段 is_review_mode 添加成功到 messages 表")

            # 更新现有的评审模式消息
            # 判断依据：leader_session_id IS NOT NULL
            result = db.session.execute(text("""
                UPDATE messages
                SET is_review_mode = TRUE
                WHERE leader_session_id IS NOT NULL
            """))

            print(f"已更新 {result.rowcount} 条评审模式消息")

            db.session.commit()
            print("迁移完成！")

        except Exception as e:
            db.session.rollback()
            print(f"迁移失败: {e}")
            raise

if __name__ == '__main__':
    migrate()