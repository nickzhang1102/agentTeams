"""
summarize_node 单元测试

覆盖场景：
1. 正常汇总（多 Agent 成功结果）
2. 空 Agent 结果
3. 全失败 Agent
4. 包含逆向思考顾问
5. SSE 事件格式
6. DB 持久化
"""

import pytest
from unittest.mock import Mock, MagicMock, AsyncMock, patch
from datetime import datetime, timedelta, timezone

from leader.node_services import NodeServices, set_services
from leader.workflow_nodes import (
    summarize_node,
    initialize_summarize_services,
    _build_summary_prompt,
    _build_agent_summary_input,
    _fallback_summary,
    _persist_final_report
)
from leader.workflow_state import LeaderWorkflowState
from leader.locale_generation import detect_content_locale, get_output_length_policy
from leader.summarize_nodes import (
    _adaptive_final_report_target_units,
    _final_report_quality_issues,
    _get_final_report_max_tokens,
    _fit_target_units_to_output_budget,
)


def _long_final_report(title: str = "综合建议") -> str:
    """构造通过最终报告质量 guard 的测试正文。"""
    section_repeats = 24
    section = (
        "本节整合专家输入，给出判断依据、取舍理由、执行细节和风险边界。"
        "报告不能停留在摘要层面，需要说明为什么这样建议、依赖哪些发现、"
        "落地时应先做什么、哪些条件变化会影响结论。"
    )
    return (
        f"## {title}\n\n"
        + section * section_repeats
        + "\n\n## 各专家关键发现\n\n"
        + section * section_repeats
        + "\n\n## 实施路径\n\n"
        + section * section_repeats
        + "\n\n## 风险提示\n\n"
        + section * section_repeats
    )


def _long_english_final_report() -> str:
    paragraph = (
        "This section integrates the expert findings, explains the decision criteria, and identifies practical "
        "actions, dependencies, tradeoffs, evidence limits, and risk boundaries for implementation. "
    )
    return "\n\n".join(
        f"## {heading}\n\n{paragraph * 18}"
        for heading in ("Recommendation", "Key Findings", "Implementation", "Risks")
    )


def _inject_services(**overrides) -> NodeServices:
    """创建 NodeServices 并注入 ContextVar（测试辅助）"""
    svc = NodeServices(**overrides)
    set_services(svc)
    return svc


def _make_mock_llm(markdown_report: str = None) -> Mock:
    """创建适配 call_structured (async) 的 Mock LLM 服务"""
    from schemas.leader import FinalReportResult

    markdown_report = markdown_report or _long_final_report()
    mock_llm = Mock()
    mock_llm.get_max_output_tokens.return_value = 327680
    mock_structured_result = FinalReportResult(
        title="综合建议",
        executive_summary="摘要",
        key_findings=["发现"],
        recommendations=["建议"],
        risks=["风险"],
        next_steps=["下一步"],
        markdown_report=markdown_report,
    )
    mock_llm.call_structured = AsyncMock(return_value=mock_structured_result)
    return mock_llm


