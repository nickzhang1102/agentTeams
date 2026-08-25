"""
添加 Leader 会话管理相关字段

迁移内容：
1. 为 leader_sessions 添加 error_message 字段（记录失败原因）
2. 为 tool_call_logs 添加 leader_session_id 外键（关联 Leader 会话）
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
            # 1. 为 leader_sessions 添加 error_message 字段
            logger.info("Adding error_message column to leader_sessions...")
            db.session.execute(text("""
                ALTER TABLE leader_sessions
                ADD COLUMN IF NOT EXISTS error_message TEXT;
            """))

            # 2. 为 tool_call_logs 添加 leader_session_id 外键
            logger.info("Adding leader_session_id column to tool_call_logs...")
            db.session.execute(text("""
                ALTER TABLE tool_call_logs
                ADD COLUMN IF NOT EXISTS leader_session_id INTEGER REFERENCES leader_sessions(id);
            """))

            # 3. 创建索引
            logger.info("Creating index on tool_call_logs.leader_session_id...")
            db.session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_tool_call_leader_session
                ON tool_call_logs(leader_session_id);
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
            logger.info("Dropping index on tool_call_logs.leader_session_id...")
            db.session.execute(text("""
                DROP INDEX IF EXISTS idx_tool_call_leader_session;
            """))

            logger.info("Removing leader_session_id column from tool_call_logs...")
            db.session.execute(text("""
                ALTER TABLE tool_call_logs
                DROP COLUMN IF EXISTS leader_session_id;
            """))

            logger.info("Removing error_message column from leader_sessions...")
            db.session.execute(text("""
                ALTER TABLE leader_sessions
                DROP COLUMN IF EXISTS error_message;
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