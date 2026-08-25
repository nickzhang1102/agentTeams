"""
Tests for requirement_loop_node

测试需求完善循环节点的核心功能
"""
import pytest
from unittest.mock import MagicMock, patch

from leader.workflow_nodes import (
    requirement_loop_node,
    route_after_requirement,
    human_input_node,
    initialize_node_services,
    _simple_assessment_fallback
)
from leader.workflow_state import LeaderWorkflowState


class TestRequirementLoopNodeCallsAssessor:
    """测试节点调用 RequirementAssessor"""

    def test_calls_assessor_with_basic_state(self):
        """测试基本状态调用评估器"""
        # Mock LLM service
        mock_llm_service = MagicMock()
        mock_llm_service.call_sync.return_value = """
        ```json
        {
          "scene": "technology",
          "scores": {"目标明确性": 30},
          "total_score": 70,
          "analysis": "需求描述较为完整",
          "passed": true,
          "risk_level": "medium",
          "category": "technology",
          "questions": []
        }
        ```
        """

        initialize_node_services(mock_llm_service)

        state = LeaderWorkflowState(
            conversation_id=1,
            user_message="设计一个用户认证系统",
            history=[],
            requirement_loop_count=0,
            sse_events=[]
        )

        result = requirement_loop_node(state)

        # 验证调用了 LLM service
        assert mock_llm_service.call_sync.called
        # 验证返回状态包含评估结果
        assert "assessment_result" in result
        assert "requirement_passed" in result

    def test_calls_assessor_with_enhanced_message(self):
        """测试用户回答后增强消息调用评估器"""
        mock_llm_service = MagicMock()
        mock_llm_service.call_sync.return_value = """
        ```json
        {
          "scene": "technology",
          "scores": {"目标明确性": 35},
          "total_score": 75,
          "analysis": "需求描述完整",
          "passed": true,
          "risk_level": "medium",
          "category": "technology",
          "questions": []
        }
        ```
        """

        initialize_node_services(mock_llm_service)

        state = LeaderWorkflowState(
            conversation_id=1,
            user_message="头疼",
            history=[],
            requirement_loop_count=1,
            user_answers=["三天了", "还有点发热"],
            sse_events=[]
        )

        result = requirement_loop_node(state)

        # 验证调用时消息包含用户回答
        call_args = mock_llm_service.call_sync.call_args
        message_arg = call_args[1]["message"]
        assert "三天了" in message_arg
        assert "还有点发热" in message_arg


class TestRequirementLoopNodeUpdatesState:
    """测试节点更新状态"""

    def test_updates_state_with_passed_result(self):
        """测试通过时更新状态"""
        mock_llm_service = MagicMock()
        mock_llm_service.call_sync.return_value = """
        ```json
        {
          "scene": "technology",
          "scores": {},
          "total_score": 80,
          "analysis": "需求完整",
          "passed": true,
          "risk_level": "low",
          "category": "technology",
          "questions": []
        }
        ```
        """

        initialize_node_services(mock_llm_service)

        state = LeaderWorkflowState(
            conversation_id=1,
            user_message="设计用户认证系统",
            history=[],
            requirement_loop_count=0,
            sse_events=[]
        )

        result = requirement_loop_node(state)

        assert result["requirement_passed"] == True
        assert result["assessment_result"]["score"] == 80
        assert "assessment_result" in result
        # 通过时不增加 loop_count
        assert "requirement_loop_count" not in result or result.get("requirement_loop_count") == 0

    def test_updates_state_with_failed_result(self):
        """测试未通过时更新状态"""
        mock_llm_service = MagicMock()
        mock_llm_service.call_sync.return_value = """
        ```json
        {
          "scene": "general",
          "scores": {},
          "total_score": 30,
          "analysis": "需求过于简短",
          "passed": false,
          "risk_level": "low",
          "category": "other",
          "questions": ["请提供更多细节", "请说明目标"]
        }
        ```
        """

        initialize_node_services(mock_llm_service)

        state = LeaderWorkflowState(
            conversation_id=1,
            user_message="头疼",
            history=[],
            requirement_loop_count=0,
            sse_events=[]
        )

        result = requirement_loop_node(state)

        assert result["requirement_passed"] == False
        # loop_count 递增已移至 human_input_node
        assert len(result["requirement_questions"]) == 2

    def test_updates_sse_events(self):
        """测试 SSE 事件更新"""
        mock_llm_service = MagicMock()
        mock_llm_service.call_sync.return_value = """
        ```json
        {
          "scene": "technology",
          "scores": {},
          "total_score": 70,
          "analysis": "需求较为完整",
          "passed": true,
          "risk_level": "medium",
          "category": "technology",
          "questions": []
        }
        ```
        """

        initialize_node_services(mock_llm_service)

        state = LeaderWorkflowState(
            conversation_id=1,
            session_id=100,
            user_message="设计系统",
            history=[],
            requirement_loop_count=0,
            sse_events=[]
        )

        result = requirement_loop_node(state)

        # 评估只使用 assessment_result 这一种 SSE 表示，避免前端重复展示
        event_types = [e["type"] for e in result["sse_events"]]
        assert event_types.count("assessment_result") == 1
        assert "leader_thinking" not in event_types

    def test_generates_question_event_when_failed(self):
        """测试未通过时生成提问事件"""
        mock_llm_service = MagicMock()
        mock_llm_service.call_sync.return_value = """
        ```json
        {
          "scene": "general",
          "scores": {},
          "total_score": 30,
          "analysis": "需求简短",
          "passed": false,
          "risk_level": "low",
          "category": "other",
          "questions": ["请补充"]
        }
        ```
        """

        initialize_node_services(mock_llm_service)

        state = LeaderWorkflowState(
            conversation_id=1,
            session_id=100,
            user_message="头疼",
            history=[],
            requirement_loop_count=0,
            sse_events=[]
        )

        result = requirement_loop_node(state)

        # leader_question 事件已移至 human_input_node 发送
        # requirement_loop_node 仅保存 questions 到 state（新格式：对象）
        assert "requirement_questions" in result
        assert len(result["requirement_questions"]) == 1
        assert result["requirement_questions"][0]["question"] == "请补充"


