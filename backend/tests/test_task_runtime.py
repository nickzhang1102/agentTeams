"""
TaskRuntime Tests

测试 TaskRuntime.check_and_adjust 快速路径的动态子任务追加逻辑。
回归测试：快速路径 add_subtask 必须同步更新 decomposition。
"""
import pytest
from unittest.mock import MagicMock, patch

from leader.task_runtime import TaskRuntime
from leader.task_types import MAX_SUBTASKS
from schemas.leader import AdjustmentDecisionOutput


def _make_decomposition(subtask_count: int = 2) -> dict:
    """构建测试用的 TaskDecomposition"""
    return {
        "agent_id": "test-agent",
        "agent_name": "Test Agent",
        "subtasks": [
            {
                "id": f"subtask_{i}",
                "goal": f"任务 {i}",
                "tools": ["web_search"],
                "status": "pending",
                "result": "",
            }
            for i in range(subtask_count)
        ],
    }


def _make_runtime(subtask_count: int = 2, completed: int = 1) -> TaskRuntime:
    """构建带已完成子任务的 TaskRuntime（跳过 __init__）

    前 completed 个子任务标记为 completed，其余保持 pending。
    """
    decomp = _make_decomposition(subtask_count)
    for i in range(min(completed, subtask_count)):
        decomp["subtasks"][i]["status"] = "completed"
        decomp["subtasks"][i]["result"] = "ok"
    runtime = TaskRuntime.__new__(TaskRuntime)
    runtime.decomposition = decomp
    runtime.completed_subtasks = [
        {"id": f"subtask_{i}", "goal": f"已完成 {i}", "result": "ok"}
        for i in range(completed)
    ]
    runtime.session_id = "test-session"
    runtime.allowed_tools = None
    return runtime


