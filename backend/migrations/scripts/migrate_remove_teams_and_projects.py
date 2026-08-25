"""
删除团队和项目相关表的迁移脚本

警告：此操作不可逆！
建议先备份数据库
"""
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db

def remove_tables():
    app = create_app()
    with app.app_context():
        print("=" * 60)
        print("删除团队和项目相关表")
        print("=" * 60)

        # 确认操作
        print("\n[警告] 此操作将删除以下表：")
        print("  - step_results")
        print("  - workflow_executions")
        print("  - workflow_definitions")
        print("  - team_memberships")
        print("  - teams")
        print("  - projects")
        print("\n此操作不可逆！建议先备份数据库。")

        confirm = input("\n确认删除？(yes/no): ")
        if confirm.lower() != 'yes':
            print("已取消操作")
            return

        try:
            # 删除表（按依赖顺序）
            print("\n正在删除表...")

            db.session.execute(db.text("DROP TABLE IF EXISTS step_results CASCADE"))
            print("[OK] 已删除 step_results")

            db.session.execute(db.text("DROP TABLE IF EXISTS workflow_executions CASCADE"))
            print("[OK] 已删除 workflow_executions")

            db.session.execute(db.text("DROP TABLE IF EXISTS workflow_definitions CASCADE"))
            print("[OK] 已删除 workflow_definitions")

            db.session.execute(db.text("DROP TABLE IF EXISTS team_memberships CASCADE"))
            print("[OK] 已删除 team_memberships")

            db.session.execute(db.text("DROP TABLE IF EXISTS teams CASCADE"))
            print("[OK] 已删除 teams")

            db.session.execute(db.text("DROP TABLE IF EXISTS projects CASCADE"))
            print("[OK] 已删除 projects")

            db.session.commit()
            print("\n" + "=" * 60)
            print("[SUCCESS] 表删除完成")
            print("=" * 60)

        except Exception as e:
            db.session.rollback()
            print(f"\n[ERROR] 删除失败: {str(e)}")
            raise

if __name__ == '__main__':
    remove_tables()