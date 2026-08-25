"""
结构化输出集成测试

覆盖 Instructor + Pydantic 结构化输出的最小闭环。
"""
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel, ValidationError

from leader.requirement_assessor import RequirementAssessor
from leader.team_former import TeamFormer
from leader.workflow_nodes import initialize_node_services, initialize_summarize_services, summarize_node
from services.llm_service import LLMService


class DummyStructuredResult(BaseModel):
    message: str


def _long_final_report(title: str = "综合建议") -> str:
    return _final_report_with_repeats(title=title, section_repeats=24)


def _medium_final_report(title: str = "综合建议") -> str:
    return _final_report_with_repeats(title=title, section_repeats=11)


def _final_report_with_repeats(title: str = "综合建议", section_repeats: int = 24) -> str:
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


class TestLeaderStructuredSchemas:
    """测试 Leader 结构化输出模型契约"""

    def test_assessment_questions_use_object_list(self):
        """AssessmentResult.questions 使用对象列表"""
        from schemas.leader import AssessmentResult, QuestionOption

        result = AssessmentResult(
            score=72,
            passed=True,
            risk_level="medium",
            scene="technology",
            category="technology",
            questions=[QuestionOption(question="目标是什么？", options=["上线", "验证", "暂不确定"])],
        )

        assert result.questions[0].question == "目标是什么？"
        assert result.questions[0].options == ["上线", "验证", "暂不确定"]
        assert result.questions[0].selection_type == "single"

        multiple = QuestionOption(
            question="可接受哪些环境？",
            options=["开发", "测试", "生产"],
            selection_type="multiple",
        )
        assert multiple.selection_type == "multiple"

        assessor = RequirementAssessor(MagicMock(), locale="en-US")
        inferred = assessor._normalize_questions([{
            "question": "Select all that apply",
            "options": ["A", "B", "C"],
        }])
        assert inferred[0]["selection_type"] == "multiple"

        with pytest.raises(ValidationError):
            AssessmentResult(
                score=30,
                passed=False,
                risk_level="low",
                scene="general",
                category="other",
                questions=["请补充目标"],
            )

    def test_assessment_category_accepts_chinese_labels(self):
        """中文分类标签应归一化为首页可识别的英文 key。"""
        from schemas.leader import AssessmentResult

        result = AssessmentResult(
            score=72,
            passed=True,
            risk_level="medium",
            scene="medical",
            category="医疗",
            questions=[],
        )

        assert result.category == "medical"

    def test_team_selection_and_final_report_contracts(self):
        """团队选择和最终报告模型含设计要求字段"""
        from schemas.leader import AgentSelection, FinalReportResult, ReportVisualBlock, TeamSelectionResult

        team = TeamSelectionResult(
            agents=[
                AgentSelection(
                    agent_id="research-analyst",
                    agent_name="调研分析师",
                    role_description="负责调研",
                    reason="需求涉及市场分析",
                )
            ],
            reasoning="需要调研视角",
            team_strategy="先调研后汇总",
        )
        report = FinalReportResult(
            title="综合建议",
            executive_summary="结论摘要",
            key_findings=["发现一"],
            recommendations=["建议一"],
            visual_blocks=[
                ReportVisualBlock(
                    block_id="risk-main",
                    type="risk_matrix",
                    title="关键风险矩阵",
                    data={"risks": [{"risk": "预算超支", "likelihood": "medium", "impact": "high", "mitigation": "阶段预算"}]},
                )
            ],
            markdown_report=_long_final_report(),
        )

        assert team.agents[0].agent_id == "research-analyst"
        assert report.markdown_report.startswith("## 综合建议")
        assert "完整 Markdown 最终报告正文" in FinalReportResult.model_fields["markdown_report"].description
        assert report.structured_payload()["visual_blocks"][0]["type"] == "risk_matrix"

    def test_final_report_result_accepts_numbered_text_lists(self):
        """最终报告结构化列表字段兼容模型输出的编号字符串。"""
        from schemas.leader import FinalReportResult

        report = FinalReportResult.model_validate({
            "title": "综合建议",
            "executive_summary": "结论摘要",
            "key_findings": "1. 发现一\n2. 发现二",
            "recommendations": "1. 建议一 2. 建议二",
            "risks": "风险一",
            "next_steps": None,
            "markdown_report": _long_final_report(),
        })

        assert report.key_findings == ["发现一", "发现二"]
        assert report.recommendations == ["建议一", "建议二"]
        assert report.risks == ["风险一"]
        assert report.next_steps == []


    def test_prompt_compatible_aliases_validate_to_contract_fields(self):
        """结构化模型兼容旧 prompt 字段名，避免真实模型按提示输出时频繁 fallback"""
        from schemas.leader import AssessmentResult, TeamSelectionResult

        assessment = AssessmentResult.model_validate({
            "scene": "technology",
            "scores": {"目标明确性": 30},
            "total_score": 70,
            "analysis": "需求基本完整",
            "passed": True,
            "risk_level": "medium",
            "category": "technology",
            "questions": [],
        })
        team = TeamSelectionResult.model_validate({
            "analysis": "需要调研视角",
            "selected_agents": [
                {
                    "agent_id": "research-analyst",
                    "agent_name": "调研分析师",
                    "role_description": "负责调研",
                }
            ],
            "team_strategy": "先调研后汇总",
        })

        assert assessment.score == 70
        assert assessment.details == "需求基本完整"
        assert team.reasoning == "需要调研视角"
        assert team.agents[0].agent_id == "research-analyst"


