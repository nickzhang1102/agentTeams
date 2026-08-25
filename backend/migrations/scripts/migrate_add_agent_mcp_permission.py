"""
添加 AgentMcpPermission 表

迁移内容：
1. 创建 agent_mcp_permissions 表
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
            logger.info("Creating agent_mcp_permissions table...")
            db.session.execute(text("""
                CREATE TABLE IF NOT EXISTS agent_mcp_permissions (
                    id SERIAL PRIMARY KEY,
                    agent_id VARCHAR(100) NOT NULL,
                    mcp_tool_pattern VARCHAR(200) NOT NULL,
                    enabled BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))

            logger.info("Creating indexes...")
            # agent_id 索引
            db.session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_agent_mcp_agent_id
                ON agent_mcp_permissions(agent_id);
            """))

            # agent_id + enabled 复合索引
            db.session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_agent_mcp_enabled
                ON agent_mcp_permissions(agent_id, enabled);
            """))

            # 唯一约束
            db.session.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_mcp_pattern
                ON agent_mcp_permissions(agent_id, mcp_tool_pattern);
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
            logger.info("Dropping agent_mcp_permissions table...")
            db.session.execute(text("DROP TABLE IF EXISTS agent_mcp_permissions;"))
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