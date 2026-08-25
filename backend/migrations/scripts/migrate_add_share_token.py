"""
数据库迁移脚本：为 conversations 表添加 share_token 字段

执行方式：
    cd backend
    python migrate_add_share_token.py
"""
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from sqlalchemy import text


def column_exists(table_name, column_name):
    """检查列是否存在"""
    result = db.session.execute(text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = :table_name AND column_name = :column_name
    """), {'table_name': table_name, 'column_name': column_name})
    return result.fetchone() is not None


def add_column():
    """添加 share_token 列"""
    if column_exists('conversations', 'share_token'):
        print("share_token 列已存在")
        return True
    
    try:
        db.session.execute(text("""
            ALTER TABLE conversations ADD COLUMN share_token VARCHAR(20)
        """))
        db.session.commit()
        print("已添加 share_token 列")
        return True
    except Exception as e:
        db.session.rollback()
        print(f"添加列失败: {e}")
        return False


def create_unique_constraint():
    """创建唯一约束"""
    try:
        # 先检查是否已有唯一约束
        result = db.session.execute(text("""
            SELECT constraint_name 
            FROM information_schema.table_constraints 
            WHERE table_name = 'conversations' 
            AND constraint_type = 'UNIQUE' 
            AND constraint_name LIKE '%share_token%'
        """))
        if result.fetchone():
            print("share_token 唯一约束已存在")
            return True
        
        db.session.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS ix_conversations_share_token 
            ON conversations (share_token) 
            WHERE share_token IS NOT NULL
        """))
        db.session.commit()
        print("已创建 share_token 唯一索引")
        return True
    except Exception as e:
        db.session.rollback()
        print(f"创建唯一约束失败: {e}")
        return False


def generate_tokens():
    """为现有对话生成 share_token"""
    from models import Conversation
    
    # 检查列是否存在
    if not column_exists('conversations', 'share_token'):
        print("share_token 列不存在，无法生成 token")
        return False
    
    # 查询没有 share_token 的对话
    conversations = db.session.execute(text("""
        SELECT id FROM conversations 
        WHERE share_token IS NULL OR share_token = ''
    """)).fetchall()
    
    if not conversations:
        print("所有对话都已有 share_token")
        return True
    
    print(f"发现 {len(conversations)} 个对话需要生成 share_token")
    
    updated_count = 0
    for (conv_id,) in conversations:
        # 生成唯一 token
        while True:
            token = Conversation.generate_share_token()
            existing = db.session.execute(text("""
                SELECT id FROM conversations WHERE share_token = :token
            """), {'token': token}).fetchone()
            if not existing:
                break
        
        # 更新 token
        db.session.execute(text("""
            UPDATE conversations SET share_token = :token WHERE id = :id
        """), {'token': token, 'id': conv_id})
        
        updated_count += 1
        if updated_count % 100 == 0:
            db.session.commit()
            print(f"已更新 {updated_count} 个对话...")
    
    db.session.commit()
    print(f"迁移完成！共更新 {updated_count} 个对话")
    return True


def migrate():
    """执行迁移"""
    app = create_app()
    with app.app_context():
        print("开始迁移：为 conversations 表添加 share_token 字段...")
        
        # 步骤 1：添加列
        if not add_column():
            print("迁移失败：无法添加列")
            return
        
        # 步骤 2：创建唯一约束
        if not create_unique_constraint():
            print("警告：创建唯一约束失败，继续执行...")
        
        # 步骤 3：生成 token
        if not generate_tokens():
            print("迁移失败：无法生成 token")
            return
        
        print("迁移成功完成！")


if __name__ == '__main__':
    migrate()