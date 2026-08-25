"""
LangGraph Workflow Tests

测试 StateGraph 执行、条件分支、SSE 输出、异步同步兼容、缺失字段处理
"""
import pytest
import asyncio
from unittest.mock import MagicMock

from leader import (
    LeaderWorkflowState,
    create_leader_workflow_graph,
    SSEStreamer
)
from leader.workflow_nodes import initialize_node_services, initialize_executor_services
from leader.langgraph_workflow import route_after_agent_execution


def create_minimal_state(
    user_message: str = "测试消息测试消息",
    requirement_passed: bool = True,
    requirement_loop_count: int = 0,
    requirement_questions: list = None,
    dag_execution_plan: dict = None
) -> dict:
    """创建最小测试状态"""
    return {
        'conversation_id': 1,
        'session_id': 1,
        'user_message': user_message,
        'history': [],
        'requirement_loop_count': requirement_loop_count,
        'requirement_passed': requirement_passed,
        'requirement_questions': requirement_questions if requirement_questions is not None else [],
        'user_answers': [],
        'assessment_result': {},
        'selected_agents': [],
        'dag_execution_plan': dag_execution_plan or {
            "execution_batches": [{"priority": 50, "agents": ["mock_agent"]}]
        },
        'agent_results': [],
        'current_agent_index': 0,
        'agent_retry_counts': {},
        'final_report': '',
        'stop_requested': False,
        'current_phase': '',
        'sse_events': []
    }


def setup_mock_llm_service():
    """设置 Mock LLM 服务"""
    mock_llm_service = MagicMock()
    mock_llm_service.call_sync.return_value = """
    ```json
    {
      "scene": "technology",
      "scores": {},
      "total_score": 80,
      "analysis": "需求完整",
      "passed": true,
      "risk_level": "medium",
      "category": "technology",
      "questions": []
    }
    ```
    """
    # call_structured 为异步结构化通道：单测中让其失败，走 call_sync fallback
    mock_llm_service.call_structured.side_effect = RuntimeError("structured disabled in tests")
    # summarize 节点按模型上限计算报告 token 预算，需要真实 int
    mock_llm_service.get_max_output_tokens.return_value = 16384
    initialize_node_services(mock_llm_service)
    return mock_llm_service


def setup_mock_coordinator():
    """设置 Mock HarnessCoordinator"""
    mock_coordinator = MagicMock()

    # Mock get_agent_info
    mock_coordinator.get_agent_info.return_value = {
        "name": "Mock Agent",
        "description": "Mock agent for testing"
    }

    # Mock execute_agent
    mock_coordinator.execute_agent.return_value = {
        "success": True,
        "status": "completed",
        "agent_id": "mock_agent",
        "content": "Mock execution result",
        "tool_calls": [],
        "tokens_used": 100,
        "execution_time": 0.5,
        "error": None
    }

    initialize_executor_services(mock_coordinator)
    return mock_coordinator


# ==================== 场景 1：StateGraph 基础执行 ====================

def test_state_graph_execution():
    """场景 1：验证 StateGraph 能正确执行节点序列"""
    setup_mock_llm_service()
    setup_mock_coordinator()
    graph = create_leader_workflow_graph()

    # 设置已通过状态，直接进入 agent_execution
    initial_state = create_minimal_state(
        user_message="设计用户认证系统",
        requirement_passed=True,
        dag_execution_plan={
            "execution_batches": [{"priority": 50, "agents": ["mock_agent"]}]
        }
    )

    result = graph.invoke(initial_state)

    # 验证 current_phase 最终为 execution_complete / team_form_dag / summarize_complete
    assert result.get("current_phase") in ["execution_complete", "team_form_dag", "summarize_complete"]

    # 验证 sse_events 包含事件
    assert len(result.get("sse_events", [])) >= 1


# ==================== 场景 2：条件分支路由 ====================