class TestLLMServiceStructuredCall:
    """测试 LLMService.call_structured"""

    def test_call_structured_returns_pydantic_instance(self):
        """call_structured 返回 Pydantic 模型实例"""
        service = LLMService(api_key="test-key", base_url="http://test", model="ep-default")
        patched_client = MagicMock()
        patched_client.chat.completions.create.return_value = DummyStructuredResult(message="ok")

        with patch("services.llm_service.instructor.from_openai", return_value=patched_client):
            result = asyncio.run(
                service.call_structured(
                    messages=[{"role": "user", "content": "Say ok"}],
                    response_model=DummyStructuredResult,
                    max_retries=2,
                    temperature=0.0,
                    timeout=120.0,
                )
            )

        assert isinstance(result, DummyStructuredResult)
        assert result.message == "ok"
        patched_client.chat.completions.create.assert_called_once()
        kwargs = patched_client.chat.completions.create.call_args.kwargs
        assert kwargs["response_model"] is DummyStructuredResult
        assert kwargs["max_retries"] == 2
        assert kwargs["model"] == "ep-default"
        assert kwargs["temperature"] == 0.0
        assert kwargs["timeout"] == 120.0
        assert kwargs["max_tokens"] == 32768

    def test_call_structured_rejects_non_pydantic_model(self):
        """response_model 非 BaseModel 子类时快速失败"""
        service = LLMService(api_key="test-key", base_url="http://test", model="ep-default")

        with pytest.raises(TypeError):
            asyncio.run(
                service.call_structured(
                    messages=[{"role": "user", "content": "bad"}],
                    response_model=dict,
                )
            )

    def test_call_structured_offloads_sync_create_from_event_loop(self):
        """同步 OpenAI 调用在线程中执行，不阻塞已有事件循环"""
        service = LLMService(api_key="test-key", base_url="http://test", model="ep-default")
        patched_client = MagicMock()

        def slow_create(**_kwargs):
            time.sleep(0.05)
            return DummyStructuredResult(message="ok")

        patched_client.chat.completions.create.side_effect = slow_create

        async def run_with_marker():
            with patch("services.llm_service.instructor.from_openai", return_value=patched_client):
                task = asyncio.create_task(service.call_structured(
                    messages=[{"role": "user", "content": "Say ok"}],
                    response_model=DummyStructuredResult,
                ))
                await asyncio.sleep(0.01)
                marker_done = not task.done()
                result = await task
                return marker_done, result

        marker_done, result = asyncio.run(run_with_marker())

        assert marker_done
        assert result.message == "ok"

    def test_structured_client_does_not_patch_raw_client_used_by_call_sync(self):
        """结构化客户端与原始 client 隔离，避免污染 call_sync fallback"""
        service = LLMService(api_key="test-key", base_url="http://test", model="ep-default")
        raw_client = service.client
        structured_client = MagicMock()
        structured_client.chat.completions.create.return_value = DummyStructuredResult(message="ok")

        with patch("services.llm_service.instructor.from_openai", return_value=structured_client) as patch_mock:
            result = asyncio.run(service.call_structured(
                messages=[{"role": "user", "content": "Say ok"}],
                response_model=DummyStructuredResult,
            ))

        assert result.message == "ok"
        assert service.client is raw_client
        assert patch_mock.call_args.args[0] is not raw_client