class TestSummarizeNode:
    """summarize_node 测试类"""

    def test_normal_summarize(self):
        """场景 1：正常汇总（多 Agent 成功结果）"""
        state = LeaderWorkflowState(
            conversation_id=1,
            session_id=100,
            user_message="设计一个 API 网关",
            history=[],
            requirement_loop_count=0,
            requirement_passed=True,
            requirement_questions=[],
            user_answers=[],
            assessment_result={"score": 85, "risk_level": "medium"},
            selected_agents=[],
            dag_execution_plan={},
            agent_results=[
                {
                    "agent_id": "cto-vogels",
                    "agent_name": "CTO专家",
                    "content": "建议使用 Kong 作为 API 网关...",
                    "success": True
                },
                {
                    "agent_id": "全栈技术主管",
                    "agent_name": "全栈技术主管",
                    "content": "需要考虑认证和限流...",
                    "success": True
                }
            ],
            current_agent_index=0,
            agent_retry_counts={},
            final_report="",
            stop_requested=False,
            current_phase="execution_complete",
            sse_events=[]
        )

        # Mock LLM 服务
        mock_llm = _make_mock_llm(_long_final_report("综合建议"))

        _inject_services(llm_service=mock_llm)
        result = summarize_node(state)

        # 验证返回结构
        assert "final_report" in result
        assert result["final_report"].startswith("## 综合建议")
        assert result["current_phase"] == "summarize_complete"

        # 验证 SSE 事件
        assert len(result["sse_events"]) >= 2
        assert result["sse_events"][0]["type"] == "leader_summarizing"
        assert result["sse_events"][0]["message_key"] == "leader.phase.summarizing"
        assert result["sse_events"][0]["message"] == result["sse_events"][0]["content"]
        assert result["sse_events"][-1]["type"] == "final_report"

    def test_empty_agent_results(self):
        """场景 2：空 Agent 结果"""
        state = LeaderWorkflowState(
            conversation_id=1,
            session_id=100,
            user_message="测试问题",
            history=[],
            requirement_loop_count=0,
            requirement_passed=True,
            requirement_questions=[],
            user_answers=[],
            assessment_result={},
            selected_agents=[],
            dag_execution_plan={},
            agent_results=[],  # 空
            current_agent_index=0,
            agent_retry_counts={},
            final_report="",
            stop_requested=False,
            current_phase="execution_complete",
            sse_events=[]
        )

        _inject_services(llm_service=None)
        result = summarize_node(state)

        # 验证返回空报告提示
        assert "没有收到任何专家" in result["final_report"]
        assert result["current_phase"] == "summarize_complete"

        # 验证 SSE 事件
        assert result["sse_events"][-1]["type"] == "final_report"

    def test_all_failed_agents(self):
        """场景 3：全失败 Agent"""
        state = LeaderWorkflowState(
            conversation_id=1,
            session_id=100,
            user_message="测试问题",
            history=[],
            requirement_loop_count=0,
            requirement_passed=True,
            requirement_questions=[],
            user_answers=[],
            assessment_result={},
            selected_agents=[],
            dag_execution_plan={},
            agent_results=[
                {"agent_id": "agent-1", "agent_name": "专家1", "content": "", "success": False},
                {"agent_id": "agent-2", "agent_name": "专家2", "content": "", "success": False}
            ],
            current_agent_index=0,
            agent_retry_counts={},
            final_report="",
            stop_requested=False,
            current_phase="execution_complete",
            sse_events=[]
        )

        _inject_services(llm_service=None)
        result = summarize_node(state)

        # 验证返回失败提示
        assert "都失败了" in result["final_report"]
        assert result["current_phase"] == "summarize_complete"

    @pytest.mark.parametrize(
        ("agent_results", "llm_service"),
        [
            ([], None),
            ([{"agent_id": "a1", "agent_name": "专家1", "content": "", "success": False}], None),
            ([{"agent_id": "a1", "agent_name": "专家1", "content": "结论", "success": True}], _make_mock_llm()),
        ],
    )
    def test_persistence_failure_never_emits_final_report(self, agent_results, llm_service):
        state = LeaderWorkflowState(
            conversation_id=1,
            session_id=100,
            user_message="测试问题",
            history=[],
            requirement_loop_count=0,
            requirement_passed=True,
            requirement_questions=[],
            user_answers=[],
            assessment_result={},
            selected_agents=[],
            dag_execution_plan={},
            agent_results=agent_results,
            current_agent_index=0,
            agent_retry_counts={},
            final_report="",
            stop_requested=False,
            current_phase="execution_complete",
            sse_events=[],
        )
        _inject_services(db_session=MagicMock(), llm_service=llm_service)

        with patch("leader.summarize_nodes._persist_final_report", side_effect=RuntimeError("commit failed")), \
             patch("leader.summarize_nodes._emit") as emit:
            with pytest.raises(RuntimeError, match="commit failed"):
                summarize_node(state)

        assert not any(
            call.args[1].get("type") == "final_report"
            for call in emit.call_args_list
        )

    def test_with_critic_agent(self):
        """场景 4：包含逆向思考顾问"""
        state = LeaderWorkflowState(
            conversation_id=1,
            session_id=100,
            user_message="设计方案",
            history=[],
            requirement_loop_count=0,
            requirement_passed=True,
            requirement_questions=[],
            user_answers=[],
            assessment_result={},
            selected_agents=[],
            dag_execution_plan={},
            agent_results=[
                {
                    "agent_id": "cto-vogels",
                    "agent_name": "CTO专家",
                    "content": "建议方案 A...",
                    "success": True
                },
                {
                    "agent_id": "critic-munger",
                    "agent_name": "逆向思考顾问",
                    "content": "方案 A 存在风险...",
                    "success": True
                }
            ],
            current_agent_index=0,
            agent_retry_counts={},
            final_report="",
            stop_requested=False,
            current_phase="execution_complete",
            sse_events=[]
        )

        # Mock LLM 服务
        mock_llm = _make_mock_llm(_long_final_report("综合建议"))

        _inject_services(llm_service=mock_llm)
        result = summarize_node(state)

        # 验证 call_structured 被调用
        assert mock_llm.call_structured.called

        # 验证 SSE 事件
        assert result["sse_events"][-1]["type"] == "final_report"

    def test_sse_event_format(self):
        """场景 5：SSE 事件格式验证"""
        state = LeaderWorkflowState(
            conversation_id=1,
            session_id=123,
            user_message="测试",
            history=[],
            requirement_loop_count=0,
            requirement_passed=True,
            requirement_questions=[],
            user_answers=[],
            assessment_result={},
            selected_agents=[],
            dag_execution_plan={},
            agent_results=[
                {"agent_id": "a1", "agent_name": "专家", "content": "内容", "success": True}
            ],
            current_agent_index=0,
            agent_retry_counts={},
            final_report="",
            stop_requested=False,
            current_phase="execution_complete",
            sse_events=[]
        )

        mock_llm = _make_mock_llm()

        _inject_services(llm_service=mock_llm)
        result = summarize_node(state)

        # 验证 leader_summarizing 事件格式
        summarizing_event = result["sse_events"][0]
        assert summarizing_event["type"] == "leader_summarizing"
        assert summarizing_event["session_id"] == 123
        assert "content" in summarizing_event

        # 验证 final_report 事件格式
        final_event = result["sse_events"][-1]
        assert final_event["type"] == "final_report"
        assert final_event["session_id"] == 123
        assert "report" in final_event
        assert final_event["summary"]["executive_summary"] == "摘要"
        assert final_event["structured_report"]["markdown_report"].startswith("## 综合建议")
        assert "total_time" in final_event
        assert isinstance(final_event["total_time"], (int, float))

    def test_final_report_total_time_uses_session_duration(self):
        """实时 final_report 事件的 total_time 应使用整个 session 耗时。"""
        state = LeaderWorkflowState(
            conversation_id=1,
            session_id=123,
            user_message="测试",
            history=[],
            requirement_loop_count=0,
            requirement_passed=True,
            requirement_questions=[],
            user_answers=[],
            assessment_result={},
            selected_agents=[],
            dag_execution_plan={},
            agent_results=[
                {"agent_id": "a1", "agent_name": "专家", "content": "内容", "success": True}
            ],
            current_agent_index=0,
            agent_retry_counts={},
            final_report="",
            stop_requested=False,
            current_phase="execution_complete",
            sse_events=[],
        )

        started_at = datetime.utcnow() - timedelta(seconds=125)
        session_record = Mock(conversation_id=1, started_at=started_at, state="summarizing")
        mock_db = MagicMock()
        mock_db.get.return_value = session_record
        # 报告查询与 DecisionRun 行锁链均解析为 None，使状态收敛成为无操作
        mock_db.query.return_value.filter_by.return_value.first.return_value = None
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = None

        _inject_services(llm_service=_make_mock_llm(), db_session=mock_db)
        result = summarize_node(state)

        final_event = result["sse_events"][-1]
        assert final_event["type"] == "final_report"
        assert final_event["total_time"] >= 120

    def test_final_report_collects_agent_evidence(self):
        """最终报告事件只聚合正文实际引用的 Agent evidence_map。"""
        state = LeaderWorkflowState(
            conversation_id=1,
            session_id=123,
            user_message="测试",
            history=[],
            requirement_loop_count=0,
            requirement_passed=True,
            requirement_questions=[],
            user_answers=[],
            assessment_result={},
            selected_agents=[],
            dag_execution_plan={},
            agent_results=[
                {
                    "agent_id": "a1",
                    "agent_name": "专家",
                    "content": "内容",
                    "success": True,
                    "evidence_map": [
                        {"evidence_id": "ev_1", "title": "证据1", "excerpt": "证据摘录"}
                    ],
                }
            ],
            current_agent_index=0,
            agent_retry_counts={},
            final_report="",
            stop_requested=False,
            current_phase="execution_complete",
            sse_events=[],
        )

        report = _long_final_report() + "\n\n结论依据 [evidence_id:ev_1]"
        _inject_services(llm_service=_make_mock_llm(report))
        result = summarize_node(state)

        assert result["sse_events"][-1]["evidence_map"] == [
            {"evidence_id": "ev_1", "title": "证据1", "excerpt": "证据摘录"}
        ]

    def test_final_report_filters_unknown_refs_and_exposes_degraded_state(self):
        from schemas.leader import (
            ClaimEvidenceReference,
            FinalReportResult,
            ReportClaim,
        )

        mock_llm = MagicMock()
        mock_llm.get_max_output_tokens.return_value = 327680
        mock_llm.call_structured = AsyncMock(return_value=FinalReportResult(
            title="综合建议",
            executive_summary="摘要",
            key_findings=["发现"],
            recommendations=["建议"],
            evidence_refs=["ev_valid", "ev_unknown"],
            claims=[ReportClaim(
                text="仅由结构化 claim 引用的发现",
                claim_type="fact",
                evidence_relations=[
                    ClaimEvidenceReference(evidence_id="ev_claim_only"),
                    ClaimEvidenceReference(evidence_id="ev_unknown"),
                ],
            )],
            markdown_report="## 综合建议\n\n结论 [evidence_id:ev_valid]",
        ))
        _inject_services(llm_service=mock_llm)

        result = summarize_node({
            "session_id": 123,
            "user_message": "测试",
            "agent_results": [{
                "agent_id": "a1",
                "agent_name": "专家",
                "content": "内容",
                "success": True,
                "quality_status": "degraded",
                "degradation_reason": "任务分解服务不可用",
                "evidence_map": [
                    {"evidence_id": "ev_valid", "title": "有效", "excerpt": "有效摘录"},
                    {"evidence_id": "ev_claim_only", "title": "Claim", "excerpt": "Claim 摘录"},
                ],
            }],
            "sse_events": [],
        })

        final_event = result["sse_events"][-1]
        assert final_event["quality_status"] == "degraded"
        assert final_event["degradation_reasons"] == ["任务分解服务不可用"]
        assert final_event["structured_report"]["evidence_refs"] == ["ev_valid"]
        assert final_event["structured_report"]["claims"][0]["claim_id"] == "final_claim_1"
        assert final_event["structured_report"]["claims"][0]["evidence_relations"] == [
            {"evidence_id": "ev_claim_only", "relation": "supports"},
            {"evidence_id": "ev_unknown", "relation": "supports"},
        ]
        assert final_event["structured_report"]["source_quality_status"] == "degraded"
        assert final_event["structured_report"]["source_degradation_reasons"] == ["任务分解服务不可用"]
        assert [item["evidence_id"] for item in final_event["evidence_map"]] == [
            "ev_valid",
            "ev_claim_only",
        ]

    def test_persisted_invalid_claim_degrades_final_event(self, db_session):
        from leader.leader_persistence import create_leader_session
        from models import Conversation, DecisionRun, User
        from schemas.leader import (
            ClaimEvidenceReference,
            FinalReportResult,
            ReportClaim,
        )

        user = User(username="claim-event-owner", password_hash="test-hash")
        db_session.add(user)
        db_session.flush()
        conversation = Conversation(title="Claim event", user_id=user.id)
        db_session.add(conversation)
        db_session.flush()
        leader_session = create_leader_session(
            db_session,
            conversation.id,
            "Analyze without evidence",
            auto_commit=False,
        )
        db_session.commit()

        mock_llm = MagicMock()
        mock_llm.get_max_output_tokens.return_value = 327680
        mock_llm.call_structured = AsyncMock(return_value=FinalReportResult(
            title="综合建议",
            executive_summary="摘要",
            key_findings=["发现"],
            recommendations=["建议"],
            claims=[ReportClaim(
                text="没有真实证据支持的事实",
                claim_type="fact",
                evidence_relations=[
                    ClaimEvidenceReference(evidence_id="ev_fabricated")
                ],
            )],
            markdown_report=_long_final_report(),
        ))
        _inject_services(llm_service=mock_llm, db_session=db_session)

        result = summarize_node({
            "conversation_id": conversation.id,
            "session_id": leader_session.id,
            "user_message": "Analyze without evidence",
            "agent_results": [{
                "agent_id": "a1",
                "agent_name": "专家",
                "content": "无证据分析",
                "success": True,
                "evidence_map": [],
            }],
            "sse_events": [],
        })

        final_event = result["sse_events"][-1]
        run = db_session.query(DecisionRun).one()

        assert final_event["quality_status"] == "degraded"
        assert set(final_event["degradation_reasons"]) == {
            "invalid_evidence_reference",
            "unsupported_fact_claim",
        }
        assert final_event["structured_report"]["claims"][0]["support_status"] == "unsupported"
        assert run.quality_status == "degraded"

    def test_short_structured_report_is_preserved_with_quality_warning(self):
        """结构化 markdown_report 过短时保留正文并暴露质量告警。"""
        state = LeaderWorkflowState(
            conversation_id=1,
            session_id=123,
            user_message="测试",
            history=[],
            requirement_loop_count=0,
            requirement_passed=True,
            requirement_questions=[],
            user_answers=[],
            assessment_result={},
            selected_agents=[],
            dag_execution_plan={},
            agent_results=[
                {"agent_id": "a1", "agent_name": "专家", "content": "内容", "success": True}
            ],
            current_agent_index=0,
            agent_retry_counts={},
            final_report="",
            stop_requested=False,
            current_phase="execution_complete",
            sse_events=[],
        )

        mock_llm = _make_mock_llm("## 综合建议\n\n太短")
        _inject_services(llm_service=mock_llm)
        result = summarize_node(state)

        assert result["final_report"] == "## 综合建议\n\n太短"
        assert not mock_llm.call_sync.called
        final_event = result["sse_events"][-1]
        assert final_event["structured_report"]["quality_status"] == "warning"
        assert final_event["structured_report"]["quality_warnings"]

    def test_english_summary_uses_word_policy_and_emits_content_locale(self):
        from schemas.leader import FinalReportResult

        report = _long_english_final_report()
        mock_llm = MagicMock()
        mock_llm.get_max_output_tokens.return_value = 327680
        mock_llm.call_structured = AsyncMock(return_value=FinalReportResult(
            title="Decision Report",
            executive_summary="The recommended path balances delivery speed with operational risk.",
            key_findings=["The current architecture supports an incremental rollout."],
            recommendations=["Begin with a measured pilot and explicit success criteria."],
            risks=["Integration constraints may delay the second phase."],
            next_steps=["Confirm ownership and launch the pilot."],
            markdown_report=report,
        ))
        _inject_services(llm_service=mock_llm)

        with patch("leader.node_utils.build_current_date_prompt", return_value="<DATE>"):
            result = summarize_node({
                "session_id": 123,
                "locale": "en-US",
                "user_message": "Compare the available implementation options.",
                "agent_results": [{
                    "agent_id": "a1",
                    "agent_name": "Architect",
                    "content": "The incremental option has the lowest operational risk.",
                    "success": True,
                }],
                "sse_events": [],
            })

        call = mock_llm.call_structured.call_args.kwargs
        system_prompt = call["messages"][0]["content"]
        user_prompt = call["messages"][1]["content"]
        final_event = result["sse_events"][-1]
        assert "Target approximately" in user_prompt
        assert "effective words" in user_prompt
        assert system_prompt.index("<DATE>") < system_prompt.index("## Output language")
        assert system_prompt.endswith("Preserve user input, raw evidence, and tool results verbatim.")
        assert final_event["content_locale"] == "en-US"
        assert final_event["structured_report"]["quality_status"] == "normal"

    def test_opposite_language_final_report_warns_once_without_regeneration(self, caplog):
        from schemas.leader import FinalReportResult

        report = _long_final_report()
        mock_llm = MagicMock()
        mock_llm.get_max_output_tokens.return_value = 327680
        mock_llm.call_structured = AsyncMock(return_value=FinalReportResult(
            title="综合建议",
            executive_summary="建议采用分阶段实施方案。",
            key_findings=["现有架构支持渐进式上线。"],
            recommendations=["先完成小范围验证。"],
            markdown_report=report,
        ))
        _inject_services(llm_service=mock_llm)

        with caplog.at_level("WARNING", logger="leader.summarize_nodes"):
            result = summarize_node({
                "session_id": 123,
                "locale": "en-US",
                "user_message": "Compare the available implementation options.",
                "agent_results": [{
                    "agent_id": "a1",
                    "agent_name": "Architect",
                    "content": "English source report",
                    "success": True,
                }],
                "sse_events": [],
            })

        assert result["sse_events"][-1]["content_locale"] == "zh-CN"
        assert mock_llm.call_structured.await_count == 1
        mock_llm.call_sync.assert_not_called()
        mismatch_logs = [record for record in caplog.records if "locale mismatch" in record.message]
        assert len(mismatch_logs) == 1

    def test_final_report_locale_detection_includes_visual_text_only(self):
        from leader.summarize_nodes import _final_report_visible_text

        visible_text = _final_report_visible_text(
            "Short report",
            {"executive_summary": "Brief summary"},
            {
                "quality_status": "warning",
                "visual_blocks": [{
                    "block_id": "risk-main-machine-id",
                    "type": "risk_matrix",
                    "title": "主要风险矩阵",
                    "data": {
                        "risks": [{
                            "risk": "供应链中断风险需要准备替代方案",
                            "likelihood": "高概率",
                            "impact": "高影响",
                            "mitigation": (
                                "提前锁定第二供应商并准备切换预案，同时建立库存缓冲、运输替代路线、"
                                "每周风险复盘和明确的升级责任机制，确保供应中断时可以快速恢复交付"
                            ),
                            "source_id": "source-machine-id",
                        }],
                    },
                    "evidence_refs": ["ev_machine_reference"],
                }],
            },
        )

        assert "主要风险矩阵" in visible_text
        assert "供应链中断风险需要准备替代方案" in visible_text
        assert "risk-main-machine-id" not in visible_text
        assert "risk_matrix" not in visible_text
        assert "source-machine-id" not in visible_text
        assert "ev_machine_reference" not in visible_text
        assert detect_content_locale(visible_text, "en-US") == "zh-CN"


