"""
添加 KnowledgeDocument.content_hash 字段

迁移内容：
1. 新增 content_hash 列（VARCHAR(32)）
2. 创建 content_hash 索引（用于去重查询）
"""
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def upgrade():
    """执行迁移"""
    app = create_app()
    with app.app_context():
        try:
            logger.info("Adding content_hash column to knowledge_documents...")

            # 新增 content_hash 列
            db.session.execute(text("""
                ALTER TABLE knowledge_documents
                ADD COLUMN IF NOT EXISTS content_hash VARCHAR(32);
            """))

            logger.info("Creating content_hash index...")
            # 创建索引（用于去重查询）
            db.session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_knowledge_content_hash
                ON knowledge_documents(content_hash);
            """))

            db.session.commit()
            logger.info("Migration completed successfully")

        except Exception as e:
            db.session.rollback()
            logger.error(f"Migration failed: {e}")
            raise

def downgrade():
    """回滚迁移"""
    app = create_app()
    with app.app_context():
        try:
            logger.info("Dropping content_hash index...")
            db.session.execute(text("""
                DROP INDEX IF EXISTS idx_knowledge_content_hash;
            """))

            logger.info("Dropping content_hash column...")
            db.session.execute(text("""
                ALTER TABLE knowledge_documents
                DROP COLUMN IF EXISTS content_hash;
            """))

            db.session.commit()
            logger.info("Migration rollback completed successfully")
        except Exception as e:
            db.session.rollback()
            logger.error(f"Migration rollback failed: {e}")
            raise

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '--downgrade':
        downgrade()
    else:
        upgrade()