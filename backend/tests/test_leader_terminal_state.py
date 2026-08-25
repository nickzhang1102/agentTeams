from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import OperationalError

from leader.langgraph_entry import async_continue_leader_workflow
from leader.langgraph_entry import ensure_terminal_state_sync


def test_terminal_state_fallback_skips_active_background_task():
    """断连后台任务仍在运行时，不应把 session 立即标记 failed。"""
    db_mock = MagicMock()
    db_mock.session.execute.return_value.fetchone.return_value = ("summarizing",)

    with patch("db.db", db_mock), \
         patch("leader.sse_streamer.is_background_task_running", return_value=True), \
         patch("leader.leader_persistence.is_session_stop_requested", return_value=False), \
         patch("leader.leader_persistence.mark_session_failed") as mark_failed:
        ensure_terminal_state_sync(123, skip_if_background=True)

    mark_failed.assert_not_called()
    db_mock.remove.assert_called_once()


def test_terminal_state_fallback_marks_non_terminal_without_background_task():
    """没有后台任务保护时，非终态仍按兜底规则标记 failed。"""
    db_mock = MagicMock()
    db_mock.session.execute.return_value.fetchone.return_value = ("summarizing",)

    with patch("db.db", db_mock), \
         patch("leader.sse_streamer.is_background_task_running", return_value=False), \
         patch("leader.leader_persistence.is_session_stop_requested", return_value=False), \
         patch("leader.leader_persistence.mark_session_failed") as mark_failed:
        ensure_terminal_state_sync(123, skip_if_background=True)

    mark_failed.assert_called_once_with(db_mock, 123, "工作流未正常完成（终态兜底）")
    db_mock.remove.assert_called_once()


@pytest.mark.asyncio
async def test_continue_workflow_rejects_terminal_session():
    """已完成/失败/停止的 session 不应被 answer-questions 恢复重跑。"""
    db_mock = MagicMock()
    session = MagicMock()
    session.state = "completed"
    session.locale = "zh-CN"
    db_mock.get.return_value = session

    with patch("db.db", db_mock):
        events = [
            event
            async for event in async_continue_leader_workflow(
                session_id=123,
                answers=["answer"],
                config={},
                user_id=1,
            )
        ]

    assert events == [{
        "type": "error",
        "message_key": "leader.error.session_finished",
        "message_params": {},
        "message": "会话已结束，不能继续提交答案",
    }]
    assert db_mock.session.execute.call_count == 1
    db_mock.session.rollback.assert_called_once()
    db_mock.session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_continue_workflow_lock_error_uses_session_locale():
    db_mock = MagicMock()
    session = MagicMock(state="questioning", locale="en-US")
    db_mock.get.return_value = session
    db_mock.session.execute.side_effect = OperationalError("lock", {}, Exception("busy"))

    with patch("db.db", db_mock):
        events = [
            event
            async for event in async_continue_leader_workflow(
                session_id=123,
                answers=["answer"],
                config={},
                user_id=1,
            )
        ]

    assert events == [{
        "type": "error",
        "message_key": "leader.error.already_running",
        "message_params": {},
        "message": "This session is already running. Do not submit it again.",
    }]
    db_mock.session.rollback.assert_called_once()