class TestBuildSummaryPrompt:
    """_build_summary_prompt 测试类"""

    def test_prompt_without_critic(self):
        """普通报告 prompt 结构"""
        other_results = [
            {"agent_id": "a1", "agent_name": "专家1", "content": "内容1"},
            {"agent_id": "a2", "agent_name": "专家2", "content": "内容2"}
        ]
        prompt = _build_summary_prompt(other_results, None, False)

        assert "专家分析结果" in prompt
        assert "结构化图表块要求" in prompt
        assert "risk_matrix" in prompt
        assert "decision_matrix" in prompt
        assert "专家1" in prompt
        assert "专家2" in prompt
        assert "逆向思考" not in prompt

    def test_english_prompt_uses_effective_word_target(self):
        policy = get_output_length_policy("en-US")
        prompt = _build_summary_prompt(
            [{"agent_id": "a1", "agent_name": "Expert", "content": "Analysis"}],
            None,
            False,
            target_units=750,
            length_policy=policy,
        )

        assert "Target approximately 750 effective words" in prompt
        assert "正文目标有效字符数" not in prompt

    def test_prompt_uses_direct_agent_summary_with_report(self):
        """有 result.summary 时，最终汇总 prompt 使用摘要与 Agent 报告正文。"""
        other_results = [
            {
                "agent_id": "a1",
                "agent_name": "专家1",
                "summary": {
                    "one_sentence": "建议先做摘要优先汇总。",
                    "key_findings": ["全文拼接会增加 token 成本"],
                    "recommendations": ["默认使用 Agent 摘要"],
                    "risks": ["摘要缺失时需要回退"],
                    "confidence": 0.8,
                    "evidence_refs": ["ev_1"],
                },
                "content": "不应该进入 prompt 的长 Markdown 正文",
            }
        ]

        prompt = _build_summary_prompt(other_results, None, False)

        assert "Agent 内部分析摘要" in prompt
        assert "建议先做摘要优先汇总" in prompt
        assert "Agent 综合报告正文" in prompt
        assert "不应该进入 prompt 的长 Markdown 正文" in prompt
        # 最终报告是独立综合分析，不消费证据/原始报告摘录
        assert "原始报告摘录" not in prompt
        assert "[evidence_id:ev_1]" not in prompt

    def test_prompt_requires_self_contained_problem_oriented_report(self):
        """最终报告必须像单一作者成稿，而不是按 Agent 来源拼装。"""
        prompt = _build_summary_prompt(
            [{"agent_id": "a1", "agent_name": "专家1", "content": "完整分析"}],
            None,
            False,
            user_message="请给出最终判断",
        )

        assert "可独立交付的最终分析报告" in prompt
        assert "读者即使没有看过任何 Agent 报告" in prompt
        assert "`**一句话总结：** ...`" in prompt
        assert "围绕用户的问题、决策或主题组织正文" in prompt
        assert "不要设置“各专家关键发现”" in prompt
        assert "主题化深度分析" in prompt
        assert "提炼每位专家最有价值" not in prompt
        assert "标注观点来源专家姓名" not in prompt

    def test_prompt_localizes_one_sentence_summary_opening(self):
        """英文最终报告不应被中文固定开头格式污染。"""
        prompt = _build_summary_prompt(
            [{"agent_id": "a1", "content": "analysis"}],
            None,
            False,
            length_policy=get_output_length_policy("en-US"),
        )

        assert "`**One-sentence summary:** ...`" in prompt
        assert "`**一句话总结：** ...`" not in prompt

    def test_prompt_uses_structured_report_summary_with_report(self):
        """没有 result.summary 时，可使用 structured_report.summary，并补充报告正文。"""
        other_results = [
            {
                "agent_id": "a1",
                "agent_name": "专家1",
                "structured_report": {
                    "summary": {
                        "one_sentence": "结构化报告摘要可用于最终汇总。",
                        "recommendations": ["读取 structured_report.summary"],
                    }
                },
                "content": "fallback markdown",
            }
        ]

        prompt = _build_summary_prompt(other_results, None, False)

        assert "结构化报告摘要可用于最终汇总" in prompt
        assert "读取 structured_report.summary" in prompt
        assert "Agent 综合报告正文" in prompt
        assert "fallback markdown" in prompt

    def test_prompt_truncates_long_agent_content(self):
        """最终汇总 prompt 不应无界携带完整专家报告"""
        other_results = [
            {"agent_id": "a1", "agent_name": "专家1", "content": "A" * 20000}
        ]

        prompt = _build_summary_prompt(other_results, None, False)

        assert len(prompt) < 10000
        assert "已截断至 6000 字符" in prompt

    def test_prompt_excludes_raw_tool_results(self):
        """最终汇总 prompt 不携带 raw_tool_results 原始内容与证据引用。"""
        other_results = [
            {
                "agent_id": "a1",
                "agent_name": "专家1",
                "summary": {
                    "one_sentence": "只引用证据 ID。",
                    "evidence_refs": ["ev_secret"],
                },
                "raw_tool_results": {
                    "ev_secret": {"raw": "RAW_SECRET_CONTENT_SHOULD_NOT_APPEAR"}
                },
            }
        ]

        prompt = _build_summary_prompt(other_results, None, False)

        assert "ev_secret" not in prompt
        assert "RAW_SECRET_CONTENT_SHOULD_NOT_APPEAR" not in prompt

    def test_prompt_notes_degraded_state_without_evidence(self):
        """最终汇总 prompt 记录降级状态，但不注入证据摘录。"""
        other_results = [{
            "agent_id": "a1",
            "agent_name": "专家1",
            "summary": {
                "one_sentence": "结论",
                "confidence": 0.9,
                "evidence_refs": ["ev_1"],
            },
            "quality_status": "degraded",
            "degradation_reason": "使用了 fallback 分解",
            "evidence_map": [{
                "evidence_id": "ev_1",
                "excerpt": "证据" * 1000,
            }],
        }]

        prompt = _build_summary_prompt(other_results, None, False)

        assert "[evidence_id:ev_1]" not in prompt
        assert "质量状态：降级" in prompt
        assert "使用了 fallback 分解" in prompt
        assert len(prompt) < 6000

    def test_prompt_truncates_agent_report_when_summary_exists(self):
        """摘要可用时，正文摘录也必须受限，避免最终汇总 prompt 失控。"""
        other_results = [
            {
                "agent_id": "a1",
                "agent_name": "专家1",
                "summary": {
                    "one_sentence": "摘要可用。",
                    "confidence": 0.9,
                },
                "content": "B" * 12000,
            }
        ]

        prompt = _build_summary_prompt(other_results, None, False)

        assert "Agent 综合报告正文" in prompt
        assert "已截断至 6000 字符" in prompt
        assert len(prompt) < 8000

    def test_prompt_with_critic(self):
        """包含逆向思考顾问的 prompt 结构"""
        other_results = [
            {"agent_id": "a1", "agent_name": "专家1", "content": "内容1"}
        ]
        critic_result = {
            "agent_id": "critic-munger",
            "agent_name": "逆向思考顾问",
            "content": "质疑内容"
        }
        prompt = _build_summary_prompt(other_results, critic_result, True)

        assert "逆向思考顾问意见" in prompt
        assert "逆向思考与风险分析" in prompt
        assert "质疑内容" in prompt

    def test_prompt_with_critic_uses_summary(self):
        """逆向思考顾问也提供内部摘要与综合报告正文。"""
        critic_result = {
            "agent_id": "critic-munger",
            "agent_name": "逆向思考顾问",
            "summary": {
                "one_sentence": "核心质疑来自摘要。",
                "risks": ["执行复杂度过高"],
            },
            "content": "不应该进入 critic prompt 的全文",
        }

        prompt = _build_summary_prompt([], critic_result, True)

        assert "逆向思考顾问意见" in prompt
        assert "核心质疑来自摘要" in prompt
        assert "执行复杂度过高" in prompt
        assert "Agent 综合报告正文" in prompt
        assert "不应该进入 critic prompt 的全文" in prompt

    def test_build_agent_summary_input_falls_back_for_empty_summary(self):
        """空摘要不算可用，仍回退 Markdown 裁剪。"""
        text = _build_agent_summary_input(
            {
                "summary": {"one_sentence": "", "key_findings": []},
                "content": "fallback content",
            }
        )

        assert text == "fallback content"

    def test_build_agent_summary_input_filters_none_items(self):
        """摘要列表中的 None 不应被写成字符串 'None'。"""
        text = _build_agent_summary_input(
            {
                "summary": {
                    "one_sentence": "结论",
                    "key_findings": [None, "有效发现"],
                    "recommendations": ["", None, "有效建议"],
                    "confidence": 0.8,
                }
            }
        )

        assert "None" not in text
        assert "有效发现" in text
        assert "有效建议" in text


