"""
SSE Streamer Integration Tests

测试 SSE_EVENT_TYPES 字段补齐、LangGraph event 映射、向后兼容、异常处理
"""
import pytest
import json
import queue
import threading
import time
from unittest.mock import Mock, patch, MagicMock

# 先导入不依赖应用上下文的模块
from leader.leader_events import build_fixed_sse_message
from leader.sse_streamer import SSE_EVENT_TYPES


def create_minimal_state(user_message: str = "测试消息测试消息") -> dict:
    """创建最小测试状态"""
    return {
        'conversation_id': 1,
        'session_id': 1,
        'user_message': user_message,
        'history': [],
        'requirement_loop_count': 0,
        'requirement_passed': False,
        'requirement_questions': [],
        'user_answers': [],
        'assessment_result': {},
        'selected_agents': [],
        'dag_execution_plan': {},
        'agent_results': [],
        'current_agent_index': 0,
        'agent_retry_counts': {},
        'final_report': '',
        'stop_requested': False,
        'current_phase': '',
        'sse_events': []
    }


# ==================== 场景 1：SSE_EVENT_TYPES 字段补齐 ====================

def test_sse_event_types_count():
    """场景 1a：验证事件类型数量为 21 种"""
    assert len(SSE_EVENT_TYPES) == 21


def test_sse_event_types_agent_result_has_tool_calls():
    """场景 1b：agent_result 包含 tool_calls 字段"""
    assert "tool_calls" in SSE_EVENT_TYPES["agent_result"]
    assert "content_locale" in SSE_EVENT_TYPES["agent_result"]
    assert "raw_tool_results" not in SSE_EVENT_TYPES["agent_result"]
    assert "content_locale" in SSE_EVENT_TYPES["final_report"]
    assert "content_locale" in SSE_EVENT_TYPES["leader_thinking"]


def test_fixed_sse_message_has_stable_key_params_and_localized_fallback():
    event_message = build_fixed_sse_message(
        "en-US",
        "leader.phase.execution_starting",
        {"agent_count": 3, "batch_count": 2},
    )

    assert event_message == {
        "message_key": "leader.phase.execution_starting",
        "message_params": {"agent_count": 3, "batch_count": 2},
        "message": "Starting 3 agents across 2 batches...",
    }
    assert build_fixed_sse_message(
        "zh-CN",
        "leader.phase.summarizing",
    )["message"] == "正在汇总所有专家意见..."


@pytest.mark.parametrize(
    "event_type",
    [
        "leader_thinking",
        "team_forming",
        "execution_status",
        "execution_complete",
        "leader_summarizing",
        "execution_stopped",
        "error",
        "done",
    ],
)
def test_fixed_sse_event_types_expose_message_contract(event_type):
    assert {"message_key", "message_params", "message"} <= SSE_EVENT_TYPES[event_type]


# ==================== 场景 2：LangGraph event 映射扩展 ====================

def test_on_chain_start_mapping():
    """场景 2a：节点自身负责实质事件，框架开始事件不重复推送。"""
    from leader import SSEStreamer
    streamer = SSEStreamer(session_id=1)
    event = {
        "event": "on_chain_start",
        "name": "test_node",
        "data": {}
    }
    sse_events = streamer.langgraph_event_to_sse(event)

    assert sse_events == []


def test_on_chain_end_does_not_forward_accumulated_sse_events():
    """场景 2b：on_chain_end 不转发 state 累计的 sse_events。

    各节点产生事件时已通过 _emit/push_sse_event 实时推送；state.sse_events
    是历史累计值，在每个节点结束时转发会把同一事件投递 O(节点数) 次。
    """
    from leader import SSEStreamer
    streamer = SSEStreamer(session_id=1)
    event = {
        "event": "on_chain_end",
        "name": "test_node",
        "data": {
            "updates": {
                "sse_events": [
                    {"type": "assessment_result", "score": 85}
                ]
            }
        }
    }
    sse_events = streamer.langgraph_event_to_sse(event)

    assert sse_events == []


def test_on_chain_end_without_sse_events():
    """场景 2c：无节点事件时不生成空洞的默认事件。"""
    from leader import SSEStreamer
    streamer = SSEStreamer(session_id=1)
    event = {
        "event": "on_chain_end",
        "name": "test_node",
        "data": {}
    }
    sse_events = streamer.langgraph_event_to_sse(event)

    assert sse_events == []


def test_on_tool_start_mapping():
    """场景 2d：on_tool_start → agent_status 事件"""
    from leader import SSEStreamer
    streamer = SSEStreamer(session_id=1)
    event = {
        "event": "on_tool_start",
        "name": "test_tool",
        "data": {}
    }
    sse_events = streamer.langgraph_event_to_sse(event)

    assert sse_events[0]["type"] == "agent_status"
    assert sse_events[0]["status"] == "started"
    assert sse_events[0]["agent_id"] == "test_tool"
    assert sse_events[0]["session_id"] == 1