class TestLeaderStructuredIntegration:
    """测试 Leader 三处结构化优先路径"""

    def test_requirement_assessor_uses_structured_result_before_regex_parser(self):
        """评估结构化成功时不调用正则解析"""
        from schemas.leader import AssessmentResult, QuestionOption

        llm_service = MagicMock()
        llm_service.call_structured = AsyncMock(return_value=AssessmentResult(
            score=68,
            passed=True,
            risk_level="medium",
            scene="technology",
            category="technology",
            questions=[QuestionOption(question="还有约束吗？", options=["无", "有", "暂不确定"])],
            details="需求基本完整",
            scores={"目标明确性": 30, "预期成果": 20, "边界范围": 18},
            risk_reason="中等投入",
        ))
        assessor = RequirementAssessor(llm_service)

        with patch.object(assessor, "_parse_assessment_response") as parse_mock:
            result = assessor.assess_requirement("设计用户系统", [])

        assert result["score"] == 68
        assert result["questions"][0]["question"] == "还有约束吗？"
        assert not parse_mock.called
        assert not llm_service.call_sync.called

    def test_requirement_assessor_falls_back_to_regex_parser(self):
        """评估结构化失败时保留旧解析 fallback"""
        llm_service = MagicMock()
        llm_service.call_structured = AsyncMock(side_effect=RuntimeError("schema failed"))
        llm_service.call_sync.return_value = """
        {"scene":"technology","scores":{},"total_score":70,"analysis":"完整","passed":true,"risk_level":"medium","category":"technology","questions":[]}
        """
        assessor = RequirementAssessor(llm_service)

        result = assessor.assess_requirement("设计用户系统", [])

        assert result["score"] == 70
        assert llm_service.call_sync.called

    def test_requirement_assessor_normalizes_fallback_category_alias(self):
        """旧 JSON 解析路径也应归一化中文分类。"""
        llm_service = MagicMock()
        llm_service.call_structured = AsyncMock(side_effect=RuntimeError("schema failed"))
        llm_service.call_sync.return_value = """
        {"scene":"general","scores":{},"total_score":70,"analysis":"完整","passed":true,"risk_level":"medium","category":"商业","questions":[]}
        """
        assessor = RequirementAssessor(llm_service)

        result = assessor.assess_requirement("做一个商业增长方案", [])

        assert result["category"] == "business"

    def test_normalize_category_key_maps_securities_to_investment(self):
        from schemas.leader import normalize_category_key

        assert normalize_category_key("securities") == "investment"
        assert normalize_category_key("证券") == "investment"

    def test_team_former_uses_structured_result_before_regex_parser(self):
        """团队选择结构化成功时不调用正则解析"""
        from schemas.leader import AgentSelection, TeamSelectionResult

        llm_service = MagicMock()
        llm_service.call_structured = AsyncMock(return_value=TeamSelectionResult(
            agents=[
                AgentSelection(
                    agent_id="research-analyst",
                    agent_name="调研分析师",
                    role_description="负责调研",
                    reason="需求需要调研",
                )
            ],
            reasoning="调研优先",
            team_strategy="调研后汇总",
        ))
        agent_parser = MagicMock()
        agent_parser.get_all_agents.return_value = [
            {"id": "research-analyst", "name": "调研分析师", "description": "市场调研"}
        ]
        former = TeamFormer(llm_service, agent_parser)

        with patch.object(former, "_parse_agent_selection_result") as parse_mock:
            result = former.form_team("做市场分析", risk_level="medium")

        assert result["selected_agents"][0]["agent_id"] == "research-analyst"
        assert result["team_strategy"] == "调研后汇总"
        assert not parse_mock.called
        assert not llm_service.call_sync.called

    def test_team_former_falls_back_to_existing_json_repair(self):
        """团队选择结构化失败时保留旧 JSON repair 兜底"""
        llm_service = MagicMock()
        llm_service.call_structured = AsyncMock(side_effect=RuntimeError("schema failed"))
        llm_service.call_sync.return_value = """
        {"selected_agents":[{"agent_id":"research-analyst","agent_name":"调研分析师","reason":"匹配"}],"team_strategy":"协作"}
        """
        agent_parser = MagicMock()
        agent_parser.get_all_agents.return_value = [
            {"id": "research-analyst", "name": "调研分析师", "description": "市场调研"}
        ]
        former = TeamFormer(llm_service, agent_parser)

        result = former.form_team("做市场分析", risk_level="medium")

        assert result["selected_agents"][0]["role_description"] == "匹配"
        assert llm_service.call_sync.called

    def test_team_former_filters_hallucinated_and_duplicate_agent_ids(self):
        from schemas.leader import AgentSelection, TeamSelectionResult

        llm_service = MagicMock()
        llm_service.call_structured = AsyncMock(return_value=TeamSelectionResult(
            agents=[
                AgentSelection(agent_id="ghost", agent_name="不存在", role_description="无", reason="幻觉"),
                AgentSelection(agent_id="research-analyst", agent_name="调研分析师", role_description="调研", reason="匹配"),
                AgentSelection(agent_id="research-analyst", agent_name="调研分析师", role_description="重复", reason="重复"),
            ],
            reasoning="测试",
            team_strategy="协作",
        ))
        agent_parser = MagicMock()
        agent_parser.get_all_agents.return_value = [
            {"id": "research-analyst", "name": "调研分析师", "description": "市场调研"}
        ]

        result = TeamFormer(llm_service, agent_parser).form_team("做市场分析")

        assert [a["agent_id"] for a in result["selected_agents"]] == ["research-analyst"]
        assert result["degraded"] is True

    def test_team_former_uses_registered_fallback_when_all_ids_invalid(self):
        from schemas.leader import AgentSelection, TeamSelectionResult

        llm_service = MagicMock()
        llm_service.call_structured = AsyncMock(return_value=TeamSelectionResult(
            agents=[AgentSelection(agent_id="ghost", agent_name="不存在", role_description="无", reason="幻觉")],
            reasoning="测试",
            team_strategy="协作",
        ))
        agent_parser = MagicMock()
        agent_parser.get_all_agents.return_value = [
            {"id": "oncology-expert", "name": "肿瘤专家", "description": "肿瘤诊疗", "category": "medical"},
            {"id": "research-analyst", "name": "调研分析师", "description": "市场调研"},
        ]

        result = TeamFormer(llm_service, agent_parser).form_team(
            "患者肺癌需要会诊", risk_level="high"
        )

        assert result["selected_agents"][0]["agent_id"] == "oncology-expert"
        assert result["selected_agents"][0]["is_fallback"] is True
        assert result["degraded"] is True

    def test_summarize_node_returns_structured_markdown_report(self):
        """LangGraph 汇总节点结构化成功时返回 markdown_report"""
        from schemas.leader import FinalReportResult

        llm_service = MagicMock()
        llm_service.get_max_output_tokens.return_value = 327680
        llm_service.call_structured = AsyncMock(return_value=FinalReportResult(
            title="综合建议",
            executive_summary="摘要",
            key_findings=["发现"],
            recommendations=["建议"],
            visual_blocks=[
                {
                    "block_id": "decision-options",
                    "type": "decision_matrix",
                    "title": "方案决策矩阵",
                    "data": {
                        "options": [
                            {
                                "option": "方案 A",
                                "pros": ["上线快"],
                                "cons": ["扩展性一般"],
                                "score": 78,
                                "recommendation": "适合短期验证",
                            }
                        ]
                    },
                }
            ],
            markdown_report=_long_final_report("节点结构化报告"),
        ))
        initialize_node_services(llm_service=llm_service)
        initialize_summarize_services(db_session=None)

        result = summarize_node({
            "session_id": 100,
            "user_message": "测试",
            "agent_results": [
                {"success": True, "agent_id": "research-analyst", "agent_name": "调研分析师", "content": "分析内容"}
            ],
            "sse_events": [],
        })

        assert result["final_report"].startswith("## 节点结构化报告")
        final_event = result["sse_events"][-1]
        assert final_event["summary"]["executive_summary"] == "摘要"
        assert final_event["structured_report"]["markdown_report"].startswith("## 节点结构化报告")
        assert final_event["structured_report"]["visual_blocks"][0]["type"] == "decision_matrix"
        assert not llm_service.call_sync.called
        assert llm_service.call_structured.call_args.kwargs["max_tokens"] == 2048
        assert llm_service.call_structured.call_args.kwargs["timeout"] == 120.0

    def test_summarize_node_preserves_short_structured_markdown_report(self):
        """结构化成功但正文较短时保留结果，并记录质量告警。"""
        from schemas.leader import FinalReportResult

        llm_service = MagicMock()
        llm_service.get_max_output_tokens.return_value = 327680
        llm_service.call_structured = AsyncMock(return_value=FinalReportResult(
            title="综合建议",
            executive_summary="摘要",
            key_findings=["发现"],
            recommendations=["建议"],
            markdown_report="## 综合建议\n\n正文太短",
        ))
        initialize_node_services(llm_service=llm_service)
        initialize_summarize_services(db_session=None)

        result = summarize_node({
            "session_id": 100,
            "user_message": "测试",
            "agent_results": [
                {"success": True, "agent_id": "research-analyst", "agent_name": "调研分析师", "content": "分析内容"}
            ],
            "sse_events": [],
        })

        assert result["final_report"] == "## 综合建议\n\n正文太短"
        assert not llm_service.call_sync.called
        final_event = result["sse_events"][-1]
        assert final_event["structured_report"]["quality_status"] == "warning"
        assert final_event["structured_report"]["quality_warnings"]

    def test_english_team_former_puts_output_language_rule_before_and_after_rubric(self):
        from schemas.leader import AgentSelection, TeamSelectionResult

        llm_service = MagicMock()
        llm_service.call_structured = AsyncMock(return_value=TeamSelectionResult(
            agents=[AgentSelection(
                agent_id="research-analyst",
                agent_name="Research Analyst",
                role_description="Research planning",
                reason="Covers market evidence",
            )],
            reasoning="The request needs market evidence.",
            team_strategy="Research first, then synthesize.",
        ))
        agent_parser = MagicMock()
        agent_parser.get_all_agents.return_value = [
            {"id": "research-analyst", "name": "Research Analyst", "description": "Market research"}
        ]

        result = TeamFormer(llm_service, agent_parser, locale="en-US").form_team("Compare rollout options")
        messages = llm_service.call_structured.await_args.kwargs["messages"]
        system_prompt, user_prompt = messages[0]["content"], messages[1]["content"]

        assert system_prompt.startswith("## Mandatory English output rule")
        assert system_prompt.rstrip().endswith("determine the language of the output values.")
        assert user_prompt.startswith("## Mandatory English output rule")
        assert user_prompt.rstrip().endswith("determine the language of the output values.")
        assert result["team_strategy"] == "Research first, then synthesize."

    def test_english_team_former_localizes_catalog_agent_name(self):
        from schemas.leader import AgentSelection, TeamSelectionResult

        llm_service = MagicMock()
        llm_service.call_structured = AsyncMock(return_value=TeamSelectionResult(
            agents=[AgentSelection(
                agent_id="oncology-expert",
                agent_name="肿瘤内科专家",
                role_description="肿瘤评估",
                reason="覆盖肿瘤诊疗",
            )],
            reasoning="The request needs oncology expertise.",
            team_strategy="Oncology review.",
        ))
        agent_parser = MagicMock()
        agent_parser.get_all_agents.return_value = [{
            "agent_id": "oncology-expert",
            "name": "肿瘤内科专家",
            "description": "肿瘤相关评估",
            "is_system": True,
        }]

        result = TeamFormer(llm_service, agent_parser, locale="en-US").form_team(
            "Review this oncology case"
        )

        assert result["selected_agents"][0]["agent_name"] == "Medical Oncology Specialist"

    def test_summarize_node_accepts_complete_medium_structured_report(self):
        """结构完整的 3000+ 字符报告不应因固定 5000 字阈值被 fallback。"""
        from schemas.leader import FinalReportResult

        llm_service = MagicMock()
        llm_service.get_max_output_tokens.return_value = 327680
        llm_service.call_structured = AsyncMock(return_value=FinalReportResult(
            title="综合建议",
            executive_summary="摘要",
            key_findings=["发现"],
            recommendations=["建议"],
            markdown_report=_medium_final_report("中等长度结构化报告"),
        ))
        initialize_node_services(llm_service=llm_service)
        initialize_summarize_services(db_session=None)

        result = summarize_node({
            "session_id": 100,
            "user_message": "测试",
            "agent_results": [
                {"success": True, "agent_id": "research-analyst", "agent_name": "调研分析师", "content": "分析内容"}
            ],
            "sse_events": [],
        })

        assert result["final_report"].startswith("## 中等长度结构化报告")
        assert not llm_service.call_sync.called
        final_event = result["sse_events"][-1]
        assert final_event["structured_report"]["markdown_report"].startswith("## 中等长度结构化报告")

    def test_summarize_node_falls_back_to_markdown_call(self):
        """LangGraph 汇总节点结构化失败时保留旧 Markdown 调用"""
        llm_service = MagicMock()
        llm_service.get_max_output_tokens.return_value = 327680
        llm_service.call_structured = AsyncMock(side_effect=RuntimeError("schema failed"))
        llm_service.call_sync.return_value = "## 节点旧报告\n\n正文"
        initialize_node_services(llm_service=llm_service)
        initialize_summarize_services(db_session=None)

        result = summarize_node({
            "session_id": 100,
            "user_message": "测试",
            "agent_results": [
                {"success": True, "agent_id": "research-analyst", "agent_name": "调研分析师", "content": "分析内容"}
            ],
            "sse_events": [],
        })

        assert result["final_report"] == "## 节点旧报告\n\n正文"
        assert llm_service.call_sync.called
        assert "不要在报告正文之后追加" in llm_service.call_sync.call_args.kwargs["message"]
        assert llm_service.call_sync.call_args.kwargs["max_tokens"] == 2048
        assert llm_service.call_sync.call_args.kwargs["max_attempts"] == 1
        assert llm_service.call_sync.call_args.kwargs["timeout"] == 120.0
        assert llm_service.call_sync.call_args.kwargs["reject_truncated"] is True

    def test_summarize_node_uses_local_fallback_when_llm_summary_times_out(self):
        """结构化和 Markdown 汇总都超时时，节点应返回本地降级摘要。"""
        llm_service = MagicMock()
        llm_service.get_max_output_tokens.return_value = 327680
        llm_service.call_structured = AsyncMock(side_effect=RuntimeError("Request timed out."))
        llm_service.call_sync.side_effect = RuntimeError("Request timed out.")
        initialize_node_services(llm_service=llm_service)
        initialize_summarize_services(db_session=None)

        result = summarize_node({
            "session_id": 100,
            "user_message": "测试",
            "agent_results": [
                {
                    "success": True,
                    "agent_id": "research-analyst",
                    "agent_name": "调研分析师",
                    "content": "分析内容",
                }
            ],
            "sse_events": [],
        })

        assert result["final_report"].startswith("## 综合建议")
        assert "最终报告生成超时" in result["final_report"]
        assert "调研分析师" in result["final_report"]