class TestLocaleAwareFinalReportPolicy:
    def test_target_and_quality_units_follow_locale(self):
        zh_policy = get_output_length_policy("zh-CN")
        en_policy = get_output_length_policy("en-US")
        results = [{"content": "analysis", "evidence_map": []}]

        assert _adaptive_final_report_target_units(results, zh_policy) == 800
        assert _adaptive_final_report_target_units(results, en_policy) == 500

        zh_issues = _final_report_quality_issues(
            "## 结论\n" + "结论" * 100 + "\n## 建议\n内容\n## 风险\n内容",
            target_units=800,
            length_policy=zh_policy,
        )
        en_issues = _final_report_quality_issues(
            "## Conclusion\n" + "short report " * 50 + "\n## Actions\nDetails\n## Risks\nDetails",
            target_units=500,
            length_policy=en_policy,
        )

        assert any(issue.startswith("effective_chars=") for issue in zh_issues)
        assert any(issue.startswith("effective_words=") for issue in en_issues)

    def test_output_token_budget_is_locale_aware_and_capped(self):
        llm_service = MagicMock()
        llm_service.get_max_output_tokens.return_value = 327680

        zh_budget = _get_final_report_max_tokens(
            llm_service,
            target_units=3000,
            length_policy=get_output_length_policy("zh-CN"),
        )
        en_budget = _get_final_report_max_tokens(
            llm_service,
            target_units=3000,
            length_policy=get_output_length_policy("en-US"),
        )

        assert zh_budget == 4024
        assert en_budget == 5524
        assert en_budget <= 12288

    def test_target_units_fit_the_models_real_output_budget(self):
        llm_service = MagicMock()
        llm_service.get_max_output_tokens.return_value = 4096

        assert _fit_target_units_to_output_budget(
            5000,
            get_output_length_policy("zh-CN"),
            llm_service,
        ) == 3072
        assert _fit_target_units_to_output_budget(
            3000,
            get_output_length_policy("en-US"),
            llm_service,
        ) == 2048


