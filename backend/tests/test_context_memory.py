"""
ContextPack + ContextBuilder 扩展测试（user_memory 层）。
"""
import pytest
from context.context_pack import ContextPack
from context.context_builder import ContextBuilder


class TestContextPackUserMemory:
    """ContextPack user_memory 字段测试。"""

    def test_user_memory_in_system_message(self):
        """user_memory 非空时 system message 含'用户记忆'段。"""
        pack = ContextPack(
            system_prompt="You are a medical expert.",
            task_description="分析体检报告",
            user_memory=["用户偏好中西医结合", "用户有高血压病史"],
        )
        messages = pack.to_messages()

        assert len(messages) >= 2
        system_msg = messages[0]
        assert system_msg["role"] == "system"
        assert "用户记忆" in system_msg["content"]
        assert "用户偏好中西医结合" in system_msg["content"]
        assert "用户有高血压病史" in system_msg["content"]

    def test_no_user_memory_section_when_empty(self):
        """user_memory 为空时不生成'用户记忆'段。"""
        pack = ContextPack(
            system_prompt="You are a medical expert.",
            task_description="分析体检报告",
        )
        messages = pack.to_messages()

        system_msg = messages[0]
        assert "用户记忆" not in system_msg["content"]

    def test_original_four_layers_unchanged(self):
        """原有四层行为不变。"""
        pack = ContextPack(
            system_prompt="System",
            shared_evidence=["证据1", "证据2"],
            task_description="任务",
            working_memory=[{"role": "user", "content": "历史"}],
        )
        messages = pack.to_messages()

        # system + working_memory user + task
        assert len(messages) == 3
        assert messages[0]["role"] == "system"
        assert "相关信息" in messages[0]["content"]
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "历史"
        assert messages[2]["role"] == "user"
        assert messages[2]["content"] == "任务"


class TestContextBuilderUserMemory:
    """ContextBuilder.build_for_agents() user_memory 参数测试。"""

    def test_with_user_memory(self):
        """传入 user_memory → ContextPack.user_memory 非空。"""
        pack = ContextBuilder.build_for_agents(
            user_message="分析报告",
            user_memory=["偏好简洁报告", "有高血压病史"],
        )
        assert pack.user_memory == ["偏好简洁报告", "有高血压病史"]

    def test_without_user_memory(self):
        """不传时 user_memory 默认为空列表。"""
        pack = ContextBuilder.build_for_agents(user_message="分析报告")
        assert pack.user_memory == []

    def test_existing_params_unaffected(self):
        """原有参数不受影响。"""
        pack = ContextBuilder.build_for_agents(
            user_message="任务",
            shared_evidence=["证据"],
            working_memory=[{"role": "user", "content": "历史"}],
            user_memory=["记忆"],
        )
        assert pack.shared_evidence == ["证据"]
        assert pack.working_memory == [{"role": "user", "content": "历史"}]
        assert pack.user_memory == ["记忆"]
