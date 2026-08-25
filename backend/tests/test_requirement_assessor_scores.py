import importlib.util
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock


def _load_requirement_assessor():
    module_path = Path(__file__).resolve().parents[1] / "leader" / "requirement_assessor.py"
    spec = importlib.util.spec_from_file_location("test_requirement_assessor_module", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.RequirementAssessor


RequirementAssessor = _load_requirement_assessor()


def test_normalize_assessment_result_recomputes_total_from_displayed_scores():
    assessor = RequirementAssessor(llm_service=None)

    result = assessor._normalize_assessment_result({
        "scene": "medical",
        "scores": {
            "nutrition": 1,
            "pain": 5,
        },
        "total_score": 9,
        "analysis": "信息不足",
        "risk_level": "high",
        "category": "medical",
        "questions": [],
    })

    assert result["score"] == 0
    assert result["details"]["scores"] == {}
    assert result["passed"] is False


def test_normalize_assessment_result_caps_each_dimension_with_scene_limits():
    assessor = RequirementAssessor(llm_service=None)

    result = assessor._normalize_assessment_result({
        "scene": "medical",
        "scores": {
            "症状描述": 40,
            "用药情况": 12,
            "个人情况": 3,
            "goal_clarity": 35,
        },
        "total_score": 8,
        "analysis": "信息部分齐全",
        "risk_level": "medium",
        "category": "medical",
        "questions": [],
    })

    assert result["details"]["scores"] == {
        "症状描述": 35,
        "用药情况": 10,
        "个人情况": 3,
    }
    assert result["score"] == 48
    assert result["passed"] is False


def test_build_assessment_prompt_includes_scene_score_reference():
    assessor = RequirementAssessor(llm_service=None)

    prompt = assessor._build_assessment_prompt("头疼三天", "", None)

    assert "场景评分详情规范" in prompt
    assert "scores" in prompt
    assert "必须严格使用当前" in prompt
    assert "中文维度名" in prompt
    assert "- 症状描述: 0-35 分；哪里不舒服？持续多久？严重程度？" in prompt
    assert "- 目标明确性: 0-35 分；要解决什么问题？达到什么目的？" in prompt


def test_assessment_model_to_result_uses_normalized_scores_for_structured_path():
    from schemas.leader import AssessmentResult

    assessor = RequirementAssessor(llm_service=None)
    structured = AssessmentResult.model_validate({
        "scene": "medical",
        "scores": {
            "病情严重度": 80,
            "营养风险": 90,
            "干预紧迫性": 85,
        },
        "total_score": 20,
        "analysis": "维度漂移",
        "passed": False,
        "risk_level": "high",
        "category": "medical",
        "questions": [],
    })

    result = assessor._assessment_model_to_result(structured)

    assert result["score"] == 0
    assert result["details"]["scores"] == {}
    assert result["passed"] is False


def test_assess_requirement_uses_assessment_prompt_even_with_context_messages():
    from schemas.leader import AssessmentResult

    llm_service = MagicMock()
    llm_service.call_structured = AsyncMock(return_value=AssessmentResult.model_validate({
        "scene": "medical",
        "scores": {
            "症状描述": 12,
            "病史信息": 8,
        },
        "total_score": 20,
        "analysis": "信息不足",
        "passed": False,
        "risk_level": "medium",
        "category": "medical",
        "questions": [],
    }))
    assessor = RequirementAssessor(llm_service=llm_service)

    result = assessor.assess_requirement(
        message="头疼三天",
        history=[],
        context_messages=[{"role": "user", "content": "旧上下文消息"}],
        previous_questions=[{"question": "持续多久？", "options": ["1天", "3天", "一周"]}],
    )

    assert result["details"]["scores"] == {
        "症状描述": 12,
        "病史信息": 8,
    }

    call_kwargs = llm_service.call_structured.call_args.kwargs
    messages = call_kwargs["messages"]
    assert messages[-1]["role"] == "user"
    assert "场景评分详情规范" in messages[-1]["content"]
    assert "已问过的问题" in messages[-1]["content"]


def test_simple_assessment_fails_closed_for_chinese_medical_case():
    assessor = RequirementAssessor(llm_service=None)

    result = assessor._simple_assessment(
        "患者肺腺癌术后复发，近期影像提示肝转移，请评估下一步治疗方案"
    )

    assert result["scene"] == "medical"
    assert result["category"] == "medical"
    assert result["risk_level"] == "high"
    assert result["passed"] is False
    assert result["degraded"] is True
    assert len(result["questions"]) >= 1


def test_simple_assessment_uses_non_whitespace_length_for_chinese_text():
    assessor = RequirementAssessor(llm_service=None)

    result = assessor._simple_assessment(
        "请比较三个供应商的交付周期成本质量风险并给出选择建议"
    )

    assert result["passed"] is True
    assert result["score"] == 85


def test_simple_assessment_does_not_treat_code_check_as_medical():
    assessor = RequirementAssessor(llm_service=None)

    result = assessor._simple_assessment(
        "请检查代码中的并发问题并给出完整修复方案和回归测试"
    )

    assert result["scene"] == "general"
