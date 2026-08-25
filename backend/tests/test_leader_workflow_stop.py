"""
Leader 工作流停止链路单元测试

覆盖（对应 issue 2036 Leader 工作流可及时停止）：
1. should_stop_workflow：内存标志 / DB stop_requested 的严格 `is True` 判定
2. summarize_node：停止时跳过 LLM 报告生成，发送 execution_stopped（省 token）
3. requirement_loop_node：停止时跳过需求评估
4. route_after_requirement：execution_stopped 阶段路由到 "end"
5. team_form_dag_node：停止时跳过团队组建
6. _persist_final_report：session 缺失时优雅降级（return None，不抛异常）
7. mark_session_failed：StaleDataError 时安全回滚跳过，不二次异常
"""
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch
from sqlalchemy.orm.exc import StaleDataError

from leader.node_services import NodeServices, set_services, should_stop_workflow
from leader.workflow_state import LeaderWorkflowState
from leader.workflow_nodes import (
    summarize_node,
    requirement_loop_node,
    route_after_requirement,
    team_form_dag_node,
)
from leader.langgraph_workflow import route_after_team_form
from leader.leader_persistence import _persist_final_report, mark_session_failed


def _inject_services(**overrides) -> NodeServices:
    """创建 NodeServices 并注入 ContextVar（测试辅助）"""
    svc = NodeServices(**overrides)
    set_services(svc)
    return svc


def _base_state(**overrides) -> LeaderWorkflowState:
    """构造最小 LeaderWorkflowState（TypedDict，字段非强制）"""
    state = LeaderWorkflowState(
        conversation_id=1,
        user_message="测试问题",
        history=[],
        stop_requested=False,
        session_id=100,
        current_phase="execution_complete",
        sse_events=[],
    )
    state.update(overrides)
    return state


class TestShouldStopWorkflow:
    """should_stop_workflow 判定"""

    def test_memory_flag_true_returns_true(self):
        """内存标志 stop_requested=True 直接返回 True"""
        state = _base_state(stop_requested=True)
        assert should_stop_workflow(state) is True

    def test_memory_flag_false_and_no_db_returns_false(self):
        """内存标志为 False 且无 DB 会话时返回 False"""
        _inject_services(db_session=None)
        state = _base_state(stop_requested=False)
        assert should_stop_workflow(state) is False

    def test_db_flag_true_returns_true(self):
        """DB 中 LeaderSession.stop_requested 为 True 返回 True"""
        magic_db = MagicMock()
        magic_session = MagicMock()
        magic_session.stop_requested = True
        magic_db.get.side_effect = [None, magic_session]
        _inject_services(db_session=magic_db)
        state = _base_state(stop_requested=False, session_id=100)
        assert should_stop_workflow(state) is True

    def test_db_flag_nontruthy_object_returns_false(self):
        """DB 标志为其它 truthy 对象（非 True）不被误判为已停止"""
        magic_db = MagicMock()
        magic_session = MagicMock()
        magic_session.stop_requested = "some-string"  # truthy 但非 True
        magic_db.get.side_effect = [None, magic_session]
        _inject_services(db_session=magic_db)
        state = _base_state(stop_requested=False, session_id=100)
        assert should_stop_workflow(state) is False

    def test_no_session_id_returns_false(self):
        """无 session_id 时不查 DB，返回 False"""
        _inject_services(db_session=MagicMock())
        state = _base_state(stop_requested=False, session_id=None)
        assert should_stop_workflow(state) is False


