"""
合并 Message 和 LeaderMessage 表的数据迁移脚本

迁移步骤：
1. 将 Message.content 从 Text 转换为 JSONB
2. 将 LeaderMessage 数据迁移到 Message
3. 删除 LeaderMessage 表
4. 创建部分唯一索引

使用方式：
    # 交互式执行（需要确认）
    python migrations/merge_message_tables.py

    # 自动执行（无需确认）
    python migrations/merge_message_tables.py --yes

注意：
- 执行前请先备份数据库
- 建议在测试环境验证后再在生产环境执行
"""

import sys
import os
from datetime import datetime
import argparse

# 添加父目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from models import Message, LeaderSession, Conversation, User
from sqlalchemy import text


def backup_table_data():
    """备份表数据（可选）"""
    print("\n=== 开始备份数据 ===")

    # 统计现有数据
    message_count = Message.query.count()

    # 检查 leader_messages 表是否存在
    from sqlalchemy import inspect
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()

    leader_message_count = 0
    if 'leader_messages' in tables:
        # 使用原生 SQL 查询统计
        result = db.session.execute(text("SELECT COUNT(*) FROM leader_messages")).scalar()
        leader_message_count = result or 0
        print(f"当前 Message 表记录数: {message_count}")
        print(f"当前 leader_messages 表记录数: {leader_message_count}")
    else:
        print(f"当前 Message 表记录数: {message_count}")
        print("leader_messages 表不存在（可能已迁移或为全新数据库）")
        leader_message_count = 0

    return message_count, leader_message_count, 'leader_messages' in tables


def step1_convert_message_content_to_jsonb():
    """步骤1：将 Message.content 从 Text 转换为 JSONB，并将 role 改为可空"""
    print("\n=== 步骤1：转换 Message.content 为 JSONB 并修改 role 为可空 ===")

    try:
        # 1. 将 role 字段改为可空
        db.session.execute(text("""
            ALTER TABLE messages
            ALTER COLUMN role DROP NOT NULL;
        """))
        print("  - role 字段已改为可空")

        # 2. 将 sequence_number 字段改为可空
        db.session.execute(text("""
            ALTER TABLE messages
            ALTER COLUMN sequence_number DROP NOT NULL;
        """))
        print("  - sequence_number 字段已改为可空")

        # 3. 使用原生 SQL 进行类型转换
        db.session.execute(text("""
            ALTER TABLE messages
            ALTER COLUMN content TYPE JSONB
            USING CASE
                WHEN content IS NULL THEN NULL
                ELSE jsonb_build_object('text', content)
            END;
        """))
        print("  - content 字段已转换为 JSONB")

        db.session.commit()
        print("[OK] 步骤1完成")
        return True
    except Exception as e:
        db.session.rollback()
        print(f"[FAIL] 步骤1失败: {e}")
        return False