class TestSimpleAssessmentFallback:
    """测试降级评估"""

    def test_fallback_for_short_message(self):
        """测试短消息降级评估（< 20 字符）"""
        result = _simple_assessment_fallback("短消息")

        assert result["passed"] == False
        assert result["score"] == 30
        assert result["questions"]

    def test_fallback_for_long_message(self):
        """测试较长消息降级评估（>= 20 字符）"""
        result = _simple_assessment_fallback("这是一个完整的需求描述包含多个要点超过二十个字符")

        assert result["passed"] == True
        assert result["score"] == 85

    def test_fallback_for_medical_message_fails_closed(self):
        result = _simple_assessment_fallback(
            "患者胃癌术后出现腹痛和消瘦，病理及复查结果尚未完整提供"
        )

        assert result["scene"] == "medical"
        assert result["risk_level"] == "high"
        assert result["passed"] is False
        assert result["questions"]


class TestInitializeNodeServices:
    """测试服务初始化"""

    def test_initialize_sets_services(self):
        """测试初始化设置服务"""
        mock_llm_service = MagicMock()
        initialize_node_services(mock_llm_service, 8000)

        # 验证后续调用能使用服务
        mock_llm_service.call_sync.return_value = """
        ```json
        {"scene": "general", "scores": {}, "total_score": 50, "passed": true, "questions": [], "risk_level": "low", "category": "other"}
        ```
        """

        state = LeaderWorkflowState(
            conversation_id=1,
            user_message="测试",
            history=[]
        )

        result = requirement_loop_node(state)
        assert mock_llm_service.call_sync.called


class TestRouteAfterRequirement:
    """测试评估后路由条件"""

    def test_route_after_requirement_passed(self):
        """测试评估通过 → team_form"""
        state = LeaderWorkflowState(
            conversation_id=1,
            user_message="完整需求",
            requirement_passed=True,
            requirement_loop_count=0
        )

        result = route_after_requirement(state)
        assert result == "team_form"

    def test_route_after_requirement_loop_limit(self):
        """测试循环上限 → team_form（强制）"""
        state = LeaderWorkflowState(
            conversation_id=1,
            user_message="简短需求",
            requirement_passed=False,
            requirement_loop_count=3  # 已达上限
        )

        result = route_after_requirement(state)
        assert result == "team_form"

    def test_route_after_requirement_human_input(self):
        """测试未通过且有追问问题 → human_input"""
        state = LeaderWorkflowState(
            conversation_id=1,
            user_message="简短需求",
            requirement_passed=False,
            requirement_loop_count=0,
            requirement_questions=["请补充细节", "请说明目标"]
        )

        result = route_after_requirement(state)
        assert result == "human_input"

    def test_route_after_requirement_no_questions_forces_team_form(self):
        """测试未通过但无追问问题 → team_form（避免卡死）"""
        state = LeaderWorkflowState(
            conversation_id=1,
            user_message="简短需求",
            requirement_passed=False,
            requirement_loop_count=0,
            requirement_questions=[]
        )

        result = route_after_requirement(state)
        assert result == "team_form"

    def test_route_after_requirement_loop_count_1(self):
        """测试第 1 轮未通过且有追问 → human_input"""
        state = LeaderWorkflowState(
            conversation_id=1,
            requirement_passed=False,
            requirement_loop_count=1,
            requirement_questions=["请补充"]
        )

        result = route_after_requirement(state)
        assert result == "human_input"

    def test_route_after_requirement_loop_count_2(self):
        """测试第 2 轮未通过且有追问 → human_input"""
        state = LeaderWorkflowState(
            conversation_id=1,
            requirement_passed=False,
            requirement_loop_count=2,
            requirement_questions=["请补充"]
        )

        result = route_after_requirement(state)
        assert result == "human_input"

    def test_route_after_requirement_missing_fields(self):
        """测试缺失字段默认值 → team_form（无问题可追问）"""
        state = LeaderWorkflowState(
            conversation_id=1,
            user_message="测试"
            # 缺失 requirement_passed, requirement_loop_count, requirement_questions
        )

        result = route_after_requirement(state)
        # 默认 passed=False, loop_count=0, questions=[] → team_form
        assert result == "team_form"


