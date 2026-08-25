"""
为 leader_sessions 添加 error_message 字段

用于存储 Leader 会话失败时的错误信息。
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
    app = create_app()
    with app.app_context():
        try:
            logger.info("Adding error_message column to leader_sessions...")
            db.session.execute(text("""
                ALTER TABLE leader_sessions
                ADD COLUMN IF NOT EXISTS error_message TEXT;
            """))
            db.session.commit()
            logger.info("Migration completed successfully")
        except Exception as e:
            db.session.rollback()
            logger.error(f"Migration failed: {e}")
            raise


def downgrade():
    app = create_app()
    with app.app_context():
        try:
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