def step2_migrate_leader_messages():
    """步骤2：将 LeaderMessage 数据迁移到 Message"""
    print("\n=== 步骤2：迁移 LeaderMessage 数据到 Message ===")

    try:
        # 检查表是否存在
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        if 'leader_messages' not in inspector.get_table_names():
            print("leader_messages 表不存在，跳过数据迁移")
            return True

        # 使用原生 SQL 直接迁移数据
        result = db.session.execute(text("""
            INSERT INTO messages (conversation_id, role, content, leader_session_id, message_type, sequence_number, created_at)
            SELECT
                conversation_id,
                NULL as role,
                content,
                leader_session_id,
                message_type,
                sequence_number,
                created_at
            FROM leader_messages
            ORDER BY created_at;
        """))

        migrated = result.rowcount
        db.session.commit()
        print(f"[OK] 成功迁移 {migrated} 条 leader_messages 记录")
        return True
    except Exception as e:
        db.session.rollback()
        print(f"[FAIL] 步骤2失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def step3_drop_leader_messages_table():
    """步骤3：删除 leader_messages 表"""
    print("\n=== 步骤3：删除 leader_messages 表 ===")

    try:
        # 检查表是否存在
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        if 'leader_messages' not in inspector.get_table_names():
            print("leader_messages 表不存在，跳过删除")
            return True

        # 删除外键约束
        try:
            db.session.execute(text("""
                ALTER TABLE leader_messages
                DROP CONSTRAINT IF EXISTS leader_messages_leader_session_id_fkey;
            """))
        except Exception as e:
            # 约束不存在，继续执行
            print(f"  - 警告：删除约束失败（可能不存在）: {e}")
            db.session.rollback()  # 确保事务状态清晰

        # 删除表
        db.session.execute(text("DROP TABLE IF EXISTS leader_messages CASCADE;"))
        db.session.commit()
        print("[OK] leader_messages 表已删除")
        return True
    except Exception as e:
        db.session.rollback()
        print(f"[FAIL] 步骤3失败: {e}")
        return False


def step4_create_partial_unique_index():
    """步骤4：创建部分唯一索引"""
    print("\n=== 步骤4：创建部分唯一索引 ===")

    try:
        # 创建部分唯一索引（仅对 leader_session_id 不为空的记录）
        db.session.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_leader_message_sequence
            ON messages (leader_session_id, sequence_number)
            WHERE leader_session_id IS NOT NULL;
        """))

        # 创建时间索引（如果不存在）
        db.session.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_conversation_created
            ON messages (conversation_id, created_at);
        """))

        # 为 created_at 创建索引
        db.session.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_messages_created_at
            ON messages (created_at);
        """))

        db.session.commit()
        print("[OK] 索引创建成功")
        return True
    except Exception as e:
        db.session.rollback()
        print(f"[FAIL] 步骤4失败: {e}")
        return False


def verify_migration(old_message_count, old_leader_message_count):
    """验证迁移结果"""
    print("\n=== 验证迁移结果 ===")

    try:
        # 统计迁移后的数据
        new_message_count = Message.query.count()
        leader_messages = Message.query.filter(
            Message.leader_session_id.isnot(None),
            Message.sequence_number.isnot(None)
        ).count()

        print(f"迁移后 Message 表总记录数: {new_message_count}")
        print(f"其中 Leader 消息数: {leader_messages}")

        # 验证数据完整性
        expected_total = old_message_count + old_leader_message_count
        if new_message_count == expected_total:
            print(f"[OK] 数据完整性验证通过 ({new_message_count} == {expected_total})")
        else:
            print(f"[FAIL] 数据完整性验证失败 ({new_message_count} != {expected_total})")
            return False

        # 验证 sequence_number 唯一性
        duplicates = db.session.execute(text("""
            SELECT leader_session_id, sequence_number, COUNT(*)
            FROM messages
            WHERE leader_session_id IS NOT NULL
            GROUP BY leader_session_id, sequence_number
            HAVING COUNT(*) > 1;
        """)).fetchall()

        if len(duplicates) == 0:
            print("[OK] sequence_number 唯一性验证通过")
        else:
            print(f"[FAIL] 发现 {len(duplicates)} 组重复的 sequence_number")
            return False

        # 验证 content 格式
        invalid_content = db.session.execute(text("""
            SELECT id, content
            FROM messages
            WHERE content IS NOT NULL
            AND jsonb_typeof(content) IS NULL;
        """)).fetchall()

        if len(invalid_content) == 0:
            print("[OK] content JSONB 格式验证通过")
        else:
            print(f"[FAIL] 发现 {len(invalid_content)} 条无效的 content 格式")
            return False

        return True
    except Exception as e:
        print(f"[FAIL] 验证失败: {e}")
        return False


def main():
    """主迁移流程"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='合并 Message 和 LeaderMessage 表')
    parser.add_argument('--yes', '-y', action='store_true', help='自动确认执行，无需交互')
    args = parser.parse_args()

    print("=" * 60)
    print("Message 和 LeaderMessage 表合并迁移")
    print("=" * 60)
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 创建应用上下文
    app = create_app()
    with app.app_context():
        # 备份数据统计
        old_message_count, old_leader_message_count, table_exists = backup_table_data()

        # 如果表不存在，说明无需迁移
        if not table_exists:
            print("\n无需迁移：leader_messages 表不存在")
            print("可能情况：")
            print("1. 已经迁移完成")
            print("2. 全新数据库（从未创建过 leader_messages 表）")

            # 执行步骤1和步骤4（创建索引）
            if not step1_convert_message_content_to_jsonb():
                print("\n步骤1失败")
                return

            if not step4_create_partial_unique_index():
                print("\n步骤4失败")
                return

            print("\n[OK] 索引创建完成")
            return

        # 确认执行
        if not args.yes:
            confirm = input("\n确认执行迁移？(yes/no): ")
            if confirm.lower() != 'yes':
                print("迁移已取消")
                return
        else:
            print("\n自动确认执行（--yes 参数）")

        # 执行迁移步骤
        if not step1_convert_message_content_to_jsonb():
            print("\n迁移失败，已回滚")
            return

        if not step2_migrate_leader_messages():
            print("\n迁移失败，已回滚")
            return

        if not step3_drop_leader_messages_table():
            print("\n迁移失败，已回滚")
            return

        if not step4_create_partial_unique_index():
            print("\n迁移失败，已回滚")
            return

        # 验证迁移结果
        if not verify_migration(old_message_count, old_leader_message_count):
            print("\n迁移验证失败，请检查数据")
            return

        print("\n" + "=" * 60)
        print("[OK] 迁移成功完成！")
        print("=" * 60)
        print(f"完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("\n建议：")
        print("1. 运行测试套件验证功能")
        print("2. 检查应用日志是否有异常")
        print("3. 更新相关文档")


if __name__ == '__main__':
    main()