class TestReportStructures:
    """报告结构化辅助函数测试。"""

    def test_build_agent_structured_report_from_markdown(self):
        from leader.report_structures import build_agent_structured_report

        structured = build_agent_structured_report("""
        # 市场分析报告

        ## 关键发现
        - 需求增长明显
        - 渠道成本上升

        ## 建议
        - 先做 PoC

        ## 风险
        - 预算超支
        """)

        assert structured["summary"]["one_sentence"] == "报告指出：需求增长明显；建议：先做 PoC"
        assert "需求增长明显" in structured["summary"]["key_findings"]
        assert structured["summary"]["recommendations"] == ["先做 PoC"]
        assert structured["summary"]["risks"] == ["预算超支"]
        assert structured["summary"]["confidence"] > 0.6
        assert structured["markdown_report"].strip().startswith("# 市场分析报告")

    def test_agent_claims_bind_only_sentence_level_evidence_markers(self):
        from leader.report_structures import build_agent_structured_report

        structured = build_agent_structured_report(
            """
            # 市场分析

            ## 关键发现
            - 需求增长明显 [evidence_id:ev_growth]
            - 渠道成本上升

            ## 建议
            - 先做 PoC [evidence_id:ev_poc]
            """,
            evidence_refs=["ev_growth", "ev_poc"],
            claim_id_prefix="market-agent",
        )

        claims = structured["claims"]
        assert claims[0]["claim_id"] == "market-agent_claim_fact_1"
        assert claims[0]["text"] == "需求增长明显"
        assert claims[0]["evidence_relations"] == [{
            "evidence_id": "ev_growth",
            "relation": "supports",
        }]
        assert claims[1]["text"] == "渠道成本上升"
        assert claims[1]["evidence_relations"] == []
        assert claims[2]["claim_type"] == "recommendation"
        assert claims[2]["evidence_relations"][0]["evidence_id"] == "ev_poc"

    def test_build_agent_report_summary_confidence_tracks_signal_density(self):
        from leader.report_structures import build_agent_report_summary

        sparse = build_agent_report_summary("一句简短结论")
        rich = build_agent_report_summary(
            """
            # 深度评估

            - 市场需求在增长
            - 成本压力上升
            - 供应存在波动

            ## 建议
            - 先做 PoC

            ## 风险
            - 预算可能超支

            ## 待确认
            - 真实转化率
            """,
            evidence_refs=["ev_subtask_1_web_search_1"],
        )

        assert sparse.confidence < rich.confidence
        assert rich.confidence >= 0.8

    def test_build_agent_report_summary_extracts_inline_sections_and_skips_opening(self):
        from leader.report_structures import build_agent_report_summary

        summary = build_agent_report_summary(
            """
            作为规划专家，我从范围控制角度给出以下判断：

            ## 关键发现
            - MVP 范围已经超出首期承载能力

            建议：先收敛到单一闭环，再验证核心指标
            风险：继续并行铺开会拉长交付周期
            """
        )

        assert summary.one_sentence == "报告指出：MVP 范围已经超出首期承载能力；建议：先收敛到单一闭环，再验证核心指标"
        assert summary.recommendations == ["先收敛到单一闭环，再验证核心指标"]
        assert summary.risks == ["继续并行铺开会拉长交付周期"]

    def test_build_agent_report_summary_skips_role_only_heading_lines(self):
        from leader.report_structures import build_agent_report_summary

        summary = build_agent_report_summary(
            """
            有色金属分析师（证券）

            铜价短期偏强，关注库存拐点。

            ## 关键发现
            - 现货升水走强

            ## 建议
            - 逢回调再布局多单
            """
        )

        assert summary.one_sentence == "铜价短期偏强，关注库存拐点。"
        assert summary.key_findings == ["现货升水走强"]
        assert summary.recommendations == ["逢回调再布局多单"]

    def test_build_agent_report_summary_one_sentence_summarizes_content_not_recommendation(self):
        """one_sentence 概括报告内容，不直接复用第一条建议。"""
        from leader.report_structures import build_agent_report_summary

        summary = build_agent_report_summary(
            """
            ## 关键发现
            - 市场需求增长明显

            ## 建议
            - 优先投入 PoC 验证
            """
        )

        assert summary.one_sentence == "报告指出：市场需求增长明显；建议：优先投入 PoC 验证"
        assert summary.one_sentence != summary.recommendations[0]

    def test_build_agent_report_summary_uses_explicit_one_sentence_summary(self):
        from leader.report_structures import build_agent_report_summary

        summary = build_agent_report_summary(
            """
            # 产品商业化评估

            一句话摘要：本报告判断该产品具备小范围商业化验证条件，但需要先锁定高频刚需场景。

            ## 关键发现
            - 目标用户付费意愿集中在效率提升场景

            ## 建议
            - 先做垂直场景 PoC
            """
        )

        assert summary.one_sentence == "本报告判断该产品具备小范围商业化验证条件，但需要先锁定高频刚需场景。"
        assert summary.recommendations == ["先做垂直场景 PoC"]

    def test_build_agent_report_summary_one_sentence_fallback_to_risk(self):
        """无 recommendations 和 key_findings 时，从 risks 中取 one_sentence"""
        from leader.report_structures import build_agent_report_summary

        summary = build_agent_report_summary(
            """
            ## 风险
            - 预算可能超支 30%
            """
        )

        assert summary.one_sentence == "报告提示：预算可能超支 30%"

    def test_build_agent_report_summary_skips_lengthy_role_preamble(self):
        """长开场白（含括号角色描述）不进入 one_sentence"""
        from leader.report_structures import build_agent_report_summary

        summary = build_agent_report_summary(
            """
            作为一名专业的证券公司宏观分析师（融合达利欧债务周期框架），当前宏观经济正处于周期切换阶段：

            ## 关键发现
            - GDP 增速放缓至 4.2%

            ## 建议
            - 关注政策拐点信号
            """
        )

        assert "专业" not in summary.one_sentence
        assert "分析师" not in summary.one_sentence
        assert summary.one_sentence == "当前宏观经济正处于周期切换阶段："

    def test_build_agent_report_summary_skips_polite_instruction_preamble(self):
        """确认式、角色扮演式开场白不进入 one_sentence。"""
        from leader.report_structures import build_agent_report_summary

        summary = build_agent_report_summary(
            """
            好的，遵照您的指示。作为一名拥有超过20年临床检验经验的资深专家，我已经仔细审阅了您提供的所有临床资料。以下是我的综合分析报告。

            ## 关键发现
            - 血常规和炎症指标提示当前感染风险较高

            ## 建议
            - 结合症状复查炎症指标并由主管医生判断是否调整用药
            """
        )

        assert "好的" not in summary.one_sentence
        assert "遵照您的指示" not in summary.one_sentence
        assert "资深专家" not in summary.one_sentence
        assert "综合分析报告" not in summary.one_sentence
        assert summary.one_sentence == "报告指出：血常规和炎症指标提示当前感染风险较高；建议：结合症状复查炎症指标并由主管医生判断是否调整用药"

    def test_build_agent_report_summary_skips_demographic_only_opening(self):
        """年龄、性别等人口学片段不应作为报告摘要。"""
        from leader.report_structures import build_agent_report_summary

        summary = build_agent_report_summary(
            """
            女性，74岁

            ## 关键发现
            - 检验结果提示感染和营养风险并存，需要结合症状判断治疗优先级

            ## 建议
            - 优先复核炎症指标、肝肾功能和当前用药方案
            """
        )

        assert summary.one_sentence == "报告指出：检验结果提示感染和营养风险并存，需要结合症状判断治疗优先级；建议：优先复核炎症指标、肝肾功能和当前用药方案"

        summary = build_agent_report_summary(
            """
            74岁女性

            ## 关键发现
            - 影像和病史提示治疗耐受性评估应优先于单纯方案升级
            """
        )

        assert summary.one_sentence == "报告指出：影像和病史提示治疗耐受性评估应优先于单纯方案升级"

    def test_build_agent_report_summary_generic_heading_filtered(self):
        """通用章节标题（前言/引言/概述）不进入 one_sentence"""
        from leader.report_structures import build_agent_report_summary

        summary = build_agent_report_summary(
            """
            ## 前言
            ## 概述
            - 实际内容在这里
            """
        )

        assert summary.one_sentence not in ("前言", "概述")
        assert summary.one_sentence == "实际内容在这里"
