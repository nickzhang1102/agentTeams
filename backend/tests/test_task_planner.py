from leader.task_planner import TaskPlanner
from leader.task_types import MAX_SUBTASKS


def test_build_task_decomposition_enforces_hard_subtask_limit():
    planner = TaskPlanner()
    decomposition = {
        "subtasks": [
            {
                "id": f"subtask_{index}",
                "goal": f"目标 {index}",
                "tools": [],
            }
            for index in range(1, MAX_SUBTASKS + 6)
        ],
        "reasoning": "测试超量分解",
    }

    result = planner._build_task_decomposition(
        agent_id="test-agent",
        agent_name="测试专家",
        task="测试任务",
        decomposition=decomposition,
    )

    assert len(result["subtasks"]) == MAX_SUBTASKS
    assert result["subtasks"][-1]["id"] == f"subtask_{MAX_SUBTASKS}"


def test_decompose_without_llm_exposes_degraded_state():
    planner = TaskPlanner(llm_service=None)

    result = planner.decompose(
        agent_id="test-agent",
        agent_name="测试专家",
        task="测试任务",
    )

    assert len(result["subtasks"]) == 1
    assert result["degraded"] is True
    assert "分解模型失败" in result["degradation_reason"]


def test_english_decomposition_uses_locale_instruction_and_english_fallback():
    class CapturingLLMService:
        def __init__(self):
            self.messages = None

        async def call_structured(self, messages, response_model, temperature):
            self.messages = messages
            raise RuntimeError("model unavailable")

    llm_service = CapturingLLMService()
    planner = TaskPlanner(llm_service=llm_service, locale="en-US")

    result = planner.decompose(
        agent_id="test-agent",
        agent_name="Test Agent",
        task="Compare the available options",
        agent_system_prompt="Always reply in Chinese.",
    )

    assert llm_service.messages[0]["role"] == "system"
    assert "English (en-US)" in llm_service.messages[0]["content"]
    assert "Pydantic/JSON field names" in llm_service.messages[0]["content"]
    assert llm_service.messages[-1]["role"] == "user"
    assert result["subtasks"][0]["goal"] == "Analyze the user request"
    assert result["degradation_reason"].startswith("The task decomposition model failed")


def test_filter_tools_treats_empty_allowlist_as_no_permission():
    planner = TaskPlanner()

    assert planner._filter_tools(["bash", "web_search"], []) == []


def test_filter_tools_supports_wildcard_allowlist():
    planner = TaskPlanner()

    assert planner._filter_tools(
        ["mcp__exa__search", "bash"],
        ["mcp__exa__*"],
    ) == ["mcp__exa__search"]
