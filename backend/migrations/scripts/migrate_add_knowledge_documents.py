"""
添加 KnowledgeDocument 表

迁移内容：
1. 创建 knowledge_documents 表
2. 创建索引优化查询性能
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
            logger.info("Creating knowledge_documents table...")
            db.session.execute(text("""
                CREATE TABLE IF NOT EXISTS knowledge_documents (
                    id SERIAL PRIMARY KEY,
                    filename VARCHAR(255) NOT NULL,
                    original_path VARCHAR(500),
                    markdown_path VARCHAR(500),
                    category VARCHAR(20) DEFAULT 'regulation',
                    file_size INTEGER,
                    file_type VARCHAR(20),
                    uploaded_by INTEGER NOT NULL REFERENCES users(id),
                    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    indexed_at TIMESTAMP,
                    status VARCHAR(20) DEFAULT 'pending'
                );
            """))

            logger.info("Creating indexes...")
            # category 索引
            db.session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_knowledge_category
                ON knowledge_documents(category);
            """))

            # status 索引
            db.session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_knowledge_status
                ON knowledge_documents(status);
            """))

            # uploaded_by 索引
            db.session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_knowledge_uploaded_by
                ON knowledge_documents(uploaded_by);
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
            logger.info("Dropping knowledge_documents table...")
            db.session.execute(text("DROP TABLE IF EXISTS knowledge_documents;"))
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