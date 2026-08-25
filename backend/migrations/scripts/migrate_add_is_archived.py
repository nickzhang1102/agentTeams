"""
数据库迁移脚本：添加 is_archived 列到 conversations 表
"""
import sqlite3
import os

# 数据库路径
DB_PATH = 'data/app.db'

def migrate():
    """执行迁移"""
    # 确保数据目录存在
    os.makedirs('data', exist_ok=True)

    # 连接数据库
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # 检查列是否已存在
        cursor.execute("PRAGMA table_info(conversations)")
        columns = [col[1] for col in cursor.fetchall()]

        if 'is_archived' not in columns:
            print("Adding is_archived column...")
            cursor.execute("""
                ALTER TABLE conversations
                ADD COLUMN is_archived BOOLEAN DEFAULT 0
            """)
            conn.commit()
            print("Migration successful: is_archived column added")
        else:
            print("is_archived column already exists, skip migration")

        # 验证
        cursor.execute("PRAGMA table_info(conversations)")
        columns = [col[1] for col in cursor.fetchall()]
        print(f"Current conversations table columns: {columns}")

    except Exception as e:
        print(f"Migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()
