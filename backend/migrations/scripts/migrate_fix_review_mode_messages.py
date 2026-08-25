"""
数据库迁移脚本：修复评审模式用户消息的 is_review_mode 标记
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
        print("开始迁移：修复评审模式用户消息的 is_review_mode 标记...")

        try:
            # 查找所有评审模式的会话
            result = db.session.execute(text("""
                SELECT DISTINCT conversation_id
                FROM leader_sessions
            """))
            conversation_ids = [row[0] for row in result.fetchall()]

            if not conversation_ids:
                print("未找到评审模式会话，跳过迁移")
                return

            print(f"找到 {len(conversation_ids)} 个评审模式会话")

            # 更新这些会话中的用户消息
            for conv_id in conversation_ids:
                # 查找该会话中所有用户消息
                db.session.execute(text("""
                    UPDATE messages
                    SET is_review_mode = TRUE
                    WHERE conversation_id = :conv_id
                    AND role = 'user'
                    AND is_review_mode = FALSE
                """), {'conv_id': conv_id})

            db.session.commit()
            print("迁移完成！")

        except Exception as e:
            db.session.rollback()
            print(f"迁移失败: {e}")
            raise

if __name__ == '__main__':
    migrate()
