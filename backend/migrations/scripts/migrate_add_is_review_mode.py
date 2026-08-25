"""
数据库迁移脚本：为 conversations 表添加 is_review_mode 列，并按 leader_sessions 保守回填
运行方式: python migrate_add_is_review_mode.py
"""
from sqlalchemy import inspect, text

import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db


COLUMN_NAME = 'is_review_mode'
TABLE_NAME = 'conversations'
LEADER_SESSIONS_TABLE = 'leader_sessions'


def _get_boolean_column_sql(dialect_name):
    if dialect_name == 'postgresql':
        return f'ALTER TABLE {TABLE_NAME} ADD COLUMN {COLUMN_NAME} BOOLEAN NOT NULL DEFAULT FALSE'
    return f'ALTER TABLE {TABLE_NAME} ADD COLUMN {COLUMN_NAME} BOOLEAN NOT NULL DEFAULT 0'


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
                connection.execute(text(_get_boolean_column_sql(dialect_name)))
            else:
                print(f'[SKIP] Column {COLUMN_NAME} already exists on {TABLE_NAME}')

            false_literal = 'FALSE' if dialect_name == 'postgresql' else '0'
            true_literal = 'TRUE' if dialect_name == 'postgresql' else '1'

            print(f'[MIGRATE] Initializing existing rows to {false_literal} when value is NULL...')
            connection.execute(text(
                f'UPDATE {TABLE_NAME} SET {COLUMN_NAME} = {false_literal} '
                f'WHERE {COLUMN_NAME} IS NULL'
            ))

            if LEADER_SESSIONS_TABLE in tables:
                print(f'[MIGRATE] Backfilling review conversations from {LEADER_SESSIONS_TABLE}...')
                connection.execute(text(
                    f'UPDATE {TABLE_NAME} SET {COLUMN_NAME} = {true_literal} '
                    f'WHERE id IN ('
                    f'  SELECT DISTINCT conversation_id FROM {LEADER_SESSIONS_TABLE} '
                    f'  WHERE conversation_id IS NOT NULL'
                    f')'
                ))
            else:
                print(f'[SKIP] Table {LEADER_SESSIONS_TABLE} does not exist, skip backfill')

            transaction.commit()

            verification_inspector = inspect(connection)
            verification_columns = [column['name'] for column in verification_inspector.get_columns(TABLE_NAME)]
            print(f'[OK] Migration completed. Current {TABLE_NAME} columns: {verification_columns}')
        except Exception as exc:
            transaction.rollback()
            print(f'[ERROR] Migration failed: {exc}')
            raise
        finally:
            connection.close()


if __name__ == '__main__':
    migrate()
