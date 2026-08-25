"""
数据库迁移：将数据从 leader_messages 迁移到新表

迁移内容：
1. 创建新表（leader_agent_results, leader_final_reports）
2. 迁移 agent_result 消息到 leader_agent_results 表
3. 迁移 final_report 和 summary 消息到 leader_final_reports 表
4. 删除已迁移的旧记录

运行方式: python migrations/add_leader_tables.py

注意：
- 使用事务确保原子性，失败时会自动回滚
- 每条记录的迁移使用独立 try-except，单条失败不影响其他记录
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from models import LeaderMessage, LeaderAgentResult, LeaderFinalReport
from sqlalchemy import text


def create_tables():
    """创建新表"""
    print("=" * 60)
    print("步骤 1: 创建新表")
    print("=" * 60)

    try:
        # 创建 leader_agent_results 表
        print("\n创建 leader_agent_results 表...")
        db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS leader_agent_results (
                id SERIAL PRIMARY KEY,
                conversation_id INTEGER NOT NULL REFERENCES conversations(id),
                leader_session_id INTEGER NOT NULL REFERENCES leader_sessions(id) ON DELETE CASCADE,
                agent_id VARCHAR(50) NOT NULL,
                agent_name VARCHAR(100) NOT NULL,
                status VARCHAR(20) NOT NULL,
                content TEXT,
                error TEXT,
                sequence_number INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # 创建索引
        db.session.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_agent_result_conversation
            ON leader_agent_results(conversation_id)
        """))
        db.session.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_agent_result_session
            ON leader_agent_results(leader_session_id)
        """))
        db.session.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_agent_result_agent
            ON leader_agent_results(agent_id)
        """))
        db.session.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_agent_result_conversation_created
            ON leader_agent_results(conversation_id, created_at)
        """))

        # 添加唯一约束
        db.session.execute(text("""
            ALTER TABLE leader_agent_results
            ADD CONSTRAINT unique_agent_result_sequence
            UNIQUE (leader_session_id, sequence_number)
        """))

        db.session.commit()
        print("  [OK] leader_agent_results 表创建成功")

        # 创建 leader_final_reports 表
        print("\n创建 leader_final_reports 表...")
        db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS leader_final_reports (
                id SERIAL PRIMARY KEY,
                conversation_id INTEGER NOT NULL REFERENCES conversations(id),
                leader_session_id INTEGER NOT NULL REFERENCES leader_sessions(id) ON DELETE CASCADE,
                report TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # 创建索引
        db.session.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_final_report_conversation
            ON leader_final_reports(conversation_id)
        """))
        db.session.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_final_report_conversation_created
            ON leader_final_reports(conversation_id, created_at)
        """))

        # 添加唯一约束
        db.session.execute(text("""
            ALTER TABLE leader_final_reports
            ADD CONSTRAINT unique_final_report_session
            UNIQUE (leader_session_id)
        """))

        db.session.commit()
        print("  [OK] leader_final_reports 表创建成功")

        return True

    except Exception as e:
        print(f"  [错误] 创建表失败: {str(e)}")
        db.session.rollback()
        raise


def migrate_agent_results():
    """迁移 agent_result 消息到 LeaderAgentResult 表"""
    print("\n" + "=" * 60)
    print("步骤 2: 迁移 agent_result 消息")
    print("=" * 60)

    # 查询所有 agent_result 消息
    agent_results = LeaderMessage.query.filter_by(message_type='agent_result').order_by(LeaderMessage.created_at).all()

    if not agent_results:
        print("\n  没有找到 agent_result 消息，跳过迁移")
        return 0

    print(f"\n  找到 {len(agent_results)} 条 agent_result 消息")
    success_count = 0
    error_count = 0

    for msg in agent_results:
        try:
            # 从 JSONB 字段提取数据
            content = msg.content or {}

            # 提取必要字段
            agent_id = content.get('agent_id')
            agent_name = content.get('agent_name')
            status = content.get('status')
            result_content = content.get('content')
            error = content.get('error')

            # 验证必要字段
            if not agent_id or not agent_name or not status:
                print(f"    [跳过] 消息 ID={msg.id} 缺少必要字段")
                error_count += 1
                continue

            # 验证 status 值
            if status not in ['success', 'failed']:
                print(f"    [跳过] 消息 ID={msg.id} 的 status 值无效: {status}")
                error_count += 1
                continue

            # 创建新记录
            new_result = LeaderAgentResult(
                conversation_id=msg.conversation_id,
                leader_session_id=msg.leader_session_id,
                agent_id=agent_id,
                agent_name=agent_name,
                status=status,
                content=result_content,
                error=error,
                sequence_number=msg.sequence_number,
                created_at=msg.created_at
            )

            db.session.add(new_result)

            # 删除旧记录
            db.session.delete(msg)

            success_count += 1
            print(f"    [OK] 迁移消息 ID={msg.id} (agent={agent_id}, status={status})")

        except Exception as e:
            error_count += 1
            print(f"    [错误] 迁移消息 ID={msg.id} 失败: {str(e)}")
            # 回滚单条记录，继续下一条
            db.session.rollback()
            continue

    # 提交所有成功的迁移
    try:
        db.session.commit()
        print(f"\n  [完成] agent_result 迁移成功: {success_count} 条")
        if error_count > 0:
            print(f"  [警告] 跳过/失败: {error_count} 条")
    except Exception as e:
        print(f"\n  [错误] 提交失败: {str(e)}")
        db.session.rollback()
        raise

    return success_count


def migrate_final_reports():
    """迁移 final_report 和 summary 消息到 LeaderFinalReport 表"""
    print("\n" + "=" * 60)
    print("步骤 3: 迁移 final_report 和 summary 消息")
    print("=" * 60)

    # 查询所有 final_report 和 summary 消息
    reports = LeaderMessage.query.filter(
        LeaderMessage.message_type.in_(['final_report', 'summary'])
    ).order_by(LeaderMessage.created_at).all()

    if not reports:
        print("\n  没有找到 final_report 或 summary 消息，跳过迁移")
        return 0

    print(f"\n  找到 {len(reports)} 条报告消息")
    success_count = 0
    error_count = 0

    for msg in reports:
        try:
            # 从 JSONB 字段提取报告内容
            content = msg.content or {}

            # 根据消息类型提取报告内容
            if msg.message_type == 'final_report':
                report_text = content.get('report')
            elif msg.message_type == 'summary':
                report_text = content.get('text')
            else:
                report_text = None

            # 验证报告内容
            if not report_text:
                print(f"    [跳过] 消息 ID={msg.id} 缺少报告内容")
                error_count += 1
                continue

            # 检查是否已存在该 session 的报告
            existing_report = LeaderFinalReport.query.filter_by(
                leader_session_id=msg.leader_session_id
            ).first()

            if existing_report:
                print(f"    [跳过] Session ID={msg.leader_session_id} 已有报告，跳过消息 ID={msg.id}")
                error_count += 1
                continue

            # 创建新记录
            new_report = LeaderFinalReport(
                conversation_id=msg.conversation_id,
                leader_session_id=msg.leader_session_id,
                report=report_text,
                created_at=msg.created_at
            )

            db.session.add(new_report)

            # 删除旧记录
            db.session.delete(msg)

            success_count += 1
            print(f"    [OK] 迁移消息 ID={msg.id} (type={msg.message_type})")

        except Exception as e:
            error_count += 1
            print(f"    [错误] 迁移消息 ID={msg.id} 失败: {str(e)}")
            # 回滚单条记录，继续下一条
            db.session.rollback()
            continue

    # 提交所有成功的迁移
    try:
        db.session.commit()
        print(f"\n  [完成] 报告迁移成功: {success_count} 条")
        if error_count > 0:
            print(f"  [警告] 跳过/失败: {error_count} 条")
    except Exception as e:
        print(f"\n  [错误] 提交失败: {str(e)}")
        db.session.rollback()
        raise

    return success_count


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("开始数据库迁移")
    print("=" * 60)

    app = create_app()

    with app.app_context():
        try:
            # 步骤 1: 创建新表
            create_tables()

            # 步骤 2: 迁移 agent_result 消息
            agent_count = migrate_agent_results()

            # 步骤 3: 迁移 final_report 和 summary 消息
            report_count = migrate_final_reports()

            # 打印总结
            print("\n" + "=" * 60)
            print("迁移完成！")
            print("=" * 60)
            print(f"\n迁移统计：")
            print(f"  - agent_result 迁移: {agent_count} 条")
            print(f"  - final_report/summary 迁移: {report_count} 条")
            print(f"  - 总计: {agent_count + report_count} 条")
            print("\n新表已创建并填充数据。")

        except Exception as e:
            print("\n" + "=" * 60)
            print(f"[错误] 迁移失败: {str(e)}")
            print("=" * 60)
            print("正在回滚所有变更...")
            db.session.rollback()
            print("[回滚完成]")
            raise


if __name__ == '__main__':
    main()
