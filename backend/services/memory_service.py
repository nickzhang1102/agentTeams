"""
用户长期记忆服务。

提供记忆 CRUD、检索（JSONB + 关键词）和对话结束后的自动提取。
所有查询强制带 user_id，不得跨用户召回。
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from models import AgentMemory
from schemas.memory import MemoryExtractionResult
from utils.time_utils import utcnow_naive

logger = logging.getLogger(__name__)

DEFAULT_SEARCH_LIMIT = 5
DEFAULT_PRUNE_DAYS = 365
DEFAULT_PRUNE_MIN_IMPORTANCE = 0.2


class MemoryService:
    """用户长期记忆服务。"""

    def __init__(self, db_session: Session, llm_service=None):
        self.db_session = db_session
        self.llm_service = llm_service

    # ==================== CRUD ====================

    def add_memory(
        self,
        user_id: int,
        content: str,
        metadata: Optional[dict] = None,
        importance: float = 0.5,
        source_conversation_id: Optional[int] = None,
        source_message_id: Optional[int] = None,
    ) -> AgentMemory:
        """新增一条记忆。importance 超出 [0,1] 自动 clamp。"""
        if user_id is None or user_id <= 0:
            raise ValueError(f"user_id must be positive, got {user_id}")

        importance = max(0.0, min(1.0, importance))
        if metadata is None:
            metadata = {"type": "fact", "source": "unknown"}

        memory = AgentMemory(
            user_id=user_id,
            content=content,
            metadata_=metadata,
            importance=importance,
            source_conversation_id=source_conversation_id,
            source_message_id=source_message_id,
        )
        self.db_session.add(memory)
        self.db_session.flush()
        return memory

    def prune(
        self,
        user_id: int,
        max_age_days: int = DEFAULT_PRUNE_DAYS,
        min_importance: float = DEFAULT_PRUNE_MIN_IMPORTANCE,
    ) -> int:
        """清理低重要性过期记忆。返回删除条数。"""
        if user_id is None or user_id <= 0:
            raise ValueError(f"user_id must be positive, got {user_id}")

        cutoff = utcnow_naive() - timedelta(days=max_age_days)
        deleted = (
            self.db_session.query(AgentMemory)
            .filter(
                AgentMemory.user_id == user_id,
                AgentMemory.created_at < cutoff,
                AgentMemory.importance < min_importance,
            )
            .delete()
        )
        self.db_session.flush()
        return deleted

    # ==================== 检索 ====================

    def search(
        self,
        user_id: int,
        query: str,
        limit: int = DEFAULT_SEARCH_LIMIT,
        memory_type: Optional[str] = None,
    ) -> list[AgentMemory]:
        """检索用户记忆。JSONB @> 类型过滤 + ILIKE 关键词 + importance 排序。"""
        if user_id is None or user_id <= 0:
            raise ValueError(f"user_id must be positive, got {user_id}")

        q = self.db_session.query(AgentMemory).filter(
            AgentMemory.user_id == user_id
        )

        if memory_type:
            q = q.filter(AgentMemory.metadata_.op("->>")("type") == memory_type)

        if query:
            q = q.filter(AgentMemory.content.ilike(f"%{query}%"))

        return q.order_by(desc(AgentMemory.importance)).limit(limit).all()

    def get_for_context(
        self,
        user_id: int,
        query: str,
        limit: int = DEFAULT_SEARCH_LIMIT,
    ) -> list[str]:
        """为 ContextBuilder 检索并格式化记忆，返回 content 字符串列表。"""
        memories = self.search(user_id=user_id, query=query, limit=limit)
        return [m.content for m in memories]

    # ==================== 对话结束后提取 ====================

    async def extract_from_conversation(
        self,
        user_id: int,
        conversation_id: int,
        messages: list[dict],
    ) -> list[AgentMemory]:
        """对话结束后，用 LLM 提取值得保留的记忆。失败返回空列表。"""
        if user_id is None or user_id <= 0:
            raise ValueError(f"user_id must be positive, got {user_id}")

        if not self.llm_service or not messages:
            return []

        try:
            conversation_text = "\n".join(
                f"[{m.get('role', 'unknown')}]: {m.get('content', '')}"
                for m in messages
                if m.get('content')
            )

            if not conversation_text.strip():
                return []

            result: MemoryExtractionResult = await self.llm_service.call_structured(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是一个记忆提取助手。从对话中提取值得长期保留的信息。\n"
                            "只提取以下类型：\n"
                            "- preference: 用户偏好（习惯、风格、方案偏好）\n"
                            "- decision: 用户做出的决策或结论\n"
                            "- fact: 用户透露的重要事实（背景信息、关键数据）\n"
                            "- constraint: 用户设定的约束或限制\n\n"
                            "不要提取：临时信息、已过时的内容、通用知识。\n"
                            "每条记忆应是一句话摘要，简洁且自包含。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"从以下对话中提取值得长期保留的记忆：\n\n{conversation_text}",
                    },
                ],
                response_model=MemoryExtractionResult,
                max_retries=2,
                temperature=0.0,
            )

            if not result.memories:
                return []

            saved = []
            for mem in result.memories:
                agent_memory = self.add_memory(
                    user_id=user_id,
                    content=mem.content,
                    metadata={
                        "type": mem.memory_type,
                        "source": "conversation",
                        "tags": mem.tags,
                    },
                    importance=mem.importance,
                    source_conversation_id=conversation_id,
                )
                saved.append(agent_memory)

            logger.info(
                f"Extracted {len(saved)} memories for user {user_id} "
                f"from conversation {conversation_id}"
            )
            return saved

        except Exception:
            logger.warning("Memory extraction failed", exc_info=True)
            return []

