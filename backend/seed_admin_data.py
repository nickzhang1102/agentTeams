#!/usr/bin/env python3
"""种子数据脚本：初始化 AgentConfig 和 SystemConfig

"""
import os
import sys
import yaml
import logging
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import SessionLocal
from models import AgentConfig, SystemConfig
from config import Config
from services.agent_category_service import AGENT_CATEGORY_MAP
from services.agentteams_integration_account import (
    DEFAULT_SERVICE_ACCOUNT_USERNAME,
    AGENTTEAMS_INTEGRATION_ENABLED,
    AGENTTEAMS_SERVICE_ACCOUNT_USERNAME,
    ensure_agentteams_service_account,
)
from services.agentteams_integration_launch import (
    AGENTTEAMS_EMBED_TOKEN_TTL_SECONDS,
    AGENTTEAMS_INTEGRATION_KEY,
    DEFAULT_EMBED_TOKEN_TTL_SECONDS,
)
from services.integration_client_service import IntegrationClientService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def parse_agent_file(file_path: str) -> dict:
    """解析 Agent 配置文件 YAML frontmatter"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except (IOError, UnicodeDecodeError) as e:
        logger.error(f"读取失败 {file_path}: {e}")
        return {}

    if not content or not content.strip():
        return {}

    metadata = {}
    if content.startswith('---'):
        parts = content.split('---', 2)
        if len(parts) >= 3:
            try:
                metadata = yaml.safe_load(parts[1].strip()) or {}
                if not isinstance(metadata, dict):
                    metadata = {}
            except yaml.YAMLError:
                metadata = {}

    if 'name' not in metadata:
        for line in content.split('\n'):
            if line.startswith('# '):
                metadata['title'] = line[2:].strip()
                break

    return metadata


def seed_system_configs(db):
    """初始化默认系统配置"""
    defaults = [
        {'key': 'system.name', 'value': 'Agent Teams', 'description': '系统名称'},
        {'key': 'system.version', 'value': '2.0.0', 'description': '系统版本'},
        {'key': 'agent.max_calls_per_day', 'value': '1000', 'description': '每Agent每日最大调用次数'},
        {'key': 'agent.default_model', 'value': 'claude-sonnet-4-6-20250514', 'description': '默认Agent模型'},
        {'key': 'performance.log_retention_days', 'value': '30', 'description': '性能日志保留天数'},
        {'key': 'tool.timeout_seconds', 'value': '300', 'description': '工具调用超时（秒）'},
        {'key': 'EXA_API_KEY', 'value': '', 'description': 'Exa Web Search API Key'},
        {'key': 'TAVILY_API_KEY', 'value': '', 'description': 'Tavily Web Search API Key'},
        {'key': AGENTTEAMS_INTEGRATION_ENABLED, 'value': 'true', 'description': 'Agent Teams 集成开关'},
        {'key': AGENTTEAMS_INTEGRATION_KEY, 'value': '', 'description': 'Agent Teams 集成密钥'},
        {'key': AGENTTEAMS_EMBED_TOKEN_TTL_SECONDS, 'value': str(DEFAULT_EMBED_TOKEN_TTL_SECONDS), 'description': 'Agent Teams 嵌入令牌有效期（秒）'},
        {'key': AGENTTEAMS_SERVICE_ACCOUNT_USERNAME, 'value': DEFAULT_SERVICE_ACCOUNT_USERNAME, 'description': 'Agent Teams 服务账户用户名'},
    ]
    inserted = 0
    for cfg in defaults:
        if db.query(SystemConfig).filter_by(key=cfg['key']).first():
            continue
        db.add(SystemConfig(**cfg))
        inserted += 1
    if inserted:
        db.commit()
        logger.info(f"SystemConfig: 新增 {inserted} 条")
    else:
        logger.info("SystemConfig: 已存在，跳过")


def seed_agentteams_service_account(db):
    """初始化 Agent Teams 服务账户"""
    user = ensure_agentteams_service_account(db)
    IntegrationClientService.sync_agentteams_client(db, user.id)
    db.commit()
    logger.info(f"Agent Teams service account: user_id={user.id}, username={user.username}")


def seed_agent_configs(db):
    """从 AGENTS_DIR/*.md 同步 AgentConfig"""
    agents_dir = Path(Config.AGENTS_DIR)
    if not agents_dir.exists():
        logger.warning(f"Agent 目录不存在: {agents_dir}")
        return

    md_files = list(agents_dir.glob('*.md'))
    logger.info(f"找到 {len(md_files)} 个 Agent 文件")

    created = 0
    updated = 0
    for md_file in md_files:
        agent_id = md_file.stem
        metadata = parse_agent_file(str(md_file))
        existing = db.query(AgentConfig).filter_by(agent_id=agent_id).first()
        if existing:
            # 同步 .md 文件中的字段到已有记录
            changed = False
            for field, meta_key in [('name', 'name'), ('description', 'description'),
                                     ('model', 'model'), ('priority', 'priority')]:
                meta_val = metadata.get(meta_key) if meta_key != 'name' else (metadata.get('name') or metadata.get('title'))
                if meta_val is not None and getattr(existing, field, None) != meta_val:
                    setattr(existing, field, meta_val)
                    changed = True
            if changed:
                updated += 1
            continue

        agent = AgentConfig(
            agent_id=agent_id,
            name=metadata.get('name') or metadata.get('title') or agent_id,
            description=metadata.get('description', ''),
            model=metadata.get('model', 'inherit'),
            category=AGENT_CATEGORY_MAP.get(agent_id),
            file_path=str(md_file),
            file_exists=True,
            is_enabled=True,
            priority=metadata.get('priority', 30),
        )
        db.add(agent)
        created += 1

    if created or updated:
        db.commit()
        logger.info(f"AgentConfig: 新增 {created} 条, 更新 {updated} 条")
    else:
        logger.info("AgentConfig: 已存在，跳过")

    # 回填缺失 category 的已有 Agent
    backfilled = 0
    for agent in db.query(AgentConfig).filter(AgentConfig.category.is_(None)).all():
        cat = AGENT_CATEGORY_MAP.get(agent.agent_id)
        if cat:
            agent.category = cat
            backfilled += 1
    if backfilled:
        db.commit()
        logger.info(f"AgentConfig: 回填 category {backfilled} 条")


def main():
    db = SessionLocal()
    try:
        print("=" * 60)
        print("种子数据初始化")
        print("=" * 60)

        print("\n[1/3] 初始化系统配置...")
        seed_system_configs(db)

        print("[2/3] 初始化 Agent Teams 服务账户...")
        seed_agentteams_service_account(db)

        print("[3/3] 同步 Agent 配置...")
        seed_agent_configs(db)

        # 验证
        agent_count = db.query(AgentConfig).count()
        config_count = db.query(SystemConfig).count()
        print(f"\n验证: AgentConfig={agent_count}, SystemConfig={config_count}")
        print("=" * 60)
        print("完成！")
    finally:
        db.close()


if __name__ == '__main__':
    main()
