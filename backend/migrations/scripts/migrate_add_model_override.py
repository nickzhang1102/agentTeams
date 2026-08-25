"""
数据库迁移脚本：为 conversations 表添加 model_override 字段

运行方式：
    cd backend
    python migrations/scripts/migrate_add_model_override.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text, inspect
from db import engine, db


def migrate():
    """执行迁移"""
    print("开始迁移：为 conversations 表添加 model_override 字段...")

    inspector = inspect(engine)
    columns = [col['name'] for col in inspector.get_columns('conversations')]

    if 'model_override' in columns:
        print("model_override 列已存在，跳过")
        return

    try:
        with engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE conversations ADD COLUMN model_override VARCHAR(100)"
            ))
            conn.commit()
        print("已添加 model_override 列")
    except Exception as e:
        print(f"迁移失败: {e}")
        return

    print("迁移成功完成！")


if __name__ == '__main__':
    migrate()
