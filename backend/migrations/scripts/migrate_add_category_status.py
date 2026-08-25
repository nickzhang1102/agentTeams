"""
数据库迁移脚本：为 Conversation 表添加 category 和 status 字段

分类字段 category: technology, business, medical, investment, science, writing, legal, education, lifestyle, other
状态字段 status: new（新增）、analyzing（分析中）、error（有报错）、completed（已完成）

运行方式：
    python migrate_add_category_status.py
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
        # 检查字段是否已存在
        inspector = db.inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('conversations')]
        
        # 添加 category 字段
        if 'category' not in columns:
            print("Adding category column to conversations table...")
            db.session.execute(text("""
                ALTER TABLE conversations 
                ADD COLUMN category VARCHAR(20) DEFAULT 'other'
            """))
            db.session.commit()
            print("✓ category column added successfully")
            
            # 创建索引
            try:
                db.session.execute(text("""
                    CREATE INDEX idx_conversations_category ON conversations(category)
                """))
                db.session.commit()
                print("✓ Index on category created")
            except Exception as e:
                print(f"Warning: Could not create index: {e}")
        else:
            print("✓ category column already exists")
        
        # 添加 status 字段
        if 'status' not in columns:
            print("Adding status column to conversations table...")
            db.session.execute(text("""
                ALTER TABLE conversations 
                ADD COLUMN status VARCHAR(20) DEFAULT 'new'
            """))
            db.session.commit()
            print("✓ status column added successfully")
            
            # 创建索引
            try:
                db.session.execute(text("""
                    CREATE INDEX idx_conversations_status ON conversations(status)
                """))
                db.session.commit()
                print("✓ Index on status created")
            except Exception as e:
                print(f"Warning: Could not create index: {e}")
        else:
            print("✓ status column already exists")
        
        print("\nMigration completed successfully!")
        
        # 显示当前数据统计
        result = db.session.execute(text("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN category = 'other' THEN 1 END) as other_category,
                COUNT(CASE WHEN status = 'new' THEN 1 END) as new_status
            FROM conversations
        """))
        row = result.fetchone()
        print(f"\nCurrent data statistics:")
        print(f"  Total conversations: {row[0]}")
        print(f"  With 'other' category: {row[1]}")
        print(f"  With 'new' status: {row[2]}")


if __name__ == '__main__':
    migrate()