class TestHumanInputNode:
    """测试用户输入等待节点"""

    def test_human_input_node_waits(self):
        """测试节点返回等待状态"""
        state = LeaderWorkflowState(
            conversation_id=1,
            session_id=100,
            requirement_loop_count=1,
            requirement_questions=[{"question": "请补充细节", "options": ["选项A", "选项B"]}],
            sse_events=[]
        )

        result = human_input_node(state)

        assert result["current_phase"] == "human_input"
        # 应包含 leader_question + leader_thinking 两个事件
        assert len(result["sse_events"]) == 2
        assert result["sse_events"][0]["type"] == "leader_question"
        assert result["sse_events"][1]["type"] == "leader_thinking"

    def test_human_input_node_skips_empty_questions(self):
        """测试无问题时跳过追问（early return）"""
        state = LeaderWorkflowState(
            conversation_id=1,
            session_id=100,
            requirement_loop_count=1,
            requirement_questions=[],  # 空问题列表
            sse_events=[]
        )

        result = human_input_node(state)

        # 空问题列表 → 跳过追问，直接进入下一阶段
        assert result["current_phase"] == "team_form"
        assert len(result["sse_events"]) == 0

    def test_human_input_node_preserves_existing_events(self):
        """测试节点保留已有事件"""
        existing_event = {"type": "test", "content": "existing"}

        state = LeaderWorkflowState(
            conversation_id=1,
            session_id=100,
            requirement_loop_count=1,
            requirement_questions=[{"question": "请补充", "options": ["A", "B"]}],
            sse_events=[existing_event]
        )

        result = human_input_node(state)

        # 保留已有事件
        assert existing_event in result["sse_events"]
        # 新增 leader_question + leader_thinking
        assert len(result["sse_events"]) == 3


class TestLoopCountLimit:
    """测试循环上限"""

    def test_loop_count_3_forces_team_form(self):
        """测试 loop_count=3 强制进入 team_form"""
        # 第 3 轮未通过
        state = LeaderWorkflowState(
            conversation_id=1,
            requirement_passed=False,
            requirement_loop_count=3,
            requirement_questions=["问题"],
            user_answers=["回答"]
        )

        result = route_after_requirement(state)
        assert result == "team_form"

    def test_loop_count_exceeds_limit_forces_team_form(self):
        """测试 loop_count>3 强制进入 team_form"""
        state = LeaderWorkflowState(
            conversation_id=1,
            requirement_passed=False,
            requirement_loop_count=5
        )

        result = route_after_requirement(state)
        assert result == "team_form"


class TestSSEEventFormat:
    """测试 SSE 事件格式"""

    def test_assessment_result_event_format(self):
        """测试 assessment_result 事件格式"""
        mock_llm_service = MagicMock()
        mock_llm_service.call_sync.return_value = """
        ```json
        {
          "scene": "technology",
          "scores": {},
          "total_score": 70,
          "analysis": "需求完整",
          "passed": true,
          "risk_level": "medium",
          "category": "technology",
          "questions": []
        }
        ```
        """

        initialize_node_services(mock_llm_service)

        state = LeaderWorkflowState(
            conversation_id=1,
            session_id=100,
            user_message="设计系统",
            history=[]
        )

        result = requirement_loop_node(state)

        # 找到 assessment_result 事件
        event = next(e for e in result["sse_events"] if e["type"] == "assessment_result")

        # 验证必要字段
        assert "type" in event
        assert "session_id" in event
        assert "score" in event
        assert "passed" in event
        assert "risk_level" in event

    def test_leader_question_event_format(self):
        """测试 leader_question 事件格式（由 human_input_node 发送）"""
        state = LeaderWorkflowState(
            conversation_id=1,
            session_id=100,
            user_message="短",
            history=[],
            requirement_loop_count=0,
            requirement_questions=[{"question": "请补充细节", "options": ["选项A", "选项B"]}],
            sse_events=[]
        )

        result = human_input_node(state)

        # 找到 leader_question 事件
        event = next(e for e in result["sse_events"] if e["type"] == "leader_question")

        # 验证必要字段
        assert "type" in event
        assert "session_id" in event
        assert "questions" in event
        assert isinstance(event["questions"], list)
        assert event["questions"][0]["question"] == "请补充细节"
        assert event["questions"][0]["options"] == ["选项A", "选项B"]
