"""
添加 OpenHarness 整合相关字段

迁移内容：
1. 为 leader_agent_results 添加字段：tool_calls, tokens_used, execution_time, iterations
2. 创建 harness_session_mappings 表
3. 创建索引优化查询性能
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
            # 1. 为 leader_agent_results 添加字段
            logger.info("Adding columns to leader_agent_results...")
            db.session.execute(text("""
                ALTER TABLE leader_agent_results
                ADD COLUMN IF NOT EXISTS tool_calls JSONB,
                ADD COLUMN IF NOT EXISTS tokens_used INTEGER DEFAULT 0,
                ADD COLUMN IF NOT EXISTS execution_time FLOAT DEFAULT 0.0,
                ADD COLUMN IF NOT EXISTS iterations INTEGER DEFAULT 1;
            """))

            # 2. 创建 harness_session_mappings 表
            logger.info("Creating harness_session_mappings table...")
            db.session.execute(text("""
                CREATE TABLE IF NOT EXISTS harness_session_mappings (
                    id SERIAL PRIMARY KEY,
                    leader_session_id INTEGER NOT NULL REFERENCES leader_sessions(id),
                    harness_session_id VARCHAR(100) UNIQUE NOT NULL,
                    harness_metadata JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))

            # 3. 创建索引
            logger.info("Creating indexes...")
            db.session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_harness_mapping_leader
                ON harness_session_mappings(leader_session_id);
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
            logger.info("Dropping harness_session_mappings table...")
            db.session.execute(text("DROP TABLE IF EXISTS harness_session_mappings;"))

            logger.info("Removing columns from leader_agent_results...")
            db.session.execute(text("""
                ALTER TABLE leader_agent_results
                DROP COLUMN IF EXISTS tool_calls,
                DROP COLUMN IF EXISTS tokens_used,
                DROP COLUMN IF EXISTS execution_time,
                DROP COLUMN IF EXISTS iterations;
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
