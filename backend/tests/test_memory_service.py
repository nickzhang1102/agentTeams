"""
MemoryService 测试。

覆盖：add_memory / prune / search / get_for_context / extract_from_conversation。
"""
import pytest
import uuid
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

from models import AgentMemory, User, Conversation
from services.memory_service import MemoryService
from utils.time_utils import utcnow_naive


@pytest.fixture
def sample_user(db_session):
    """创建测试用户（唯一用户名避免冲突）。"""
    user = User(username=f"memory_test_{uuid.uuid4().hex[:8]}")
    user.set_password("Test1234!")
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def memory_service(db_session):
    """创建 MemoryService 实例（无 LLM）。"""
    return MemoryService(db_session=db_session, llm_service=None)


@pytest.fixture
def memory_service_with_llm(db_session):
    """创建 MemoryService 实例（带 mock LLM）。"""
    mock_llm = MagicMock()
    mock_llm.call_structured = AsyncMock()
    return MemoryService(db_session=db_session, llm_service=mock_llm)


# ==================== Step 3: add_memory / prune ====================


class TestAddMemory:
    """add_memory 测试。"""

    def test_add_basic_memory(self, memory_service, sample_user, db_session):
        """基本新增记忆。"""
        mem = memory_service.add_memory(
            user_id=sample_user.id,
            content="用户偏好中西医结合",
            metadata={"type": "preference", "source": "conversation", "tags": ["医疗"]},
            importance=0.8,
        )
        db_session.commit()

        assert mem.id is not None
        assert mem.user_id == sample_user.id
        assert mem.content == "用户偏好中西医结合"
        assert mem.metadata_["type"] == "preference"
        assert mem.importance == 0.8

    def test_add_memory_default_metadata(self, memory_service, sample_user, db_session):
        """metadata 为 None 时使用默认值。"""
        mem = memory_service.add_memory(user_id=sample_user.id, content="test")
        db_session.commit()

        assert mem.metadata_ == {"type": "fact", "source": "unknown"}

    def test_add_memory_importance_clamp(self, memory_service, sample_user, db_session):
        """importance 超范围自动 clamp。"""
        mem_high = memory_service.add_memory(
            user_id=sample_user.id, content="high", importance=1.5
        )
        mem_low = memory_service.add_memory(
            user_id=sample_user.id, content="low", importance=-0.3
        )
        db_session.commit()

        assert mem_high.importance == 1.0
        assert mem_low.importance == 0.0

    def test_add_memory_invalid_user_id(self, memory_service):
        """user_id 非法时 raise ValueError。"""
        with pytest.raises(ValueError, match="user_id must be positive"):
            memory_service.add_memory(user_id=None, content="test")

        with pytest.raises(ValueError, match="user_id must be positive"):
            memory_service.add_memory(user_id=-1, content="test")

    def test_add_memory_with_source(self, memory_service, sample_user, db_session):
        """带来源追溯的新增（不传 source ID 时为 None）。"""
        mem = memory_service.add_memory(
            user_id=sample_user.id,
            content="test no source",
        )
        db_session.commit()

        assert mem.source_conversation_id is None
        assert mem.source_message_id is None


class TestPrune:
    """prune 测试。"""

    def test_prune_removes_old_low_importance(self, memory_service, sample_user, db_session):
        """清理过期低重要性记忆。"""
        from datetime import datetime, timedelta

        # 新建一条过期 + 低重要性记忆
        old_mem = AgentMemory(
            user_id=sample_user.id,
            content="old low importance",
            metadata_={"type": "fact"},
            importance=0.1,
            created_at=utcnow_naive() - timedelta(days=400),
        )
        db_session.add(old_mem)

        # 新建一条高重要性记忆（不应被删除）
        high_mem = memory_service.add_memory(
            user_id=sample_user.id,
            content="high importance",
            importance=0.9,
        )
        db_session.commit()

        deleted = memory_service.prune(user_id=sample_user.id, max_age_days=365, min_importance=0.2)
        db_session.commit()

        assert deleted == 1
        # 高重要性记忆仍存在
        remaining = db_session.query(AgentMemory).filter_by(user_id=sample_user.id).all()
        assert len(remaining) == 1
        assert remaining[0].content == "high importance"

    def test_prune_invalid_user_id(self, memory_service):
        """user_id 非法时 raise ValueError。"""
        with pytest.raises(ValueError, match="user_id must be positive"):
            memory_service.prune(user_id=0)


# ==================== Step 4: search ====================


