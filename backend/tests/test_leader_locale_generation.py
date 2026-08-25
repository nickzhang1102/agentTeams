import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from leader.locale_generation import (
    build_output_locale_instruction,
    detect_content_locale,
    get_output_length_policy,
    resolve_generation_locale,
    resolve_agent_display_name,
)


def test_system_agent_display_name_is_localized_for_leader_events():
    assert resolve_agent_display_name(
        'oncology-expert', '肿瘤内科专家', 'en-US', True
    ) == 'Medical Oncology Specialist'
    assert resolve_agent_display_name(
        'oncology-expert', '肿瘤内科专家', 'zh-CN', True
    ) == '肿瘤内科专家'


@pytest.mark.asyncio
async def test_existing_leader_session_locale_is_loaded_into_workflow_state(monkeypatch):
    from db import db
    from leader import langgraph_entry

    session = SimpleNamespace(
        id=77,
        locale="en-US",
        state="monitoring",
        requirement_loop_count=2,
    )
    captured_state = {}
    restored_results = [{"agent_id": "agent-1", "content": "durable result"}]
    restored_agents = [{"agent_id": "agent-1", "agent_name": "Agent One"}]
    restored_dag = {"nodes": [{"agent_id": "agent-1"}], "edges": []}
    restored_qa = [{"question": "Scope?", "answer": "Patient A"}]

    class CapturingStreamer:
        def __init__(self, session_id):
            assert session_id == 77

        async def astream_graph_events(self, graph, initial_state):
            captured_state.update(initial_state)
            if False:
                yield None

    async def initialize_services(config, db_session):
        return None

    class StubDecisionRunService:
        def __init__(self, db_session):
            self.db_session = db_session

        def mark_started(self, session_id, *, stage):
            return None

    monkeypatch.setattr(db, "get", lambda model, session_id: session)
    monkeypatch.setattr(langgraph_entry, "_initialize_services", initialize_services)
    monkeypatch.setattr(langgraph_entry, "create_leader_workflow_graph", lambda: object())
    monkeypatch.setattr(langgraph_entry, "SSEStreamer", CapturingStreamer)
    monkeypatch.setattr(langgraph_entry, "DecisionRunService", StubDecisionRunService)
    monkeypatch.setattr(langgraph_entry, "load_agent_results", lambda db_session, session_id: restored_results)
    monkeypatch.setattr(
        langgraph_entry,
        "load_team_config",
        lambda db_session, session_id: {
            "selected_agents": restored_agents,
            "dag_plan": restored_dag,
        },
    )
    monkeypatch.setattr(langgraph_entry, "load_qa_history", lambda db_session, session_id: restored_qa)
    monkeypatch.setattr(langgraph_entry, "is_session_stop_requested", lambda *args, **kwargs: False)
    monkeypatch.setattr(langgraph_entry, "ensure_terminal_state_sync", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        langgraph_entry,
        "create_leader_session",
        lambda *args, **kwargs: pytest.fail("existing session must be reused"),
    )

    events = [
        event
        async for event in langgraph_entry.async_run_leader_workflow(
            conversation_id=9,
            message="task",
            history=[],
            config={},
            existing_session_id=77,
            locale="zh-CN",
        )
    ]

    assert captured_state["locale"] == "en-US"
    assert captured_state["skip_to_execution"] is True
    assert captured_state["agent_results"] == restored_results
    assert captured_state["selected_agents"] == restored_agents
    assert captured_state["dag_execution_plan"] == restored_dag
    assert captured_state["qa_history"] == restored_qa
    assert captured_state["all_asked_questions"] == [{"question": "Scope?", "options": []}]
    assert captured_state["requirement_loop_count"] == 2
    assert events == [{
        "type": "done",
        "session_id": 77,
        "message_key": "leader.status.done",
        "message_params": {},
        "message": "Workflow completed",
    }]


@pytest.mark.asyncio
async def test_existing_completed_session_reconciles_without_restarting_graph(
    monkeypatch,
):
    from db import db
    from leader import langgraph_entry

    session = SimpleNamespace(
        id=78,
        locale="en-US",
        state="completed",
        error_message=None,
    )

    class StubDecisionRunService:
        def __init__(self, db_session):
            self.db_session = db_session

    monkeypatch.setattr(db, "get", lambda model, session_id: session)
    monkeypatch.setattr(langgraph_entry, "DecisionRunService", StubDecisionRunService)
    monkeypatch.setattr(
        langgraph_entry,
        "create_leader_workflow_graph",
        lambda: pytest.fail("completed session must not restart the graph"),
    )

    events = [
        event
        async for event in langgraph_entry.async_run_leader_workflow(
            conversation_id=9,
            message="task",
            history=[],
            config={},
            existing_session_id=78,
        )
    ]

    assert events == [{
        "type": "done",
        "session_id": 78,
        "message_key": "leader.status.done",
        "message_params": {},
        "message": "Workflow completed",
    }]