class TestFallbackSummary:
    """_fallback_summary 测试类"""

    def test_fallback_basic(self):
        """降级汇总基本功能"""
        other_results = [
            {"agent_id": "a1", "agent_name": "专家1", "content": "这是一段很长的内容，应该被截断..."}
        ]
        report = _fallback_summary(other_results, None, False)

        assert "## 综合建议" in report
        assert "专家1" in report

    def test_fallback_with_critic(self):
        """降级汇总包含逆向思考"""
        other_results = [
            {"agent_id": "a1", "agent_name": "专家1", "content": "内容"}
        ]
        critic_result = {
            "agent_id": "critic",
            "agent_name": "逆向思考顾问",
            "content": "质疑"
        }
        report = _fallback_summary(other_results, critic_result, True)

        assert "逆向思考顾问" in report

    def test_english_fallback_is_localized(self):
        report = _fallback_summary(
            [{"agent_id": "a1", "agent_name": "Expert", "content": "English finding"}],
            None,
            False,
            locale="en-US",
        )

        assert report.startswith("## Final Recommendation")
        assert "A concise summary of the expert findings follows" in report
        assert "English finding" in report


class TestPersistFinalReport:
    """_persist_final_report 测试类"""

    def test_persist_new_report(self):
        """新增报告持久化"""
        # Mock 数据库会话
        mock_db = MagicMock()
        mock_session = Mock()
        mock_session.conversation_id = 1
        mock_db.get.return_value = mock_session

        # Mock 查询返回 None（不存在）：报告查询与 DecisionRun 行锁链均解析为 None，
        # 使 completion gate 不就绪、状态收敛成为无操作（与真实"无报告"行为一致）
        mock_query = MagicMock()
        mock_query.filter_by.return_value.first.return_value = None
        mock_query.filter.return_value.first.return_value = None
        mock_query.filter.return_value.with_for_update.return_value.first.return_value = None
        mock_db.query.return_value = mock_query

        report_record = _persist_final_report(
            db_session=mock_db,
            session_id=100,
            report="测试报告",
            content_locale="en-US",
            completed_at=datetime.now(timezone.utc),
            executive_summary={"executive_summary": "摘要"},
            structured_report={"markdown_report": "测试报告"},
        )

        # 验证 add 被调用
        assert mock_db.add.called
        # 验证返回新报告记录，供 SSE 携带 id
        assert report_record.report == "测试报告"
        assert report_record.content_locale == "en-US"
        assert report_record.executive_summary == {"executive_summary": "摘要"}
        assert report_record.structured_report == {"markdown_report": "测试报告"}
        # 验证 commit 被调用
        assert mock_db.commit.called

    def test_persist_update_report(self):
        """更新已有报告"""
        # Mock 数据库会话
        mock_db = MagicMock()
        mock_existing = Mock()
        mock_existing.report = "旧报告"

        mock_query = MagicMock()
        mock_query.filter_by.return_value.first.return_value = mock_existing
        mock_query.filter.return_value.first.return_value = None
        mock_query.filter.return_value.with_for_update.return_value.first.return_value = None
        mock_db.query.return_value = mock_query

        mock_session = Mock()
        mock_session.conversation_id = 1
        mock_session.state = "monitoring"
        mock_db.get.return_value = mock_session

        report_record = _persist_final_report(
            db_session=mock_db,
            session_id=100,
            report="新报告",
            content_locale="en-US",
            completed_at=datetime.now(timezone.utc),
            executive_summary={"executive_summary": "新摘要"},
            structured_report={"markdown_report": "新报告"},
        )

        # 验证报告被更新
        assert mock_existing.report == "新报告"
        assert mock_existing.content_locale == "en-US"
        assert mock_existing.executive_summary == {"executive_summary": "新摘要"}
        assert mock_existing.structured_report == {"markdown_report": "新报告"}
        # 验证返回已有报告记录
        assert report_record is mock_existing
        # 验证状态被更新
        assert mock_session.state == "completed"
        # 验证 commit 被调用
        assert mock_db.commit.called


class TestInitializeSummarizeServices:
    """服务初始化测试"""

    def test_initialize(self):
        """初始化服务注入"""
        mock_db = Mock()

        # 调用初始化函数
        initialize_summarize_services(mock_db)

        # 验证通过 get_services 可获取注入的 db_session
        from leader.node_services import get_services
        svc = get_services()
        assert svc.db_session == mock_db


# 运行测试
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