class TestSearch:
    """search 测试。"""

    def _seed_memories(self, memory_service, user_id, db_session):
        """预置测试记忆。"""
        memories = [
            ("用户偏好中西医结合治疗", {"type": "preference", "tags": ["医疗"]}, 0.8),
            ("决定采用保守治疗方案", {"type": "decision", "tags": ["医疗"]}, 0.9),
            ("用户有高血压病史", {"type": "fact", "tags": ["病史"]}, 0.7),
            ("不使用含激素药物", {"type": "constraint", "tags": ["药物"]}, 0.6),
            ("喜欢简洁风格的报告", {"type": "preference", "tags": ["风格"]}, 0.5),
        ]
        for content, meta, imp in memories:
            memory_service.add_memory(
                user_id=user_id, content=content, metadata=meta, importance=imp
            )
        db_session.commit()

    def test_search_all(self, memory_service, sample_user, db_session):
        """无过滤条件返回全部。"""
        self._seed_memories(memory_service, sample_user.id, db_session)
        results = memory_service.search(user_id=sample_user.id, query="")
        assert len(results) == 5

    def test_search_by_type(self, memory_service, sample_user, db_session):
        """按类型过滤。"""
        self._seed_memories(memory_service, sample_user.id, db_session)
        results = memory_service.search(
            user_id=sample_user.id, query="", memory_type="preference"
        )
        assert len(results) == 2
        assert all(r.metadata_.get("type") == "preference" for r in results)

    def test_search_by_keyword(self, memory_service, sample_user, db_session):
        """按关键词过滤。"""
        self._seed_memories(memory_service, sample_user.id, db_session)
        results = memory_service.search(user_id=sample_user.id, query="治疗")
        assert len(results) == 2  # "中西医结合治疗" + "保守治疗方案"

    def test_search_limit(self, memory_service, sample_user, db_session):
        """limit 截断。"""
        self._seed_memories(memory_service, sample_user.id, db_session)
        results = memory_service.search(user_id=sample_user.id, query="", limit=2)
        assert len(results) == 2

    def test_search_order_by_importance(self, memory_service, sample_user, db_session):
        """结果按 importance 降序。"""
        self._seed_memories(memory_service, sample_user.id, db_session)
        results = memory_service.search(user_id=sample_user.id, query="")
        importances = [r.importance for r in results]
        assert importances == sorted(importances, reverse=True)

    def test_search_empty_result(self, memory_service, sample_user, db_session):
        """无匹配时返回空列表。"""
        results = memory_service.search(user_id=sample_user.id, query="不存在的关键词")
        assert results == []

    def test_search_isolates_users(self, memory_service, sample_user, db_session):
        """不同用户记忆隔离。"""
        self._seed_memories(memory_service, sample_user.id, db_session)

        other_user = User(username=f"other_{uuid.uuid4().hex[:8]}")
        other_user.set_password("Test1234!")
        db_session.add(other_user)
        db_session.flush()

        memory_service.add_memory(user_id=other_user.id, content="other user memory")
        db_session.commit()

        results = memory_service.search(user_id=other_user.id, query="")
        assert len(results) == 1
        assert results[0].content == "other user memory"

    def test_search_invalid_user_id(self, memory_service):
        """user_id 非法时 raise ValueError。"""
        with pytest.raises(ValueError, match="user_id must be positive"):
            memory_service.search(user_id=-1, query="test")


# ==================== Step 6: get_for_context ====================


class TestGetForContext:
    """get_for_context 测试。"""

    def test_returns_string_list(self, memory_service, sample_user, db_session):
        """返回 list[str]。"""
        memory_service.add_memory(
            user_id=sample_user.id,
            content="用户偏好简洁报告",
            metadata={"type": "preference"},
            importance=0.8,
        )
        db_session.commit()

        result = memory_service.get_for_context(
            user_id=sample_user.id, query="报告"
        )
        assert isinstance(result, list)
        assert all(isinstance(s, str) for s in result)
        assert "用户偏好简洁报告" in result

    def test_empty_when_no_memories(self, memory_service, sample_user, db_session):
        """无记忆时返回空列表。"""
        result = memory_service.get_for_context(
            user_id=sample_user.id, query="anything"
        )
        assert result == []


# ==================== Step 5: extract_from_conversation ====================


class TestExtractFromConversation:
    """extract_from_conversation 测试。"""

    @pytest.mark.asyncio
    async def test_extract_success(self, memory_service_with_llm, sample_user, db_session):
        """正常提取并持久化。"""
        from schemas.memory import ExtractedMemory, MemoryExtractionResult

        # 创建测试对话（满足 FK 约束）
        conv = Conversation(title="test", user_id=sample_user.id)
        db_session.add(conv)
        db_session.flush()

        memory_service_with_llm.llm_service.call_structured.return_value = MemoryExtractionResult(
            memories=[
                ExtractedMemory(
                    content="用户偏好中西医结合",
                    memory_type="preference",
                    importance=0.8,
                    tags=["医疗"],
                ),
            ]
        )

        messages = [
            {"role": "user", "content": "我偏好中西医结合治疗"},
            {"role": "assistant", "content": "好的，我会结合中西医方案"},
        ]

        result = await memory_service_with_llm.extract_from_conversation(
            user_id=sample_user.id,
            conversation_id=conv.id,
            messages=messages,
        )

        assert len(result) == 1
        assert result[0].content == "用户偏好中西医结合"
        assert result[0].metadata_["type"] == "preference"

        # 验证数据库持久化
        db_session.commit()
        all_memories = db_session.query(AgentMemory).filter_by(user_id=sample_user.id).all()
        assert len(all_memories) == 1

    @pytest.mark.asyncio
    async def test_extract_empty_messages(self, memory_service_with_llm, sample_user):
        """空消息列表返回空。"""
        result = await memory_service_with_llm.extract_from_conversation(
            user_id=sample_user.id, conversation_id=1, messages=[]
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_extract_llm_failure(self, memory_service_with_llm, sample_user):
        """LLM 调用失败时返回空列表。"""
        memory_service_with_llm.llm_service.call_structured.side_effect = Exception("LLM error")

        messages = [{"role": "user", "content": "test"}]
        result = await memory_service_with_llm.extract_from_conversation(
            user_id=sample_user.id, conversation_id=1, messages=messages
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_extract_no_llm_service(self, memory_service, sample_user):
        """无 LLM 服务时返回空列表。"""
        result = await memory_service.extract_from_conversation(
            user_id=sample_user.id,
            conversation_id=1,
            messages=[{"role": "user", "content": "test"}],
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_extract_invalid_user_id(self, memory_service):
        """user_id 非法时 raise ValueError。"""
        with pytest.raises(ValueError, match="user_id must be positive"):
            await memory_service.extract_from_conversation(
                user_id=0, conversation_id=1, messages=[{"role": "user", "content": "test"}]
            )

