from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from leader.execution_nodes import agent_execution_node
from leader.langgraph_entry import async_run_leader_workflow
from leader.node_services import NodeServices, set_services


def test_agent_execution_node_raises_on_executor_exception():
    """执行节点自身异常应向外抛出，由 workflow 入口标记 failed。"""
    harness = MagicMock()
    harness._cached_full_registry = MagicMock()
    set_services(NodeServices(harness_coordinator=harness, max_parallel=1))

    state = {
        "conversation_id": 1,
        "session_id": 123,
        "user_message": "测试任务",
        "history": [],
        "shared_evidence": [],
        "qa_history": [],
        "dag_execution_plan": {
            "execution_batches": [{"priority": 50, "agents": ["agent-1"]}]
        },
        "agent_results": [],
        "stop_requested": False,
        "sse_events": [],
    }

    with patch(
        "leader.batch_executor.BatchExecutor.execute_plan",
        side_effect=RuntimeError("executor boom"),
    ):
        with pytest.raises(RuntimeError, match="Agent 执行失败: executor boom"):
            agent_execution_node(state)


@pytest.mark.asyncio
async def test_workflow_graph_failure_marks_failed_without_done():
    """图执行异常时入口必须收敛为 failed 终态，且不再发出 done 事件。"""

    class FailingGraph:
        async def astream_events(self, _state, version):
            if False:
                yield None
            raise RuntimeError("graph boom")

    session = MagicMock(id=321)

    with patch("leader.langgraph_entry.create_leader_session", return_value=session), \
         patch("leader.langgraph_entry._initialize_services", new=AsyncMock()), \
         patch("leader.langgraph_entry.create_leader_workflow_graph", return_value=FailingGraph()), \
         patch("leader.langgraph_entry.is_session_stop_requested", return_value=False), \
         patch("leader.langgraph_entry.mark_session_failed") as mark_failed, \
         patch("leader.langgraph_entry.ensure_terminal_state_sync"), \
         patch("leader.langgraph_entry.DecisionRunService") as decision_run_service:
        events = [
            event
            async for event in async_run_leader_workflow(
                conversation_id=1,
                message="test",
                history=[],
                config={},
            )
        ]

    assert [event["type"] for event in events] == ["error"]
    decision_run_service.return_value.mark_started.assert_called_once_with(321, stage="assessment")
    mark_failed.assert_called_once()


@pytest.mark.asyncio
async def test_stopped_workflow_emits_stop_without_done():
    """停止路径只发出 execution_stopped，不产生 done 事件。"""

    class StoppedGraph:
        async def astream_events(self, _state, version):
            yield {
                "event": "on_chain_end",
                "name": "requirement_loop",
                "data": {
                    "output": {
                        "sse_events": [{
                            "type": "execution_stopped",
                            "session_id": 322,
                        }]
                    }
                },
            }

    session = MagicMock(id=322)

    with patch("leader.langgraph_entry.create_leader_session", return_value=session), \
         patch("leader.langgraph_entry._initialize_services", new=AsyncMock()), \
         patch("leader.langgraph_entry.create_leader_workflow_graph", return_value=StoppedGraph()), \
         patch("leader.langgraph_entry.is_session_stop_requested", return_value=True), \
         patch("leader.langgraph_entry.ensure_terminal_state_sync"), \
         patch("leader.langgraph_entry.DecisionRunService") as decision_run_service:
        events = [
            event
            async for event in async_run_leader_workflow(
                conversation_id=1,
                message="test",
                history=[],
                config={},
            )
        ]

    assert [event["type"] for event in events] == ["execution_stopped"]