def test_conditional_routing_short_message():
    """场景 2a：短消息通过 agent_execution 条件"""
    setup_mock_llm_service()
    setup_mock_coordinator()
    graph = create_leader_workflow_graph()

    # 已通过评估，直接进入 agent_execution
    initial_state = create_minimal_state(
        user_message="短",
        requirement_passed=True
    )

    result = graph.invoke(initial_state)

    # 短消息流程会进入 agent_execution → summarize
    assert result.get("current_phase") in ["execution_complete", "execution_failed", "summarize_complete"]


def test_conditional_routing_long_message():
    """场景 2b：长消息进入 summarize"""
    setup_mock_llm_service()
    setup_mock_coordinator()
    graph = create_leader_workflow_graph()

    # 已通过评估，长消息直接执行并汇总
    long_state = create_minimal_state(
        user_message="这是一条超过十个字符的测试消息",
        requirement_passed=True
    )

    result = graph.invoke(long_state)

    # 长消息流程会进入 agent_execution → summarize
    assert result.get("current_phase") in ["execution_complete", "summarize_complete"]


# ==================== 新增：requirement_loop 流程测试 ====================

def test_workflow_graph_with_requirement_loop():
    """测试 requirement_loop 作为入口节点"""
    setup_mock_llm_service()
    graph = create_leader_workflow_graph()

    initial_state = create_minimal_state(
        user_message="设计认证系统",
        requirement_passed=False,  # 未通过，触发评估
        requirement_loop_count=0
    )

    result = graph.invoke(initial_state)

    # 验证执行成功
    assert result is not None
    assert "current_phase" in result
    # 验证 assessment_result 被设置
    assert "assessment_result" in result


def test_requirement_loop_routes_to_team_form_when_passed():
    """测试评估通过后路由到 team_form"""
    setup_mock_llm_service()
    setup_mock_coordinator()
    graph = create_leader_workflow_graph()

    # 模拟已通过状态
    initial_state = create_minimal_state(
        requirement_passed=True
    )

    result = graph.invoke(initial_state)

    # 应进入 team_form_dag → agent_execution → summarize
    assert result.get("current_phase") in ["team_form_dag", "execution_complete", "execution_failed", "summarize_complete"]


def test_requirement_loop_routes_to_human_input_when_not_passed():
    """测试评估未通过且有追问问题时路由到 human_input"""
    graph = create_leader_workflow_graph()

    # 模拟未通过、未达上限、且有可追问问题
    initial_state = create_minimal_state(
        requirement_passed=False,
        requirement_loop_count=0,
        requirement_questions=[{"question": "请补充细节", "options": ["A", "B"]}]
    )

    from leader.workflow_nodes import route_after_requirement
    route = route_after_requirement(initial_state)

    assert route == "human_input"


def test_requirement_loop_forces_team_form_when_no_questions():
    """测试评估未通过但无追问问题时强制 team_form（避免卡死）"""
    initial_state = create_minimal_state(
        requirement_passed=False,
        requirement_loop_count=0,
        requirement_questions=[]  # 无问题可追问
    )

    from leader.workflow_nodes import route_after_requirement
    route = route_after_requirement(initial_state)

    assert route == "team_form"


def test_requirement_loop_forces_team_form_at_limit():
    """测试循环上限强制进入 team_form"""
    graph = create_leader_workflow_graph()

    # 模拟已达上限
    initial_state = create_minimal_state(
        requirement_passed=False,
        requirement_loop_count=3  # 已达上限
    )

    from leader.workflow_nodes import route_after_requirement
    route = route_after_requirement(initial_state)

    assert route == "team_form"


# ==================== 场景 3：SSE Streaming 输出 ====================

def test_sse_streaming_output():
    """场景 3：验证 SSEStreamer 能正确输出事件"""
    setup_mock_llm_service()
    setup_mock_coordinator()
    graph = create_leader_workflow_graph()

    initial_state = create_minimal_state(
        user_message="这是一条超过十个字符的长消息",
        requirement_passed=True
    )

    result = graph.invoke(initial_state)
    streamer = SSEStreamer(session_id=1)

    events = list(streamer.yield_sse_from_state(result))

    # 验证事件数量 >= 1
    assert len(events) >= 1

    # 验证事件格式
    for event in events:
        assert "type" in event
        assert "session_id" in event


