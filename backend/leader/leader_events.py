"""
Leader Events

SSE 事件推送函数和事件工厂。从 workflow_nodes.py 提取
（2026-06-18 workflow-nodes-split refactor）。

_emit 是核心推送函数；make_* 工厂函数供后续 #D 重构替换节点内手写事件字典。
"""
from typing import Dict, Any, Optional, List

from .sse_streamer import push_sse_event


_FIXED_SSE_MESSAGES = {
    "leader.phase.waiting_answers": {
        "zh-CN": "等待用户回答问题...",
        "en-US": "Waiting for your answers...",
    },
    "leader.phase.forming_team": {
        "zh-CN": "正在组建专家团队...",
        "en-US": "Forming the expert team...",
    },
    "leader.phase.forming_preset_team": {
        "zh-CN": "正在从预选 Agent 构建团队...",
        "en-US": "Building the team from preselected agents...",
    },
    "leader.phase.execution_starting": {
        "zh-CN": "启动 {agent_count} 个 Agent 执行，共 {batch_count} 个批次...",
        "en-US": "Starting {agent_count} agents across {batch_count} batches...",
    },
    "leader.execution.stopped": {
        "zh-CN": "用户请求停止执行",
        "en-US": "Execution stopped at the user's request",
    },
    "leader.execution.unavailable": {
        "zh-CN": "OpenHarness 未启用或未初始化，跳过 Agent 执行",
        "en-US": "OpenHarness is unavailable or not initialized; skipping agent execution",
    },
    "leader.phase.execution_complete": {
        "zh-CN": "执行完成：{successful}/{total} 成功",
        "en-US": "Execution complete: {successful}/{total} succeeded",
    },
    "leader.phase.summarizing": {
        "zh-CN": "正在汇总所有专家意见...",
        "en-US": "Summarizing all expert findings...",
    },
    "leader.phase.resuming": {
        "zh-CN": "正在恢复工作流...",
        "en-US": "Resuming the workflow...",
    },
    "leader.phase.reassessing": {
        "zh-CN": "正在根据用户补充信息重新评估需求...",
        "en-US": "Reassessing the request using your additional information...",
    },
    "leader.error.already_running": {
        "zh-CN": "会话正在执行中，请勿重复提交",
        "en-US": "This session is already running. Do not submit it again.",
    },
    "leader.error.session_not_found": {
        "zh-CN": "未找到会话",
        "en-US": "Session not found",
    },
    "leader.error.session_finished": {
        "zh-CN": "会话已结束，不能继续提交答案",
        "en-US": "This session has finished and cannot accept more answers.",
    },
    "leader.error.session_lock_failed": {
        "zh-CN": "会话状态锁定失败，请重试",
        "en-US": "Failed to lock the session state. Please try again.",
    },
    "leader.status.done": {
        "zh-CN": "工作流已完成",
        "en-US": "Workflow completed",
    },
}


def build_fixed_sse_message(
    locale: str,
    message_key: str,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """构建固定 SSE 文案的稳定 key、参数和本地化 fallback。"""
    message_params = dict(params or {})
    resolved_locale = "en-US" if locale == "en-US" else "zh-CN"
    message = _FIXED_SSE_MESSAGES[message_key][resolved_locale].format(**message_params)
    return {
        "message_key": message_key,
        "message_params": message_params,
        "message": message,
    }


def _emit(session_id: int, event: Dict) -> None:
    """实时推送 SSE 事件（节点执行期间立即发出）"""
    if session_id:
        push_sse_event(session_id, event)


# ==================== 事件工厂函数（供 #D 重构使用） ====================

def make_leader_thinking_event(session_id: int, phase: str, content: str) -> Dict:
    """构建 leader_thinking 事件"""
    return {"type": "leader_thinking", "session_id": session_id, "phase": phase, "content": content}


def make_assessment_result_event(
    session_id: int, score: int, details: Dict, passed: bool, risk_level: str
) -> Dict:
    """构建 assessment_result 事件"""
    return {
        "type": "assessment_result",
        "session_id": session_id,
        "score": score,
        "details": details,
        "passed": passed,
        "risk_level": risk_level,
    }


def make_team_forming_event(
    session_id: int, phase: str, content: str, selected_agents: Optional[List] = None
) -> Dict:
    """构建 team_forming 事件"""
    event: Dict[str, Any] = {
        "type": "team_forming",
        "session_id": session_id,
        "phase": phase,
        "content": content,
    }
    if selected_agents is not None:
        event["selected_agents"] = selected_agents
    return event


def make_team_ready_event(session_id: int, team_data: Dict) -> Dict:
    """构建 team_ready 事件"""
    return {"type": "team_ready", "session_id": session_id, "team": team_data}


def make_leader_question_event(session_id: int, questions: List) -> Dict:
    """构建 leader_question 事件"""
    return {"type": "leader_question", "session_id": session_id, "questions": questions}


def make_execution_status_event(session_id: int, phase: str, content: str) -> Dict:
    """构建 execution_status 事件"""
    return {"type": "execution_status", "session_id": session_id, "phase": phase, "content": content}


def make_agent_result_event(session_id: int, result: Dict) -> Dict:
    """构建 agent_result 事件"""
    return {
        "type": "agent_result",
        "session_id": session_id,
        "agent_id": result.get("agent_id"),
        "agent_name": result.get("agent_name"),
        "content": result.get("content"),
        "content_locale": result.get("content_locale"),
        "summary": result.get("summary"),
        "structured_report": result.get("structured_report"),
        "status": "success",
        "tool_calls": result.get("tool_calls", []),
        "tokens_used": result.get("tokens_used", 0),
        "execution_time": result.get("execution_time", 0),
    }


def make_agent_error_event(session_id: int, result: Dict) -> Dict:
    """构建 agent_error 事件"""
    return {
        "type": "agent_error",
        "session_id": session_id,
        "agent_id": result.get("agent_id"),
        "agent_name": result.get("agent_name"),
        "content": result.get("content") or result.get("error") or "Agent 执行失败",
        "error": result.get("error"),
        "status": "failed",
    }


def make_execution_complete_event(session_id: int, content: str) -> Dict:
    """构建 execution_complete 事件"""
    return {"type": "execution_complete", "session_id": session_id, "content": content}


def make_execution_stopped_event(session_id: int, locale: str = "zh-CN") -> Dict:
    """Build the single public event used for every workflow cancellation path."""
    fixed_message = build_fixed_sse_message(locale, "leader.execution.stopped")
    return {
        "type": "execution_stopped",
        "session_id": session_id,
        "reason": fixed_message["message"],
        **fixed_message,
    }


def make_final_report_event(
    session_id: int, report: str, total_time: float, report_id: Optional[int] = None
) -> Dict:
    """构建 final_report 事件"""
    event = {
        "type": "final_report",
        "session_id": session_id,
        "report": report,
        "total_time": total_time,
    }
    if report_id is not None:
        event["id"] = report_id
    return event