class TestSummarizeNodeStop:
    """summarize_node 停止分支"""

    def test_stop_skips_llm_and_emits_execution_stopped(self):
        """停止时跳过 LLM 报告生成，输出明确的停止事件"""
        svc = _inject_services(
            llm_service=MagicMock(),
            db_session=None,
        )
        state = _base_state()
        with patch("leader.summarize_nodes.should_stop_workflow", return_value=True):
            result = summarize_node(state)

        # 不消耗 LLM（省 token）
        svc.llm_service.call_sync.assert_not_called()
        svc.llm_service.call_structured.assert_not_called()

        # 停止语义
        assert result["quality_status"] == "stopped"
        assert result["current_phase"] == "execution_stopped"

        # SSE 停止反馈事件
        last_event = result["sse_events"][-1]
        assert last_event["type"] == "execution_stopped"
        assert last_event["message_key"] == "leader.execution.stopped"

    def test_stop_marks_session_stopped_in_db(self):
        """停止分支将运行中的 session 标记为 stopped（避免停留在 summarizing）"""
        magic_db = MagicMock()
        running_session = MagicMock()
        running_session.state = "summarizing"
        running_session.started_at = None
        magic_db.query.return_value.filter.return_value.with_for_update.return_value.populate_existing.return_value.first.return_value = running_session
        magic_db.get.return_value = None
        _inject_services(llm_service=MagicMock(), db_session=magic_db)

        state = _base_state(session_id=100)
        with patch("leader.summarize_nodes.should_stop_workflow", return_value=True), \
             patch("leader.leader_persistence.request_session_stop"), \
             patch("services.decision_run_service.DecisionRunService"):
            result = summarize_node(state)

        assert running_session.state == "stopped"
        assert result["quality_status"] == "stopped"
        magic_db.commit.assert_called()

    def test_stop_arriving_during_summary_discards_late_report(self):
        """汇总 LLM 返回前收到停止请求时，不持久化或发布迟到报告。"""
        llm_service = MagicMock()
        llm_service.get_max_output_tokens.return_value = 32768
        _inject_services(llm_service=llm_service, db_session=None)
        state = _base_state(
            agent_results=[{
                "agent_id": "agent-1",
                "agent_name": "专家1",
                "content": "分析结果",
                "success": True,
            }],
        )
        stopped_event = {
            "type": "execution_stopped",
            "session_id": 100,
            "message": "已停止",
        }

        with patch(
            "leader.summarize_nodes.should_stop_workflow",
            side_effect=[False, True],
        ), patch(
            "leader.summarize_nodes._call_llm_for_summary",
            return_value=("# 迟到报告", None, None),
        ) as llm_call, patch(
            "leader.summarize_nodes.stop_workflow",
            return_value=stopped_event,
        ), patch(
            "leader.summarize_nodes._persist_final_report",
        ) as persist_report:
            result = summarize_node(state)

        llm_call.assert_called_once()
        persist_report.assert_not_called()
        assert result["current_phase"] == "execution_stopped"
        assert result["quality_status"] == "stopped"
        assert result["sse_events"][-1] == stopped_event
        assert not any(event.get("type") == "final_report" for event in result["sse_events"])

    @pytest.mark.parametrize(
        "agent_results",
        [
            [],
            [{
                "agent_id": "agent-1",
                "agent_name": "专家1",
                "content": "执行失败",
                "success": False,
            }],
        ],
        ids=["no-results", "all-results-failed"],
    )
    def test_stop_wins_before_degraded_report_is_published(self, agent_results):
        """降级报告持久化被停止裁决后，不再向客户端发布 final_report。"""
        magic_db = MagicMock()
        _inject_services(llm_service=MagicMock(), db_session=magic_db)
        state = _base_state(agent_results=agent_results)
        stopped_event = {
            "type": "execution_stopped",
            "session_id": 100,
            "message": "已停止",
        }

        with patch(
            "leader.summarize_nodes.should_stop_workflow",
            side_effect=[False, True],
        ), patch(
            "leader.summarize_nodes._persist_final_report",
            return_value=None,
        ) as persist_report, patch(
            "leader.summarize_nodes.stop_workflow",
            return_value=stopped_event,
        ), patch(
            "leader.summarize_nodes._calculate_session_total_time",
            return_value=0.1,
        ), patch("services.decision_run_service.DecisionRunService"):
            result = summarize_node(state)

        persist_report.assert_called_once()
        assert result["current_phase"] == "execution_stopped"
        assert result["quality_status"] == "stopped"
        assert result["sse_events"][-1] == stopped_event
        assert not any(event.get("type") == "final_report" for event in result["sse_events"])


class TestRequirementLoopNodeStop:
    """requirement_loop_node 停止分支"""

    def test_stop_skips_assessment(self):
        """停止时跳过需求评估，直接进入 execution_stopped"""
        state = _base_state()
        with patch("leader.node_services.should_stop_workflow", return_value=True), \
             patch("leader.node_services.stop_workflow", return_value={"type": "execution_stopped"}):
            result = requirement_loop_node(state)
        assert result["current_phase"] == "execution_stopped"
        assert result["requirement_passed"] is False


class TestTeamFormNodeStop:
    """team_form_dag_node 停止分支"""

    def test_stop_skips_team_forming(self):
        """停止时跳过团队组建，直接进入 execution_stopped"""
        state = _base_state()
        with patch("leader.node_services.should_stop_workflow", return_value=True), \
             patch("leader.node_services.stop_workflow", return_value={"type": "execution_stopped"}):
            result = team_form_dag_node(state)
        assert result["current_phase"] == "execution_stopped"

    def test_stopped_team_form_routes_directly_to_end(self):
        state = _base_state(current_phase="execution_stopped")
        assert route_after_team_form(state) == "end"

    def test_completed_team_form_routes_to_agent_execution(self):
        state = _base_state(current_phase="team_form_dag")
        assert route_after_team_form(state) == "agent_execution"


class TestRouteAfterRequirementStop:
    """route_after_requirement 停止路由"""

    def test_stopped_phase_routes_to_end(self):
        """execution_stopped 阶段路由到 end，结束工作流"""
        state = _base_state(current_phase="execution_stopped", requirement_passed=False)
        assert route_after_requirement(state) == "end"


class TestPersistenceGracefulDegradation:
    """会话删除后的持久化优雅降级"""

    def test_persist_final_report_session_missing_returns_none(self):
        """session 不存在时 _persist_final_report 优雅降级返回 None，不抛异常"""
        magic_db = MagicMock()
        # 不存在既有报告 → 走新建分支 → 再因 session 缺失优雅降级
        magic_db.query.return_value.filter_by.return_value.first.return_value = None
        magic_db.get.return_value = None
        with patch("services.decision_evidence_service.DecisionEvidenceService") as m_ev:
            m_ev.return_value.persist_for_session.return_value = None
            result = _persist_final_report(
                db_session=magic_db,
                session_id=999,
                report="## 综合建议",
                completed_at=datetime.now(),
                content_locale="zh-CN",
                state={},
                quality_status="passed",
            )
        assert result is None

    def test_mark_session_failed_stale_data_error_is_safe(self):
        """commit 命中 StaleDataError 时回滚并安全跳过，不二次异常"""
        magic_db = MagicMock()
        magic_session = MagicMock()
        magic_session.conversation_id = 5
        magic_db.get.return_value = magic_session
        magic_db.commit.side_effect = StaleDataError()

        with patch("leader.leader_persistence.is_session_stop_requested", return_value=False), \
             patch("services.decision_run_service.DecisionRunService"):
            mark_session_failed(magic_db, 1, "boom")

        magic_db.rollback.assert_called_once()
