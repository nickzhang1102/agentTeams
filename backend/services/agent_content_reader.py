"""Agent 内容统一读取层

替代 AgentMetadataParser 作为 Leader 全链路的 Agent 内容入口。
优先从 DB 读取 content 字段，fallback 到 .md 文件。
"""

import json
import logging
from typing import Optional

from models import AgentConfig

logger = logging.getLogger(__name__)


class AgentContentReader:
    """统一读取层：DB Agent 直接读 content 字段；File Agent 读 .md 文件。

    Args:
        db_session: SQLAlchemy Session（由调用方注入，请求/工作流级别生命周期）
    """

    def __init__(self, db_session) -> None:
        self._db = db_session

    def get_agent_prompt(self, agent_id: str) -> str:
        """返回完整 system prompt。

        优先级：
        1. AgentConfig.content 非空 → 直接返回
        2. AgentConfig.file_path 有值且文件存在 → 读 .md 文件
        3. 均不存在 → raise FileNotFoundError
        """
        agent = self._db.query(AgentConfig).filter_by(agent_id=agent_id).first()
        if not agent:
            raise FileNotFoundError(f'Agent not found: {agent_id}')

        # 优先 DB content
        if agent.content:
            return agent.content

        # fallback 到文件
        if agent.file_path and agent.file_exists:
            try:
                with open(agent.file_path, 'r', encoding='utf-8') as f:
                    return f.read()
            except (FileNotFoundError, IOError) as e:
                logger.warning(f'Agent file read failed: {agent_id}, {e}')

        raise FileNotFoundError(f'Agent content not available: {agent_id}')

    def get_agent_metadata(self, agent_id: str) -> Optional[dict]:
        """返回 Agent 元数据（name, description, capabilities, tags 等）。"""
        agent = self._db.query(AgentConfig).filter_by(agent_id=agent_id).first()
        if not agent:
            return None
        return agent.to_dict()

    def get_all_agents(
        self,
        category: Optional[str] = None,
        tags: Optional[list] = None,
        source: Optional[str] = None,
        is_enabled: Optional[bool] = None,
        is_system: Optional[bool] = None,
        created_by: Optional[int] = None,
    ) -> list[dict]:
        """返回 Agent 列表，支持多维筛选。不返回 content 字段。"""
        query = self._db.query(AgentConfig)

        if is_enabled is not None:
            query = query.filter_by(is_enabled=is_enabled)
        if is_system is not None:
            query = query.filter_by(is_system=is_system)
        if source is not None:
            query = query.filter_by(source=source)
        if created_by is not None:
            query = query.filter(AgentConfig.created_by == created_by)

        # JSONB 包含过滤（@> 操作符，精确匹配）
        if tags:
            tag_list = tags if isinstance(tags, list) else [tags]
            for tag in tag_list:
                query = query.filter(AgentConfig.tags.op('@>')(json.dumps([tag])))

        agents = query.order_by(AgentConfig.priority.desc(), AgentConfig.agent_id).all()
        result = []
        for a in agents:
            d = a.to_dict()
            # 列表不返回 content（太大）
            d.pop('content', None)
            result.append(d)
        return result


def get_agent_content_reader(db_session=None) -> AgentContentReader:
    """创建 AgentContentReader 实例。

    Args:
        db_session: SQLAlchemy Session（必须由调用方提供）

    Raises:
        ValueError: db_session 为 None 时
    """
    if db_session is None:
        raise ValueError(
            'db_session is required for AgentContentReader. '
            'Callers must provide a Session to avoid resource leaks.'
        )
    return AgentContentReader(db_session)
