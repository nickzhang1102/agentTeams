"""
数据库迁移脚本：为 messages 表添加 sequence_number 字段

此脚本用于解决 Leader Session 消息排序问题：
- Leader Session 的所有消息在同一事务中创建，created_at 时间戳几乎相同
- 添加 sequence_number 字段用于精确排序同一次会话中的消息

执行方式：
python migrate_add_message_sequence.py
"""

import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import inspect, text
from app import create_app, db

COLUMN_NAME = 'sequence_number'
TABLE_NAME = 'messages'

def migrate():
    """执行迁移"""
    app = create_app()

    with app.app_context():
        connection = db.engine.connect()
        transaction = connection.begin()

        try:
            inspector = inspect(connection)
            tables = set(inspector.get_table_names())

            if TABLE_NAME not in tables:
                print(f'[SKIP] Table {TABLE_NAME} does not exist')
                transaction.commit()
                return

            columns = {column['name'] for column in inspector.get_columns(TABLE_NAME)}
            dialect_name = connection.dialect.name

            if COLUMN_NAME not in columns:
                print(f'[MIGRATE] Adding {COLUMN_NAME} column to {TABLE_NAME} ({dialect_name})...')

                # PostgreSQL 使用原生 SQL
                if dialect_name == 'postgresql':
                    connection.execute(text(
                        f'ALTER TABLE {TABLE_NAME} ADD COLUMN {COLUMN_NAME} INTEGER DEFAULT 0'
                    ))
                else:
                    connection.execute(text(
                        f'ALTER TABLE {TABLE_NAME} ADD COLUMN {COLUMN_NAME} INTEGER DEFAULT 0'
                    ))
            else:
                print(f'[SKIP] Column {COLUMN_NAME} already exists on {TABLE_NAME}')

            # 创建索引
            print(f'[MIGRATE] Creating index idx_messages_conversation_sequence...')
            connection.execute(text(
                f'CREATE INDEX IF NOT EXISTS idx_messages_conversation_sequence '
                f'ON {TABLE_NAME}(conversation_id, created_at, {COLUMN_NAME})'
            ))

            transaction.commit()

            verification_inspector = inspect(connection)
            verification_columns = [column['name'] for column in verification_inspector.get_columns(TABLE_NAME)]
            print(f'[OK] Migration completed. Current {TABLE_NAME} columns: {verification_columns}')
            print(f'[OK] Index idx_messages_conversation_sequence created')

        except Exception as e:
            transaction.rollback()
            print(f'[ERROR] Migration failed: {str(e)}')
            raise
        finally:
            connection.close()

if __name__ == '__main__':
    migrate()
