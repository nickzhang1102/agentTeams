"""
数据库迁移脚本: 修复文件表的外键约束和安全问题

修复内容:
1. 将 files.conversation_id 改为可空(允许临时文件)
2. 添加 files.user_id 字段(防止跨用户访问)
3. 更新现有数据:设置 user_id 并清理 conversation_id=0 的记录

使用方法:
    python migrate_files_table.py
"""

import os
import sys
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from sqlalchemy import text


def migrate_database():
    """执行数据库迁移"""
    app = create_app()

    with app.app_context():
        print("开始数据库迁移...")

        try:
            # 清理之前失败的迁移
            db.session.execute(text("DROP TABLE IF EXISTS files_new"))

            # 检查是否已经有 user_id 列
            result = db.session.execute(text("PRAGMA table_info(files)"))
            columns = [row[1] for row in result.fetchall()]

            if 'user_id' not in columns:
                print("步骤 1: 添加 user_id 列...")
                # SQLite 的 ALTER TABLE 限制较多,需要重建表
                # 创建临时表
                db.session.execute(text("""
                    CREATE TABLE files_new (
                        id INTEGER PRIMARY KEY,
                        conversation_id INTEGER,
                        message_id INTEGER,
                        user_id INTEGER NOT NULL,
                        filename VARCHAR(255) NOT NULL,
                        file_path VARCHAR(500) NOT NULL,
                        file_type VARCHAR(50),
                        file_size INTEGER,
                        version INTEGER DEFAULT 1,
                        created_at DATETIME,
                        FOREIGN KEY (conversation_id) REFERENCES conversations(id),
                        FOREIGN KEY (message_id) REFERENCES messages(id),
                        FOREIGN KEY (user_id) REFERENCES users(id)
                    )
                """))

                print("步骤 2: 获取默认用户...")
                # 获取第一个用户作为默认用户
                result = db.session.execute(text("SELECT id FROM users LIMIT 1"))
                user_row = result.fetchone()
                if not user_row:
                    print("错误: 没有找到用户,请先创建用户")
                    return False
                default_user_id = user_row[0]
                print(f"使用用户ID {default_user_id} 作为默认用户")

                print("步骤 3: 迁移现有数据...")
                # 获取所有文件记录
                result = db.session.execute(text("""
                    SELECT id, conversation_id, message_id, filename, file_path, file_type, file_size, version, created_at
                    FROM files
                """))
                files = result.fetchall()
                print(f"找到 {len(files)} 个文件记录")

                for file_row in files:
                    file_id, conv_id, msg_id, filename, file_path, file_type, file_size, version, created_at = file_row

                    # 获取关联对话的用户ID
                    user_id = default_user_id
                    if conv_id and conv_id != 0:
                        conv_result = db.session.execute(
                            text("SELECT user_id FROM conversations WHERE id = :id"),
                            {'id': conv_id}
                        )
                        conv_row = conv_result.fetchone()
                        if conv_row:
                            user_id = conv_row[0]

                    # 将 conversation_id=0 改为 NULL
                    final_conv_id = conv_id if conv_id != 0 else None

                    db.session.execute(text("""
                        INSERT INTO files_new
                        (id, conversation_id, message_id, user_id, filename, file_path, file_type, file_size, version, created_at)
                        VALUES (:id, :conv_id, :msg_id, :user_id, :filename, :file_path, :file_type, :file_size, :version, :created_at)
                    """), {
                        'id': file_id,
                        'conv_id': final_conv_id,
                        'msg_id': msg_id,
                        'user_id': user_id,
                        'filename': filename,
                        'file_path': file_path,
                        'file_type': file_type,
                        'file_size': file_size,
                        'version': version,
                        'created_at': created_at
                    })

                print("步骤 4: 删除旧表...")
                db.session.execute(text("DROP TABLE files"))

                print("步骤 5: 重命名新表...")
                db.session.execute(text("ALTER TABLE files_new RENAME TO files"))

                print("步骤 6: 创建索引...")
                db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_files_conversation_id ON files (conversation_id)"))
                db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_files_user_id ON files (user_id)"))
                db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_files_message_id ON files (message_id)"))

                db.session.commit()
                print("迁移完成!")

            else:
                print("user_id 列已存在,跳过迁移")

                # 只需要更新 conversation_id=0 的记录
                print("更新 conversation_id=0 的记录...")
                db.session.execute(text("UPDATE files SET conversation_id = NULL WHERE conversation_id = 0"))
                db.session.commit()
                print("更新完成!")

            return True

        except Exception as e:
            print(f"迁移失败: {str(e)}")
            import traceback
            traceback.print_exc()
            db.session.rollback()
            return False


if __name__ == '__main__':
    success = migrate_database()
    sys.exit(0 if success else 1)
