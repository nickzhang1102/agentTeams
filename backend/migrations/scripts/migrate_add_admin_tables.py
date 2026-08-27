#!/usr/bin/env python3
"""数据库迁移脚本：创建Admin后台管理表

创建以下表：
- agent_configs: Agent配置与统计
- system_configs: 系统配置
- tool_call_logs: 工具调用日志
- performance_metrics: 性能指标

初始化数据：
- 默认系统配置
- 同步现有 agents/*.md 文件到数据库
"""

import os
import re
import sys
import logging
from datetime import datetime
from pathlib import Path
import yaml

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from models import AgentConfig, SystemConfig

# 配置日志
logger = logging.getLogger(__name__)


def parse_agent_file(file_path):
    """解析Agent配置文件（Markdown + YAML frontmatter）

    Args:
        file_path: Agent文件路径

    Returns:
        dict: Agent配置信息，包含name, description, model等字段

    Raises:
        IOError: 文件读取失败
        UnicodeDecodeError: 文件编码错误
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except (IOError, UnicodeDecodeError) as e:
        logger.error(f"Failed to read agent file {file_path}: {e}")
        raise

    # 处理空文件
    if not content or not content.strip():
        logger.warning(f"Empty agent file: {file_path}")
        return {}

    # 解析YAML frontmatter
    metadata = {}
    if content.startswith('---'):
        parts = content.split('---', 2)
        if len(parts) >= 3:
            frontmatter = parts[1].strip()
            try:
                # 使用 yaml.safe_load 替代手工解析，支持多行值和复杂结构
                metadata = yaml.safe_load(frontmatter) or {}
                if not isinstance(metadata, dict):
                    logger.warning(f"Invalid YAML frontmatter in {file_path}, expected dict")
                    metadata = {}
            except yaml.YAMLError as e:
                logger.error(f"YAML parse error in {file_path}: {e}")
                # 解析失败时返回空字典，不中断流程
                metadata = {}

    # 解析Markdown标题（如果 YAML 中没有 name）
    if 'name' not in metadata and 'title' not in metadata:
        lines = content.split('\n')
        for line in lines:
            if line.startswith('# '):
                metadata['title'] = line[2:].strip()
                break

    return metadata


def sync_existing_agents():
    """同步现有的Agent文件到数据库

    扫描 agents/ 目录下的所有 .md 文件，
    解析配置并插入到 agent_configs 表。
    """
    agents_dir = Path(__file__).parent.parent.parent.parent / 'agents'

    if not agents_dir.exists():
        print(f"[WARN] Agent目录不存在: {agents_dir}")
        return

    md_files = list(agents_dir.glob('*.md'))
    print(f"[INFO] 找到 {len(md_files)} 个Agent配置文件")

    synced_count = 0
    error_count = 0

    for md_file in md_files:
        agent_id = md_file.stem  # 文件名（不含扩展名）

        try:
            # 跳过已存在的记录
            existing = AgentConfig.query.filter_by(agent_id=agent_id).first()
            if existing:
                print(f"  [SKIP] {agent_id} - 已存在，跳过")
                continue

            # 解析Agent文件
            try:
                metadata = parse_agent_file(md_file)
            except (IOError, UnicodeDecodeError) as e:
                print(f"  [ERROR] {agent_id} - 文件读取失败: {e}")
                error_count += 1
                continue

            # 创建数据库记录
            agent_config = AgentConfig(
                agent_id=agent_id,
                file_path=str(md_file),
                file_exists=True,
                is_enabled=True,
                priority=0,
                name=metadata.get('name') or metadata.get('title') or agent_id,
                description=metadata.get('description', ''),
                model=metadata.get('model', 'inherit')
            )

            db.session.add(agent_config)
            synced_count += 1
            print(f"  [OK] {agent_id} - {agent_config.name}")

        except Exception as e:
            logger.exception(f"Unexpected error syncing agent {agent_id}")
            print(f"  [ERROR] {agent_id} - 同步失败: {e}")
            error_count += 1
            continue

    if synced_count > 0:
        try:
            db.session.commit()
            print(f"[SUCCESS] 成功同步 {synced_count} 个Agent配置")
        except Exception as e:
            db.session.rollback()
            logger.exception("Database commit failed")
            print(f"[ERROR] 数据库提交失败: {e}")
            raise

    if error_count > 0:
        print(f"[WARN] {error_count} 个Agent同步失败")

    if synced_count == 0 and error_count == 0:
        print("[INFO] 没有需要同步的Agent")


def initialize_system_configs():
    """初始化默认系统配置

    插入系统运行所需的关键配置项。
    """
    default_configs = [
        {
            'key': 'system.name',
            'value': 'Claude Chat System',
            'description': '系统名称'
        },
        {
            'key': 'system.version',
            'value': '1.0.0',
            'description': '系统版本'
        },
        {
            'key': 'agent.max_calls_per_day',
            'value': '1000',
            'description': '每个Agent每日最大调用次数'
        },
        {
            'key': 'agent.default_model',
            'value': 'claude-sonnet-4-6-20250514',
            'description': '默认Agent模型'
        },
        {
            'key': 'performance.log_retention_days',
            'value': '30',
            'description': '性能日志保留天数'
        },
        {
            'key': 'tool.timeout_seconds',
            'value': '300',
            'description': '工具调用超时时间（秒）'
        },
        {
            'key': 'EXA_API_KEY',
            'value': '',
            'description': 'Exa Web Search API Key'
        },
        {
            'key': 'TAVILY_API_KEY',
            'value': '',
            'description': 'Tavily Web Search API Key'
        }
    ]

    inserted_count = 0

    try:
        for config_data in default_configs:
            # 检查是否已存在
            existing = SystemConfig.query.filter_by(key=config_data['key']).first()
            if existing:
                print(f"  [SKIP] {config_data['key']} - 已存在，跳过")
                continue

            config = SystemConfig(**config_data)
            db.session.add(config)
            inserted_count += 1
            print(f"  [OK] {config_data['key']} = {config_data['value']}")

        if inserted_count > 0:
            db.session.commit()
            print(f"[SUCCESS] 初始化 {inserted_count} 个系统配置")
        else:
            print("[INFO] 所有系统配置已存在，无需初始化")

    except Exception as e:
        db.session.rollback()
        logger.exception("Failed to initialize system configs")
        print(f"[ERROR] 系统配置初始化失败: {e}")
        raise


def main():
    """执行迁移"""
    print("[INFO] 开始执行数据库迁移...")
    print("=" * 60)

    # 创建数据库表
    app = create_app()

    with app.app_context():
        # 1. 创建表结构
        print("\n[STEP 1] 创建表结构")
        print("-" * 60)
        db.create_all()
        print("[OK] 表结构创建完成")

        # 2. 初始化系统配置
        print("\n[STEP 2] 初始化系统配置")
        print("-" * 60)
        initialize_system_configs()

        # 3. 同步现有Agent
        print("\n[STEP 3] 同步Agent配置")
        print("-" * 60)
        sync_existing_agents()

    print("\n" + "=" * 60)
    print("[DONE] 数据库迁移完成！")
    print("=" * 60)


if __name__ == '__main__':
    main()