def test_on_tool_end_mapping():
    """场景 2e：on_tool_end → agent_result 事件"""
    from leader import SSEStreamer
    streamer = SSEStreamer(session_id=1)
    event = {
        "event": "on_tool_end",
        "name": "test_tool",
        "data": {
            "output": "工具执行结果"
        }
    }
    sse_events = streamer.langgraph_event_to_sse(event)

    assert sse_events[0]["type"] == "agent_result"
    assert sse_events[0]["status"] == "success"
    assert sse_events[0]["content"] == "工具执行结果"
    assert sse_events[0]["tool_calls"] == ["test_tool"]
    assert sse_events[0]["session_id"] == 1


def test_unknown_event_type_mapping():
    """场景 2f：未知 event 类型不泄露内部框架事件。"""
    from leader import SSEStreamer
    streamer = SSEStreamer(session_id=1)
    event = {
        "event": "unknown_event",
        "name": "something",
        "data": {}
    }
    sse_events = streamer.langgraph_event_to_sse(event)

    assert sse_events == []


# ==================== 场景 4：向后兼容 ====================

def test_sse_event_format_compatible():
    """场景 4a：SSE 事件格式与前端兼容"""
    from leader import SSEStreamer
    streamer = SSEStreamer(session_id=1)

    # 测试各种 event 类型输出都包含必要字段
    test_events = [
        {"event": "on_chain_start", "name": "node", "data": {}},
        {"event": "on_chain_end", "name": "node", "data": {}},
        {"event": "on_tool_start", "name": "tool", "data": {}},
        {"event": "on_tool_end", "name": "tool", "data": {"output": "result"}},
    ]

    for event in test_events:
        sse_events = streamer.langgraph_event_to_sse(event)
        assert isinstance(sse_events, list)
        for sse_event in sse_events:
            assert "type" in sse_event
            assert "session_id" in sse_event


def test_sse_events_from_state_compatible():
    """场景 4b：从 state 提取的事件格式兼容"""
    from leader import SSEStreamer
    streamer = SSEStreamer(session_id=1)
    state = {
        "sse_events": [
            {"type": "leader_thinking", "phase": "test", "content": "思考中"},
            {"type": "final_report", "report": "报告内容"}
        ]
    }

    events = list(streamer.yield_sse_from_state(state))

    for event in events:
        assert "type" in event
        assert "session_id" in event


# ==================== 场景 5：SSE Streamer 独立导入 ====================

def test_sse_streamer_import_independent():
    """场景 5a：SSEStreamer 可独立导入，不依赖应用上下文"""
    from leader import SSEStreamer

    assert SSEStreamer is not None


# ==================== 场景 6：异常处理 ====================

def test_stream_graph_events_handles_exception():
    """场景 6a：LangGraph streaming 异常时输出 error 事件"""
    from leader import SSEStreamer
    streamer = SSEStreamer(session_id=1)

    # Mock graph 抛出异常
    mock_graph = Mock()
    mock_graph.astream_events = Mock(side_effect=Exception("测试异常"))

    events = list(streamer.stream_graph_events(mock_graph, {}))

    # 应该有 error 事件
    assert len(events) > 0
    error_events = [e for e in events if e.get("type") == "error"]
    assert len(error_events) > 0
    # 客户端只能收到通用文案，原始异常仅记录在服务端日志中。
    assert error_events[0]["message"] == "处理请求时发生内部错误，请稍后重试"
    assert "测试异常" not in error_events[0]["message"]


def test_langgraph_event_to_sse_handles_missing_fields():
    """场景 6b：event 字段缺失时不抛异常"""
    from leader import SSEStreamer
    streamer = SSEStreamer(session_id=1)

    # 不完整 event
    incomplete_events = [
        {},  # 空
        {"event": "on_chain_start"},  # 缺 name
        {"name": "test"},  # 缺 event
    ]

    for event in incomplete_events:
        sse_events = streamer.langgraph_event_to_sse(event)
        assert isinstance(sse_events, list)


# ==================== 辅助测试 ====================

def test_extract_agent_id_from_data():
    """场景 6c：从 data 提取 agent_id"""
    from leader import SSEStreamer
    streamer = SSEStreamer(session_id=1)

    agent_id = streamer._extract_agent_id("tool_name", {"agent_id": "agent_123"})

    assert agent_id == "agent_123"


def test_extract_agent_id_fallback_to_name():
    """场景 6d：agent_id 缺失时用 name"""
    from leader import SSEStreamer
    streamer = SSEStreamer(session_id=1)

    agent_id = streamer._extract_agent_id("tool_name", {})

    assert agent_id == "tool_name"


def test_extract_agent_id_empty_name():
    """场景 6e：name 空时返回 unknown"""
    from leader import SSEStreamer
    streamer = SSEStreamer(session_id=1)

    agent_id = streamer._extract_agent_id("", {})

    assert agent_id == "unknown"