def test_generation_locale_uses_full_precedence_order():
    assert resolve_generation_locale(
        explicit_locale="en-US",
        session_locale="zh-CN",
        conversation_locale="zh-CN",
        preferred_locale="zh-CN",
        accept_language="zh-CN",
    ) == "en-US"
    assert resolve_generation_locale(
        session_locale="en-US",
        conversation_locale="zh-CN",
        preferred_locale="zh-CN",
        accept_language="zh-CN",
    ) == "en-US"
    assert resolve_generation_locale(
        conversation_locale="en-US",
        preferred_locale="zh-CN",
        accept_language="zh-CN",
    ) == "en-US"
    assert resolve_generation_locale(
        preferred_locale="en-US",
        accept_language="zh-CN",
    ) == "en-US"
    assert resolve_generation_locale(accept_language="en-GB,en;q=0.9") == "en-US"
    assert resolve_generation_locale(accept_language="fr-FR") == "zh-CN"


@pytest.mark.parametrize("locale", ["", "EN-us", "fr-FR"])
def test_generation_locale_rejects_non_canonical_explicit_value(locale):
    with pytest.raises(ValueError, match="UNSUPPORTED_LOCALE"):
        resolve_generation_locale(explicit_locale=locale)


@pytest.mark.parametrize(
    ("locale", "content_kind", "expected_text"),
    [
        ("zh-CN", "assessment", "所有用户可见文本必须使用简体中文"),
        ("zh-CN", "question", "追问及选项"),
        ("en-US", "agent_report", "Write every user-visible value"),
        ("en-US", "final_report", "final synthesis report"),
    ],
)
def test_output_locale_instruction_covers_content_kinds(locale, content_kind, expected_text):
    instruction = build_output_locale_instruction(locale, content_kind)

    assert expected_text in instruction
    assert "Pydantic/JSON" in instruction
    assert "evidence ID" in instruction or "证据 ID" in instruction
    assert "highest priority" in instruction or "最高优先级" in instruction


def test_output_length_policy_counts_locale_specific_units():
    zh_policy = get_output_length_policy("zh-CN")
    en_policy = get_output_length_policy("en-US")

    assert zh_policy.unit == "effective_chars"
    assert zh_policy.count_units("中文 报告\n正文") == 6
    assert en_policy.unit == "effective_words"
    assert en_policy.count_units("A concise decision-making report.") == 4
    assert en_policy.target_units(agent_count=3, evidence_count=2, input_size=3200) > en_policy.minimum_units
    assert en_policy.output_token_budget(1000) == 2524


def test_content_locale_detection_only_changes_for_clear_opposite_language():
    chinese = "这是一个完整的中文分析报告，包含结论、建议、风险边界和下一步行动计划。"
    english = (
        "This is a complete English analysis report with conclusions, recommendations, "
        "risk boundaries, and a practical action plan."
    )
    mixed = "建议保留现有接口、证据编号和报告结构，同时 keep the API contract and evidence IDs stable。"

    assert detect_content_locale(chinese, "en-US") == "zh-CN"
    assert detect_content_locale(english, "zh-CN") == "en-US"
    assert detect_content_locale(mixed, "zh-CN") == "zh-CN"
    assert detect_content_locale("Short text", "zh-CN") == "zh-CN"


def test_content_locale_detection_ignores_code_urls_and_evidence_ids():
    text = """这是中文结论和建议，正文信息足够明确，应当保持中文判断。
```python
def english_identifier():
    return "machine contract"
```
https://example.com/english/path [evidence_id:ENGLISH_REFERENCE]
"""

    assert detect_content_locale(text, "zh-CN") == "zh-CN"


def test_english_assessment_fallback_localizes_visible_text_only():
    from leader.requirement_assessor import simple_assessment_fallback

    result = simple_assessment_fallback("Need help", "en-US")

    assert result["details"]["analysis"] == "The request is too brief for a reliable assessment."
    assert result["questions"][0]["question"].startswith("Please add the goal")
    assert result["questions"][0]["options"] == [
        "Provide details",
        "Give a brief summary",
        "Skip for now",
    ]
    assert result["scene"] == "general"
    assert result["category"] == "other"
    assert result["risk_level"] == "low"


