"""Admin 共享工具函数

提供 admin 路由模块共同依赖的工具函数：
- get_file_manager(): 获取 AgentFileManager 实例
- paginate(): SQLAlchemy 查询分页

注：AgentConfig 序列化统一使用 AgentConfig.to_dict()（models.py）。
"""

import os
import logging

from config import config as app_config
from services.agent_file_manager import AgentFileManager


logger = logging.getLogger(__name__)


def get_file_manager() -> AgentFileManager:
    """获取AgentFileManager实例（延迟初始化）"""
    agents_dir = app_config.get(
        'AGENTS_DIR',
        os.path.join(os.path.dirname(__file__), '..', '..', '.claude/agents')
    )
    return AgentFileManager(agents_dir)


def paginate(query, page: int, per_page: int) -> dict:
    """原生 SQLAlchemy 分页辅助函数

    Args:
        query: SQLAlchemy query 对象
        page: 页码
        per_page: 每页数量

    Returns:
        dict: {items, total, page, per_page, pages}
    """
    total = query.count()
    offset = (page - 1) * per_page
    items = query.offset(offset).limit(per_page).all()
    pages = (total + per_page - 1) // per_page if total > 0 else 0
    return {
        'items': items,
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': pages
    }
