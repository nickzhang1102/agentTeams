"""Leader session 终态兜底保护。

独立于工作流入口/流式模块，避免后台任务完成回调造成循环导入。
"""
import logging
from typing import Callable, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

TERMINAL_STATES = frozenset({'completed', 'stopped', 'failed'})
WAITING_STATES = frozenset({'questioning', 'idle'})


def ensure_terminal_state_sync(
    session_id: int,
    *,
    skip_if_background: bool = False,
    background_check: Optional[Callable[[int], bool]] = None,
) -> None:
    """将异常未达终态的 session 标记为 failed（幂等，可安全多次调用）。"""
    from db import db
    try:
        row = db.session.execute(
            text("SELECT state FROM leader_sessions WHERE id = :sid"),
            {"sid": session_id},
        ).fetchone()
        current_state = row[0] if row else None

        if current_state is not None:
            from .leader_persistence import is_session_stop_requested
            if is_session_stop_requested(db, session_id):
                from .leader_persistence import mark_session_stopped
                mark_session_stopped(db, session_id)
                return

        if skip_if_background:
            if background_check is None:
                from .sse_streamer import is_background_task_running
                background_check = is_background_task_running
            try:
                if background_check(session_id):
                    logger.info(
                        "[终态兜底] Session %s 仍有后台任务在运行，跳过 failed 标记",
                        session_id,
                    )
                    return
            except Exception as exc:
                logger.warning(
                    "[终态兜底] Session %s 后台任务检查失败: %s",
                    session_id,
                    exc,
                )

        if current_state is not None and current_state not in TERMINAL_STATES:
            if current_state in WAITING_STATES:
                logger.info(
                    "[终态兜底] Session %s state=%s 是合法等待状态，跳过 failed 标记",
                    session_id,
                    current_state,
                )
            else:
                from .leader_persistence import mark_session_failed
                logger.warning(
                    "[终态兜底] Session %s state=%s 不在终态，强制标记 failed",
                    session_id,
                    current_state,
                )
                mark_session_failed(db, session_id, "工作流未正常完成（终态兜底）")
    except Exception as exc:
        logger.error("[终态兜底] Session %s 检查失败: %s", session_id, exc, exc_info=True)
    finally:
        db.remove()