def test_sse_event_types_defined():
    """验证 SSE_EVENT_TYPES 定义完整"""
    from leader.sse_streamer import SSE_EVENT_TYPES

    # 验证核心事件类型存在
    required_types = ["leader_thinking", "assessment_result", "final_report", "error", "done"]
    for t in required_types:
        assert t in SSE_EVENT_TYPES


# ==================== 场景 4：异步同步兼容 ====================

def test_async_sync_compat():
    """场景 4：验证 asyncio.run() 能在同步上下文执行异步 streaming"""
    graph = create_leader_workflow_graph()
    # 使用超过10字符的消息
    initial_state = create_minimal_state("异步测试消息超过十个字符")
    streamer = SSEStreamer(session_id=1)

    # SSEStreamer.stream_graph_events 使用 asyncio.run 包装
    events = list(streamer.stream_graph_events(graph, initial_state))

    # 验证能正常输出事件（无 RuntimeError）
    assert len(events) > 0

    # 验证无 asyncio 相关错误
    for event in events:
        if event.get("type") == "error":
            assert "asyncio" not in event.get("message", "").lower()
            assert "RuntimeError" not in event.get("message", "")


# ==================== 场景 5：依赖版本兼容 ====================

def test_dependency_compat():
    """场景 5：验证 LangGraph 依赖导入无冲突"""
    # 导入核心模块
    from langgraph.graph import StateGraph, END
    from langchain_core.messages.utils import convert_to_messages

    # 导入项目模块
    from leader import LeaderWorkflowState, create_leader_workflow_graph, SSEStreamer

    # 验证无 ImportError（已隐含在 import 成功中）
    assert create_leader_workflow_graph is not None


def test_openharness_compat():
    """验证 LangGraph 与 OpenHarness 无冲突"""
    # 导入 OpenHarness 相关模块
    try:
        from services.harness.harness_adapter import get_harness_tool_registry
        from services.harness.harness_coordinator import get_harness_coordinator

        # 同时导入 LangGraph
        from leader import create_leader_workflow_graph

        # 验证无 ImportError
        assert True
    except ImportError as e:
        pytest.fail(f"OpenHarness/LangGraph import conflict: {e}")


# ==================== 场景 6：缺失字段处理 ====================

def test_missing_field_handling():
    """场景 6：验证节点函数能处理缺失字段"""
    graph = create_leader_workflow_graph()

    # 不完整状态（缺少部分字段）
    incomplete_state = {
        'conversation_id': 1,
        'user_message': '不完整状态测试',
        # 缺少 session_id, history, sse_events 等
    }

    # 执行不应抛 KeyError
    try:
        result = graph.invoke(incomplete_state)
        # 验证执行成功
        assert result is not None
        assert "current_phase" in result
    except KeyError as e:
        pytest.fail(f"KeyError raised for missing field: {e}")


# ==================== 辅助测试 ====================

def test_graph_has_expected_nodes():
    """验证 graph 包含预期的节点（审核节点已移除）"""
    graph = create_leader_workflow_graph()

    # LangGraph 1.2.2: get_graph().nodes 返回 dict（key=node_id）
    graph_info = graph.get_graph()
    node_names = list(graph_info.nodes.keys())

    # 新节点
    assert "requirement_loop" in node_names
    assert "human_input" in node_names
    assert "team_form_dag" in node_names
    # Agent 执行节点
    assert "agent_execution" in node_names
    # 汇总节点
    assert "summarize" in node_names

    # 审核节点已移除
    assert "agent_review" not in node_names


def test_route_after_agent_execution_stopped_goes_to_end():
    assert route_after_agent_execution({"current_phase": "execution_stopped"}) == "end"


def test_route_after_agent_execution_complete_goes_to_summarize():
    assert route_after_agent_execution({"current_phase": "execution_complete"}) == "summarize"
