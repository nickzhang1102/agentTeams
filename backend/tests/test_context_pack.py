"""ContextPack 单元测试。"""
import pytest
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from context.context_pack import ContextPack


class TestContextPackToMessages:
    """to_messages() 测试。"""

    def test_basic(self):
        pack = ContextPack(task_description="分析代码质量")
        msgs = pack.to_messages()
        assert len(msgs) == 1
        assert msgs[0] == {"role": "user", "content": "分析代码质量"}

    def test_with_system_prompt(self):
        pack = ContextPack(
            system_prompt="You are a code reviewer.",
            task_description="分析代码质量",
        )
        msgs = pack.to_messages()
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert "You are a code reviewer." in msgs[0]["content"]
        assert msgs[1]["role"] == "user"
        assert msgs[1]["content"] == "分析代码质量"

    def test_with_shared_evidence(self):
        pack = ContextPack(
            task_description="分析代码质量",
            shared_evidence=["文件 main.py: def foo(): pass"],
        )
        msgs = pack.to_messages()
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert "## 相关信息" in msgs[0]["content"]
        assert "文件 main.py" in msgs[0]["content"]

    def test_system_prompt_and_evidence_merged(self):
        pack = ContextPack(
            system_prompt="You are a reviewer.",
            task_description="分析",
            shared_evidence=["证据A", "证据B"],
        )
        msgs = pack.to_messages()
        assert len(msgs) == 2
        system_content = msgs[0]["content"]
        assert "You are a reviewer." in system_content
        assert "证据A" in system_content
        assert "证据B" in system_content

    def test_with_working_memory(self):
        pack = ContextPack(
            task_description="汇总结果",
            working_memory=[
                {"role": "user", "content": "之前的提问"},
                {"role": "assistant", "content": "之前的回答"},
            ],
        )
        msgs = pack.to_messages()
        assert len(msgs) == 3
        assert msgs[0] == {"role": "user", "content": "之前的提问"}
        assert msgs[1] == {"role": "assistant", "content": "之前的回答"}
        assert msgs[2]["content"] == "汇总结果"

    def test_empty_task_raises(self):
        pack = ContextPack(task_description="")
        with pytest.raises(ValueError, match="task_description"):
            pack.to_messages()

    def test_working_memory_invalid_role_skipped(self):
        pack = ContextPack(
            task_description="任务",
            working_memory=[{"role": "system", "content": "忽略"}],
        )
        msgs = pack.to_messages()
        # system role in working_memory is skipped
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"


class TestContextPackToTaskString:
    """to_task_string() 测试。"""

    def test_basic(self):
        pack = ContextPack(task_description="分析代码质量")
        result = pack.to_task_string()
        assert result == "分析代码质量"

    def test_with_shared_evidence(self):
        pack = ContextPack(
            task_description="分析代码质量",
            shared_evidence=["文件 main.py: def foo(): pass", "文件 utils.py: def bar(): pass"],
        )
        result = pack.to_task_string()
        assert "分析代码质量" in result
        assert "## 相关信息" in result
        assert "- 文件 main.py" in result
        assert "- 文件 utils.py" in result

    def test_empty_evidence_omitted(self):
        pack = ContextPack(task_description="任务", shared_evidence=[])
        result = pack.to_task_string()
        assert "## 相关信息" not in result

    def test_empty_task_raises(self):
        pack = ContextPack(task_description="")
        with pytest.raises(ValueError, match="task_description"):
            pack.to_task_string()

    def test_system_prompt_not_included(self):
        """system_prompt 不应出现在 task string 中（由 LLMService 处理）。"""
        pack = ContextPack(
            system_prompt="You are a reviewer.",
            task_description="任务",
        )
        result = pack.to_task_string()
        assert "You are a reviewer." not in result

    def test_includes_bounded_user_memory_and_recent_history(self):
        pack = ContextPack(
            task_description="继续分析",
            user_memory=["偏好保守方案"],
            working_memory=[
                {"role": "user", "content": f"历史{i}"}
                for i in range(8)
            ] + [{"role": "system", "content": "不应注入"}],
        )

        result = pack.to_task_string()

        assert "## 用户记忆" in result
        assert "偏好保守方案" in result
        assert "## 最近对话" in result
        assert "历史0" not in result
        assert "历史2" in result
        assert "历史7" in result
        assert "不应注入" not in result
