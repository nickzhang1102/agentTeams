"""
Tests for HarnessMemoryManager
"""
import pytest
import tempfile
import os
from pathlib import Path

from services.harness.harness_memory_manager import HarnessMemoryManager


@pytest.fixture
def temp_workspace():
    """创建临时工作空间"""
    workspace = tempfile.mkdtemp()
    yield workspace
    # 清理
    import shutil
    shutil.rmtree(workspace, ignore_errors=True)


@pytest.fixture
def memory_manager(temp_workspace):
    """创建记忆管理器实例"""
    return HarnessMemoryManager(workspace_dir=temp_workspace)


class TestHarnessMemoryManager:
    """HarnessMemoryManager 测试"""

    def test_initialization(self, memory_manager, temp_workspace):
        """测试初始化"""
        from pathlib import Path
        assert memory_manager.workspace_dir == Path(temp_workspace)
        assert memory_manager.memory_dir.exists()

    def test_save_context(self, memory_manager):
        """测试保存上下文"""
        conversation_id = 1
        context = {
            "messages": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"}
            ],
            "metadata": {"turn": 1}
        }

        memory_manager.save_context(conversation_id, context)

        # 验证文件已创建
        context_file = memory_manager.memory_dir / f"conversation_{conversation_id}" / "context.json"
        assert context_file.exists()

    def test_load_context(self, memory_manager):
        """测试加载上下文"""
        conversation_id = 1
        context = {
            "messages": [{"role": "user", "content": "Test"}],
            "metadata": {"turn": 1}
        }

        # 保存
        memory_manager.save_context(conversation_id, context)

        # 加载
        loaded = memory_manager.load_context(conversation_id)

        # 验证核心字段匹配
        assert loaded["messages"] == context["messages"]
        assert loaded["metadata"] == context["metadata"]
        assert loaded["conversation_id"] == conversation_id

    def test_load_nonexistent_context(self, memory_manager):
        """测试加载不存在的上下文"""
        result = memory_manager.load_context(999)
        assert result is None

    def test_save_session_state(self, memory_manager):
        """测试保存会话状态"""
        leader_session_id = 1
        harness_session_id = "oh-session-123"
        session_state = {
            "state": "monitoring",
            "agents": ["agent1", "agent2"],
            "results": []
        }

        memory_manager.save_session_state(leader_session_id, harness_session_id, session_state)

        # 验证
        session_file = memory_manager.memory_dir / f"session_{leader_session_id}" / "state.json"
        assert session_file.exists()

    def test_load_session_state(self, memory_manager):
        """测试加载会话状态"""
        leader_session_id = 1
        harness_session_id = "oh-session-456"
        session_state = {"state": "completed"}

        memory_manager.save_session_state(leader_session_id, harness_session_id, session_state)

        loaded = memory_manager.load_session_state(leader_session_id)

        assert loaded["harness_session_id"] == harness_session_id
        assert loaded["state"] == "completed"

    def test_load_nonexistent_session_state(self, memory_manager):
        """测试加载不存在的会话状态"""
        result = memory_manager.load_session_state(999)
        assert result is None

    def test_compact_memory(self, memory_manager):
        """测试记忆压缩"""
        conversation_id = 1

        # 创建大量上下文
        large_context = {
            "messages": [{"role": "user", "content": f"Message {i}"} for i in range(100)],
            "metadata": {"turn": 100}
        }

        memory_manager.save_context(conversation_id, large_context)

        # 压缩
        memory_manager.compact_memory(conversation_id, max_messages=10)

        # 验证
        compacted = memory_manager.load_context(conversation_id)
        assert len(compacted["messages"]) <= 10
        assert "compaction_summary" in compacted.get("metadata", {})
