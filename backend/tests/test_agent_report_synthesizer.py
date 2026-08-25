from leader.agent_report_synthesizer import AgentReportSynthesizer
from unittest.mock import patch


class FakeLLMService:
    def __init__(self, max_output_tokens):
        self.max_output_tokens = max_output_tokens
        self.call_args = None

    def get_max_output_tokens(self):
        return self.max_output_tokens

    def call_sync(self, message, system_prompt=None, max_tokens=None, max_attempts=None, **kwargs):
        self.call_args = {
            "message": message,
            "system_prompt": system_prompt,
            "max_tokens": max_tokens,
            "max_attempts": max_attempts,
            **kwargs,
        }
        return "# 合成报告"


def _completed_subtasks():
    return [
        {"id": "subtask_1", "goal": "任务一", "status": "completed", "result": "结果一"},
        {"id": "subtask_2", "goal": "任务二", "status": "completed", "result": "结果二"},
    ]


def _single_completed_subtask():
    return [
        {
            "id": "subtask_1",
            "goal": "检索资料并总结",
            "status": "completed",
            "result": "子任务工具摘要：这是中间工具摘要，不应直接显示。",
        }
    ]


def test_synthesize_caps_large_model_output_limit():
    llm_service = FakeLLMService(max_output_tokens=327680)
    synthesizer = AgentReportSynthesizer(llm_service=llm_service)

    result = synthesizer.synthesize(
        subtasks=_completed_subtasks(),
        agent_name="测试专家",
        agent_type="analysis",
        original_task="测试任务",
    )

    assert result == "# 合成报告"
    assert llm_service.call_args["max_tokens"] == 8192
    assert llm_service.call_args["max_attempts"] == 1
    assert llm_service.call_args["reject_truncated"] is True
    assert "完整性边界" in llm_service.call_args["message"]


def test_synthesize_preserves_lower_model_output_limit():
    llm_service = FakeLLMService(max_output_tokens=4096)
    synthesizer = AgentReportSynthesizer(llm_service=llm_service)

    synthesizer.synthesize(
        subtasks=_completed_subtasks(),
        agent_name="测试专家",
        agent_type="analysis",
        original_task="测试任务",
    )

    assert llm_service.call_args["max_tokens"] == 4096


def test_single_subtask_still_uses_report_synthesis():
    llm_service = FakeLLMService(max_output_tokens=4096)
    synthesizer = AgentReportSynthesizer(llm_service=llm_service)

    result = synthesizer.synthesize(
        subtasks=_single_completed_subtask(),
        agent_name="测试专家",
        agent_type="analysis",
        original_task="测试任务",
    )

    assert result == "# 合成报告"
    assert llm_service.call_args is not None
    assert "一句话摘要" in llm_service.call_args["message"]
    assert "不要写成建议、发现或风险清单" in llm_service.call_args["message"]
    assert "禁止开场白" in llm_service.call_args["message"]
    assert "第一行必须直接进入报告标题" in llm_service.call_args["message"]


def test_fallback_report_does_not_expose_subtask_result():
    synthesizer = AgentReportSynthesizer(llm_service=None)

    result = synthesizer.synthesize(
        subtasks=_single_completed_subtask(),
        agent_name="测试专家",
        agent_type="analysis",
        original_task="测试任务",
    )

    assert "子任务工具摘要" not in result
    assert "这是中间工具摘要" not in result
    assert "检索资料并总结" in result


def test_english_fallback_report_and_empty_result_are_localized():
    synthesizer = AgentReportSynthesizer(llm_service=None, locale="en-US")

    fallback = synthesizer.synthesize(
        subtasks=_single_completed_subtask(),
        agent_name="Researcher",
        agent_type="analysis",
        original_task="Compare options",
    )
    empty = synthesizer.synthesize(
        subtasks=[],
        agent_name="Researcher",
        agent_type="analysis",
        original_task="Compare options",
    )

    assert fallback.startswith("## Agent Report Generation Failed")
    assert "子任务工具摘要" not in fallback
    assert empty == "No execution results"


def test_locale_instruction_follows_role_and_date_in_system_prompt():
    llm_service = FakeLLMService(max_output_tokens=4096)
    synthesizer = AgentReportSynthesizer(llm_service=llm_service, locale="en-US")

    with patch("leader.node_utils.build_current_date_prompt", return_value="<DATE>"):
        synthesizer.synthesize(
            subtasks=_completed_subtasks(),
            agent_name="Researcher",
            agent_type="analysis",
            original_task="Compare options",
            agent_system_prompt="<ROLE>",
        )

    system_prompt = llm_service.call_args["system_prompt"]
    assert system_prompt.startswith("## Mandatory English report rule")
    assert system_prompt.index("<ROLE><DATE>") > system_prompt.index("## Mandatory English report rule")
    assert system_prompt.index("<DATE>") < system_prompt.index("## Output language")
    assert system_prompt.rstrip().endswith("necessary verbatim evidence quotes exactly as provided.")


def test_synthesize_includes_bounded_evidence_and_citation_contract():
    llm_service = FakeLLMService(max_output_tokens=4096)
    synthesizer = AgentReportSynthesizer(llm_service=llm_service)

    synthesizer.synthesize(
        subtasks=_completed_subtasks(),
        agent_name="测试专家",
        agent_type="analysis",
        original_task="测试任务",
        evidence_map=[
            {
                "evidence_id": "agent_ev_1",
                "title": "检索结果",
                "excerpt": "关键证据" * 400,
            }
        ],
    )

    prompt = llm_service.call_args["message"]
    assert "[evidence_id:agent_ev_1]" in prompt
    assert "对应句末" in prompt
    assert "不得杜撰" in prompt
    assert len(prompt) < 5000


def test_synthesize_uses_selected_passage_beyond_list_excerpt():
    llm_service = FakeLLMService(max_output_tokens=4096)
    synthesizer = AgentReportSynthesizer(llm_service=llm_service)
    passage = "A" * 350 + " critical limitation after excerpt"

    synthesizer.synthesize(
        subtasks=_completed_subtasks(),
        agent_name="测试专家",
        agent_type="analysis",
        original_task="测试任务",
        evidence_map=[{
            "evidence_id": "agent_ev_1",
            "title": "检索结果",
            "excerpt": "A" * 300,
            "raw_ref": "raw_tool_results.agent_ev_1",
        }],
        raw_tool_results={"agent_ev_1": {"passage": passage}},
    )

    prompt = llm_service.call_args["message"]
    assert "critical limitation after excerpt" in prompt
    assert "raw_tool_results" not in prompt