def test_english_assessor_prompts_enforce_visible_field_language_at_each_level():
    from leader.requirement_assessor import RequirementAssessor
    from schemas.leader import AssessmentResult

    llm_service = MagicMock()
    llm_service.call_structured = AsyncMock(return_value=AssessmentResult.model_validate({
        "scene": "general",
        "scores": {},
        "total_score": 30,
        "analysis": "More information is required before the team can proceed.",
        "passed": False,
        "risk_level": "low",
        "risk_reason": "The impact is limited and reversible.",
        "category": "other",
        "questions": [{
            "question": "What outcome do you need?",
            "options": ["A decision", "A plan", "A comparison"],
        }],
    }))

    result = RequirementAssessor(llm_service, locale="en-US").assess_requirement("Help", [])

    messages = llm_service.call_structured.await_args.kwargs["messages"]
    system_prompt = messages[0]["content"]
    user_prompt = messages[1]["content"]
    assert system_prompt.startswith("You are a professional requirements analyst.")
    assert "需求分析师" not in system_prompt
    assert "this assessment in English" in system_prompt
    assert "follow-up questions and options in English" in system_prompt
    assert user_prompt.startswith("## Mandatory English output rule")
    assert user_prompt.rstrip().endswith("specified machine enum values.")
    assert user_prompt.count("## Mandatory English output rule") == 2
    assert "The only Chinese text allowed" in user_prompt
    assert "exact `scores` object key" in user_prompt
    assert "`analysis`, `risk_reason`, `category_reason`" in user_prompt
    assert "every `questions[].question`" in user_prompt
    assert "`questions[].options[]` must be English" in user_prompt
    assert result["questions"][0]["options"] == ["A decision", "A plan", "A comparison"]
    assert RequirementAssessor(llm_service, locale="en-US")._normalize_questions(["More context?"])[0]["options"] == [
        "Provide details",
        "Give a brief summary",
        "Skip for now",
    ]
    assert result["scene"] == "general"
    assert result["risk_level"] == "low"


def test_english_requirement_node_emits_one_canonical_assessment_and_persists_locale():
    from leader import requirement_nodes

    assessment = {
        "score": 72,
        "details": {
            "scene": "technology",
            "analysis": "The request provides a clear goal but needs one implementation constraint.",
            "risk_reason": "The change is reversible and has a limited operational impact.",
            "scores": {"目标明确性": 30},
        },
        "passed": True,
        "questions": [],
        "risk_level": "medium",
        "category": "technology",
        "scene": "technology",
    }
    db_session = MagicMock()
    db_session.get.return_value = None
    services = SimpleNamespace(llm_service=MagicMock(), max_tokens_limit=4096, db_session=db_session)

    with patch.object(requirement_nodes, "get_services", return_value=services), \
         patch("leader.requirement_assessor.RequirementAssessor.assess_requirement", return_value=assessment), \
         patch.object(requirement_nodes, "_save_leader_message", return_value=True) as save_message, \
         patch.object(requirement_nodes, "_emit"):
        result = requirement_nodes.requirement_loop_node({
            "conversation_id": 1,
            "session_id": 9,
            "locale": "en-US",
            "user_message": "Design an authentication service.",
            "history": [],
            "requirement_loop_count": 0,
            "sse_events": [],
        })

    assessment_events = [event for event in result["sse_events"] if event["type"] == "assessment_result"]
    assert len(assessment_events) == 1
    assert all(event["type"] != "leader_thinking" for event in result["sse_events"])
    assert assessment_events[0]["content_locale"] == "en-US"
    assert assessment_events[0]["details"]["analysis"].startswith("The request provides")
    assert result["assessment_result"]["scene"] == "technology"
    assert result["assessment_result"]["risk_level"] == "medium"
    assert save_message.call_args.kwargs["content_locale"] == "en-US"


def test_english_question_node_persists_detected_locale():
    from leader import requirement_nodes

    db_session = MagicMock()
    db_session.get.return_value = None
    services = SimpleNamespace(db_session=db_session)
    questions = [{
        "question": "Which deployment target should the plan use?",
        "options": ["Existing cluster", "New cluster", "Not decided"],
    }]

    with patch.object(requirement_nodes, "get_services", return_value=services), \
         patch.object(requirement_nodes, "_save_leader_message", return_value=True) as save_message, \
         patch.object(requirement_nodes, "_emit"):
        result = requirement_nodes.human_input_node({
            "conversation_id": 1,
            "session_id": 9,
            "locale": "en-US",
            "requirement_loop_count": 0,
            "requirement_questions": questions,
            "sse_events": [],
        })

    question_event, waiting_event = result["sse_events"]
    assert question_event["content_locale"] == "en-US"
    assert waiting_event["content"] == "Waiting for your answers..."
    assert waiting_event["message_key"] == "leader.phase.waiting_answers"
    assert waiting_event["message_params"] == {}
    assert waiting_event["message"] == waiting_event["content"]
    assert save_message.call_args.kwargs["content_locale"] == "en-US"


def test_english_execution_stop_event_keeps_reason_and_adds_message_contract():
    from leader import execution_nodes

    with patch.object(
        execution_nodes,
        "get_services",
        return_value=SimpleNamespace(db_session=None),
    ), \
         patch.object(execution_nodes, "_mark_session_stopped"):
        result = execution_nodes.agent_execution_node({
            "session_id": 9,
            "locale": "en-US",
            "stop_requested": True,
            "sse_events": [],
        })

    event = result["sse_events"][0]
    assert event["reason"] == "Execution stopped at the user's request"
    assert event["message"] == event["reason"]
    assert event["message_key"] == "leader.execution.stopped"
    assert event["message_params"] == {}
