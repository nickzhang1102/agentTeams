"""
添加 KnowledgeCategory 表 + 种子数据

迁移内容：
1. 创建 knowledge_categories 表
2. 创建索引优化查询性能
3. 插入 4 条预置分类（regulation/workflow/contract/news）
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

# 预置分类数据
SEED_CATEGORIES = [
    {'key': 'regulation', 'label': '制度', 'description': '公司规章制度、政策文件', 'icon': 'Document', 'sort_order': 10},
    {'key': 'workflow', 'label': '流程', 'description': '业务流程、操作指南', 'icon': 'Operation', 'sort_order': 20},
    {'key': 'contract', 'label': '合同', 'description': '合同模板、协议范本', 'icon': 'Tickets', 'sort_order': 30},
    {'key': 'news', 'label': '新闻', 'description': '行业新闻、资讯动态', 'icon': 'Reading', 'sort_order': 40},
]


def upgrade():
    """执行迁移"""
    app = create_app()
    with app.app_context():
        try:
            logger.info("Creating knowledge_categories table...")
            db.session.execute(text("""
                CREATE TABLE IF NOT EXISTS knowledge_categories (
                    id SERIAL PRIMARY KEY,
                    key VARCHAR(20) UNIQUE NOT NULL,
                    label VARCHAR(50) NOT NULL,
                    description VARCHAR(200),
                    icon VARCHAR(50) DEFAULT 'Document',
                    sort_order INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT TRUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))

            logger.info("Creating indexes...")
            # sort_order 索引
            db.session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_knowledge_category_sort
                ON knowledge_categories(sort_order);
            """))

            # is_active 索引
            db.session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_knowledge_category_active
                ON knowledge_categories(is_active);
            """))

            db.session.commit()
            logger.info("Table created successfully")

            # 插入种子数据
            logger.info("Inserting seed categories...")
            for cat in SEED_CATEGORIES:
                db.session.execute(text("""
                    INSERT INTO knowledge_categories (key, label, description, icon, sort_order, is_active)
                    VALUES (:key, :label, :description, :icon, :sort_order, TRUE)
                    ON CONFLICT (key) DO NOTHING;
                """), cat)

            db.session.commit()
            logger.info(f"Inserted {len(SEED_CATEGORIES)} seed categories")

            # 验证插入结果
            result = db.session.execute(text("SELECT COUNT(*) FROM knowledge_categories;"))
            count = result.scalar()
            logger.info(f"Total categories in database: {count}")

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
            logger.info("Dropping knowledge_categories table...")
            db.session.execute(text("DROP TABLE IF EXISTS knowledge_categories;"))
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