@patch("leader.task_runtime.push_sse_event")
class TestCheckAndAdjustQuickPath:
    """check_and_adjust 快速路径测试"""

    def test_short_result_adds_subtask_to_decomposition(self, mock_push):
        """回归测试：快速路径 add_subtask 必须追加到 decomposition"""
        runtime = _make_runtime(subtask_count=2, completed=1)
        initial_count = len(runtime.decomposition["subtasks"])

        decision = runtime.check_and_adjust("短结果")

        assert decision["action"] == "add_subtask"
        assert len(runtime.decomposition["subtasks"]) == initial_count + 1
        new_st = runtime.decomposition["subtasks"][-1]
        assert new_st["status"] == "pending"
        assert new_st["added_dynamically"] is True
        assert new_st["goal"] == "补充信息搜索"

    def test_short_result_filters_dynamically_added_tool(self, mock_push):
        runtime = _make_runtime(subtask_count=2, completed=1)
        runtime.allowed_tools = []

        decision = runtime.check_and_adjust("短结果")

        assert decision["new_subtasks"][0]["tools"] == []

    def test_short_result_emits_task_adjusted_event(self, mock_push):
        """快速路径 add_subtask 必须触发 SSE 事件"""
        runtime = _make_runtime(subtask_count=2, completed=1)

        runtime.check_and_adjust("短")

        mock_push.assert_called_once()
        event = mock_push.call_args[0][1]
        assert event["type"] == "task_adjusted"
        assert event["action"] == "add_subtask"

    def test_short_result_new_subtask_is_gettable(self, mock_push):
        """新增的 pending 子任务必须能被 get_next_subtask 发现"""
        runtime = _make_runtime(subtask_count=1, completed=1)
        # 所有初始子任务已完成
        assert runtime.get_next_subtask() is None

        runtime.check_and_adjust("短")

        next_st = runtime.get_next_subtask()
        assert next_st is not None
        assert next_st["goal"] == "补充信息搜索"

    def test_failed_short_result_does_not_add_search_subtask(self, mock_push):
        """LLM/工具失败不应被当作信息不足而追加搜索子任务。"""
        runtime = _make_runtime(subtask_count=2, completed=1)
        initial_count = len(runtime.decomposition["subtasks"])

        decision = runtime.check_and_adjust("[失败] LLM 分析超时或失败：Request timed out.")

        assert decision["action"] == "skip"
        assert len(runtime.decomposition["subtasks"]) == initial_count
        mock_push.assert_not_called()

    def test_long_result_does_not_trigger_quick_path(self, mock_push):
        """无缺口信号的正常结果不应调用调整模型。"""
        runtime = _make_runtime(subtask_count=2, completed=1)
        runtime._llm_service = MagicMock()
        initial_count = len(runtime.decomposition["subtasks"])

        with patch.object(runtime, '_call_llm_adjust') as adjust:
            runtime.check_and_adjust("该结果已覆盖目标并给出明确结论。" * 10)

        assert len(runtime.decomposition["subtasks"]) == initial_count
        adjust.assert_not_called()

    def test_gap_signal_uses_llm_adjustment(self, mock_push):
        runtime = _make_runtime(subtask_count=2, completed=1)
        with patch.object(runtime, '_call_llm_adjust', return_value={
            "action": "continue", "reason": "已检查", "new_subtasks": []
        }) as adjust:
            runtime.check_and_adjust("现有证据存在冲突，需要进一步核实。" * 4)

        adjust.assert_called_once()

    def test_llm_adjustment_filters_unauthorized_tools(self, mock_push):
        class StubLLMService:
            async def call_structured(self, messages, response_model, temperature):
                return AdjustmentDecisionOutput(
                    action="add_subtask",
                    reason="补充检索",
                    new_subtasks=[{
                        "id": "dynamic_1",
                        "goal": "检索资料",
                        "tools": ["bash", "mcp__exa__search"],
                    }],
                )

        runtime = _make_runtime(subtask_count=2, completed=1)
        runtime._llm_service = StubLLMService()
        runtime.allowed_tools = ["mcp__exa__*"]

        decision = runtime._call_llm_adjust("需要补充资料", completed_count=1)

        assert decision["new_subtasks"][0]["tools"] == ["mcp__exa__search"]

    def test_english_adjustment_uses_locale_instruction(self, mock_push):
        class CapturingLLMService:
            def __init__(self):
                self.messages = None

            async def call_structured(self, messages, response_model, temperature):
                self.messages = messages
                return AdjustmentDecisionOutput(
                    action="continue",
                    reason="The current plan remains sufficient",
                    new_subtasks=[],
                )

        runtime = _make_runtime(subtask_count=2, completed=1)
        runtime._locale = "en-US"
        runtime._llm_service = CapturingLLMService()

        decision = runtime._call_llm_adjust("More evidence may be needed", completed_count=1)

        assert "English (en-US)" in runtime._llm_service.messages[0]["content"]
        assert runtime._llm_service.messages[-1]["role"] == "user"
        assert decision["reason"] == "The current plan remains sufficient"

    def test_english_quick_path_uses_english_fixed_text(self, mock_push):
        runtime = _make_runtime(subtask_count=2, completed=1)
        runtime._locale = "en-US"

        decision = runtime.check_and_adjust("short result")

        assert decision["new_subtasks"][0]["goal"] == "Search for additional information"
        assert decision["reason"].startswith("The available information is insufficient")

    def test_max_subtasks_guard_blocks_add(self, mock_push):
        """达到上限时不应新增子任务"""
        runtime = _make_runtime(subtask_count=MAX_SUBTASKS, completed=MAX_SUBTASKS)

        decision = runtime.check_and_adjust("短")

        assert decision["action"] == "continue"
        assert "上限" in decision["reason"]

    def test_llm_abort_is_coerced_to_continue(self, mock_push):
        """LLM 返回 legacy abort 时，不应中止剩余 pending 子任务。"""

        class StubLLMService:
            async def call_structured(self, messages, response_model, temperature):
                return AdjustmentDecisionOutput(
                    action="abort",
                    reason="高风险，建议终止",
                    new_subtasks=[],
                )

        runtime = _make_runtime(subtask_count=3, completed=1)
        runtime._llm_service = StubLLMService()

        decision = runtime.check_and_adjust(
            "现有分析已经覆盖主要事实与建议，但不同数据源之间仍存在冲突，"
            "需要进一步核实关键指标的统计口径和时间范围后再继续。"
        )

        assert decision["action"] == "continue"
        assert "忽略中途终止建议" in decision["reason"]
        assert runtime.get_next_subtask()["id"] == "subtask_1"
