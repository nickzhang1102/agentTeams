"""
迁移脚本：添加 leader_final_reports 表

将 final_report 从 leader_messages 表分离到独立的表。
一个 session 只能有一个最终报告。
"""
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from models import LeaderFinalReport


def migrate():
    """执行迁移"""
    app = create_app()
    with app.app_context():
        # 创建表
        db.create_all()
        print("✓ leader_final_reports 表创建成功")


if __name__ == '__main__':
    migrate()
