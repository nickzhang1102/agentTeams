"""
数据库迁移：为 KnowledgeDocument 表添加 graphify 提取相关字段

迁移内容：
1. 添加 graphify_error 字段（TEXT）
2. 添加 graphify_processed_at 字段（TIMESTAMP）
3. 添加 graph_nodes 字段（INTEGER）
4. 添加 graph_edges 字段（INTEGER）

运行方式: python migrations/add_graphify_fields.py

注意：
- 使用 ALTER TABLE 添加新字段
- 字段允许 NULL，不影响现有数据
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from sqlalchemy import text


def add_graphify_fields():
    """添加 graphify 提取相关字段"""
    print("=" * 60)
    print("迁移：为 KnowledgeDocument 表添加 graphify 字段")
    print("=" * 60)

    try:
        # 添加 graphify_error 字段
        print("\n添加 graphify_error 字段...")
        db.session.execute(text("""
            ALTER TABLE knowledge_documents
            ADD COLUMN IF NOT EXISTS graphify_error TEXT
        """))

        # 添加 graphify_processed_at 字段
        print("添加 graphify_processed_at 字段...")
        db.session.execute(text("""
            ALTER TABLE knowledge_documents
            ADD COLUMN IF NOT EXISTS graphify_processed_at TIMESTAMP
        """))

        # 添加 graph_nodes 字段
        print("添加 graph_nodes 字段...")
        db.session.execute(text("""
            ALTER TABLE knowledge_documents
            ADD COLUMN IF NOT EXISTS graph_nodes INTEGER
        """))

        # 添加 graph_edges 字段
        print("添加 graph_edges 字段...")
        db.session.execute(text("""
            ALTER TABLE knowledge_documents
            ADD COLUMN IF NOT EXISTS graph_edges INTEGER
        """))

        db.session.commit()
        print("\n✓ 迁移完成")

    except Exception as e:
        db.session.rollback()
        print(f"\n✗ 迁移失败: {e}")
        raise


def verify_migration():
    """验证迁移结果"""
    print("\n" + "=" * 60)
    print("验证迁移结果")
    print("=" * 60)

    try:
        result = db.session.execute(text("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'knowledge_documents'
            AND column_name IN ('graphify_error', 'graphify_processed_at', 'graph_nodes', 'graph_edges')
            ORDER BY column_name
        """))

        columns = list(result)
        if len(columns) == 4:
            print("\n✓ 新字段已添加:")
            for col in columns:
                print(f"  - {col[0]}: {col[1]}")
        else:
            print(f"\n⚠ 期望 4 个字段，实际找到 {len(columns)} 个")

    except Exception as e:
        print(f"\n✗ 验证失败: {e}")


if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        add_graphify_fields()
        verify_migration()