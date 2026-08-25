"""OpenHarness 配置定义

提供 OpenHarness 运行时配置的 schema 定义、重启标记集合和值获取辅助函数。
从 admin_api.py 路由中解耦，供 settings_api.py 复用。
"""

import os
from typing import Dict, Tuple

from sqlalchemy.orm import Session
from models import SystemConfig


# OpenHarness 配置项定义：key -> (描述, 默认值, 分组)
OPENHARNESS_CONFIG_SCHEMA: Dict[str, Tuple[str, str, str]] = {
    'OPENHARNESS_ENABLED': ('OpenHarness 总开关', 'true', 'core'),
    'OPENHARNESS_TOOLS_ENABLED': ('工具调用开关', 'true', 'core'),
    'OPENHARNESS_COORDINATOR_ENABLED': ('协调器开关（多 Agent 并行执行）', 'true', 'core'),
    'OPENHARNESS_TOOLS_TIMEOUT': ('工具执行超时（秒）', '300', 'execution'),
    'MAX_AGENT_ITERATIONS': ('Agent 最大迭代次数', '10', 'execution'),
    'MAX_AGENT_PARALLEL': ('最大并行 Agent 数', '5', 'execution'),
    'OPENHARNESS_MEMORY_ENABLED': ('记忆系统开关', 'true', 'memory'),
    'OPENHARNESS_MEMORY_MAX_MESSAGES': ('记忆压缩阈值（消息数）', '50', 'memory'),
    'OPENHARNESS_PERMISSION_ENABLED': ('权限治理开关', 'true', 'memory'),
    'OPENHARNESS_HOOKS_ENABLED': ('钩子系统开关', 'true', 'hooks'),
    'OPENHARNESS_HOOKS_TIMEOUT': ('钩子执行超时（秒）', '10', 'hooks'),
    'WORKSPACE_DIR': ('Agent 工作目录（文件读写基准路径）', 'data/workspace', 'paths'),
    # OpenHarness 原生环境变量分组
    'OPENHARNESS_MAX_TOKENS': ('API 最大输出 Token', '16384', 'openharness'),
    'OPENHARNESS_TIMEOUT': ('API 调用超时（秒）', '30', 'openharness'),
    'OPENHARNESS_CONFIG_DIR': ('OpenHarness 配置目录', '', 'openharness'),
}

# 需要重启服务才能生效的配置项
RESTART_REQUIRED_KEYS = {
    'OPENHARNESS_ENABLED',          # 总开关影响全局初始化
    'OPENHARNESS_TOOLS_ENABLED',    # 工具注册在启动时完成
    'OPENHARNESS_COORDINATOR_ENABLED',  # 协调器初始化在启动时
}


def get_openharness_config_value(key: str, db_session: Session) -> dict:
    """获取单个 OpenHarness 配置项的当前值和来源

    优先级：SystemConfig DB > 环境变量 > 默认值
    """
    db_setting = db_session.query(SystemConfig).filter_by(key=key).first()
    if db_setting:
        return {'value': db_setting.value, 'source': 'db'}

    env_val = os.environ.get(key)
    if env_val is not None:
        return {'value': env_val, 'source': 'env'}

    schema = OPENHARNESS_CONFIG_SCHEMA.get(key)
    if schema:
        return {'value': schema[1], 'source': 'default'}

    return {'value': '', 'source': 'unknown'}
