"""
Execution Nodes

Agent 执行相关节点：agent_execution_node, _check_stop_flag。
从 workflow_nodes.py 提取（2026-06-18 workflow-nodes-split-round2 #D）。
"""
import logging
import time
from typing import Dict, List

from context.context_builder import ContextBuilder

from .workflow_state import LeaderWorkflowState
from .node_services import get_services
from .leader_events import _emit, build_fixed_sse_message
from .leader_persistence import _persist_agent_results

logger = logging.getLogger(__name__)


def _log_tool_call(
    agent_id: str,
    tool_name: str,
    tool_input,
    tool_output,
    status: str,
    execution_time: float,
    conversation_id: int,
    session_id: int,
    error_message: str = None,
) -> None:
    """持久化工具调用日志到数据库"""
    try:
        from db import get_db_session
        from models import ToolCallLog
        db_session = get_db_session()
        try:
            log = ToolCallLog(
                conversation_id=conversation_id,
                leader_session_id=session_id,
                agent_id=agent_id,
                tool_name=tool_name,
                tool_input=tool_input if isinstance(tool_input, dict) else {"raw": str(tool_input)} if tool_input else None,
                tool_output={"raw": str(tool_output)[:2000]} if tool_output else None,  # 截断大输出
                status=status,
                execution_time=round(execution_time, 3),
                error_message=error_message,
            )
            db_session.add(log)
            db_session.commit()
        finally:
            db_session.close()
    except Exception:
        logger.warning("Failed to persist tool call log", exc_info=True)


def _on_agent_event(
    event_data: Dict,
    state: LeaderWorkflowState,
    session_id: int,
    event_queue: List[Dict],
    tool_start_times: Dict[str, float],
) -> None:
    """工具调用事件回调（实时推送 + 持久化）

    从 agent_execution_node 中提取的独立函数，替代原 event_callback 闭包。
    """
    event_type = event_data.get("type", "tool_call")
    agent_id = event_data.get("agent_id")
    tool_name = event_data.get("tool_name")

    # 追踪工具调用开始时间
    if event_type == "tool_call_started" and agent_id and tool_name:
        key = f"{agent_id}:{tool_name}:{len([k for k in tool_start_times if k.startswith(f'{agent_id}:{tool_name}:')])}"
        tool_start_times[key] = time.time()

    # 工具调用完成时记录日志
    if event_type == "tool_call_completed" and agent_id and tool_name:
        # 找到对应的开始时间
        matching_keys = [k for k in tool_start_times if k.startswith(f"{agent_id}:{tool_name}:")]
        if matching_keys:
            start_key = matching_keys[-1]  # 取最后一个匹配的
            start_time = tool_start_times.pop(start_key, None)
            elapsed = time.time() - start_time if start_time else 0.0
        else:
            elapsed = 0.0

        is_error = event_data.get("is_error", False)
        _log_tool_call(
            agent_id=agent_id,
            tool_name=tool_name,
            tool_input=event_data.get("tool_input"),
            tool_output=event_data.get("tool_output_summary"),
            status="failed" if is_error else "success",
            execution_time=elapsed,
            conversation_id=state.get("conversation_id"),
            session_id=session_id,
            error_message=str(event_data.get("tool_output_summary"))[:500] if is_error else None,
        )

    event_queue.append({
        "type": event_type,
        "session_id": session_id,
        "agent_id": agent_id,
        "agent_name": event_data.get("agent_name"),
        "tool_name": tool_name,
        "tool_input": event_data.get("tool_input"),
        "tool_output_summary": event_data.get("tool_output_summary")
    })


def agent_execution_node(state: LeaderWorkflowState) -> Dict:
    """
    Agent 执行节点（含批次顺序）

    按 execution_batches 顺序执行 Agent：
    - 批次内：ThreadPoolExecutor 并行执行
    - 批次间：循环顺序执行
    - 每批次前检查 stop_requested

    Args:
        state: 当前状态（含 dag_execution_plan, history, stop_requested）

    Returns:
        状态更新字典：
        - agent_results: List[Dict]（追加结果）
        - total_tokens: int（累加）
        - current_batch_index: int
        - sse_events: List[Dict]
    """
    from .batch_executor import BatchExecutor

    # 获取当前状态
    svc = get_services()
    session_id = state.get("session_id")
    existing_events = state.get("sse_events", [])
    generation_locale = state.get("locale", "zh-CN")

    # DB/持久取消标记必须在任何阶段写入或 Agent 调用之前检查。
    if _check_stop_flag(state):
        from .node_services import stop_workflow
        return {
            "current_phase": "execution_stopped",
            "sse_events": existing_events + [stop_workflow(state)],
        }

    if svc.db_session is not None and session_id:
        from services.decision_run_service import DecisionRunService
        DecisionRunService(svc.db_session).set_stage(session_id, 'execution')
        svc.db_session.commit()
    dag_plan = state.get("dag_execution_plan", {})
    user_message = state.get("user_message", "")
    history = state.get("history", [])
    existing_results = state.get("agent_results", [])

    # 恢复执行时清除 action 标志（已路由完成，后续正常执行）
    if state.get("skip_to_execution"):
        logger.info("agent_execution_node: skip_to_execution mode, clearing flag")

    # 构建事件队列（用于实时推送）和工具调用时间追踪
    event_queue = []
    tool_start_times: Dict[str, float] = {}  # key: "{agent_id}:{tool_name}:{index}"
    conversation_id = state.get("conversation_id")

    # 发送执行开始事件
    batches = dag_plan.get("execution_batches", [])
    total_batches = len(batches)
    total_agents = sum(len(b.get("agents", [])) for b in batches)

    fixed_message = build_fixed_sse_message(
        generation_locale,
        "leader.phase.execution_starting",
        {"agent_count": total_agents, "batch_count": total_batches},
    )
    event_queue.append({
        "type": "execution_status",
        "session_id": session_id,
        "phase": "starting",
        "content": fixed_message["message"],
        **fixed_message,
    })

    # 初始化 BatchExecutor
    # 使用 NodeServices 中的服务
    if svc.harness_coordinator is None:
        logger.warning("HarnessCoordinator not initialized, returning empty results")
        # 返回完整的空结果状态，让后续节点能正常处理
        fixed_message = build_fixed_sse_message(
            generation_locale,
            "leader.execution.unavailable",
        )
        return {
            "agent_results": [],  # 空结果，后续节点会跳过
            "total_tokens": 0,
            "current_phase": "execution_skipped",
            "sse_events": existing_events + [{
                "type": "execution_stopped",
                "session_id": session_id,
                "reason": fixed_message["message"],
                **fixed_message,
            }]
        }

    stop_checker = lambda: _check_stop_flag(state)

    # 获取 tool_registry（优先 NodeServices，fallback 到 harness_coordinator 缓存或创建默认）
    tool_registry = svc.tool_registry
    if tool_registry is None and svc.harness_coordinator:
        tool_registry = svc.harness_coordinator._cached_full_registry
    if tool_registry is None:
        # 创建默认 registry（首次执行时）
        from services.harness.harness_adapter import HarnessToolRegistry
        try:
            from config import Config
            workspace_dir = Config.WORKSPACE_DIR
        except Exception:
            workspace_dir = 'data/workspace'
        default_registry = HarnessToolRegistry(workspace_dir=workspace_dir)
        tool_registry = default_registry  # 使用 HarnessToolRegistry 实例（有 execute_tool 方法）
        logger.info(f"Created default HarnessToolRegistry for session {session_id}")

    executor = BatchExecutor(
        harness_coordinator=svc.harness_coordinator,
        max_parallel=svc.max_parallel,
        stop_checker=stop_checker,
        llm_service=svc.llm_service,
        tool_registry=tool_registry,
        system_prompt_addition=state.get("system_prompt_addition"),
        locale=state.get("locale", "zh-CN"),
    )

    # 构建上下文包（替代 task=user_message 直接透传）
    # 检索用户长期记忆
    user_memory: list[str] = []
    user_id = state.get("user_id")
    if user_id:
        try:
            from services.memory_service import MemoryService
            memory_svc = MemoryService(db_session=svc.db_session)
            user_memory = memory_svc.get_for_context(
                user_id=user_id, query=user_message
            )
            if user_memory:
                logger.info(f"Loaded {len(user_memory)} memories for user {user_id}")
        except Exception:
            logger.warning("Failed to load user memories, continuing without", exc_info=True)

    # 知识图谱已改为 Agent 按需搜索工具（knowledge_search），不再全局注入
    shared_evidence = list(state.get("shared_evidence") or [])

    pack = ContextBuilder.build_for_agents(
        user_message=user_message,
        shared_evidence=shared_evidence or None,
        working_memory=history or None,
        user_memory=user_memory or None,
        qa_pairs=state.get("qa_history") or None,
    )

    # 执行 DAG 计划（启用任务编排模式）
    try:
        results = executor.execute_plan(
            plan=dag_plan,
            task=pack.to_task_string(),
            history=history,
            event_callback=lambda e: _on_agent_event(e, state, session_id, event_queue, tool_start_times),
            session_id=session_id,
            use_task_orchestration=True,  # 启用任务自主拆解与编排
            user_id=user_id,
            initial_results=existing_results,
            result_callback=lambda result: _persist_agent_results(
                db_session=svc.db_session,
                conversation_id=conversation_id,
                session_id=session_id,
                results=[result],
            ),
        )

        # Callback persistence gives per-Agent recovery boundaries. Keep one
        # idempotent batch flush as a fallback if an individual callback was
        # temporarily unable to persist.
        _persist_agent_results(
            db_session=svc.db_session,
            conversation_id=conversation_id,
            session_id=session_id,
            results=results,
        )

        merged_results = existing_results + results
        total_tokens = sum(r.get("tokens_used", 0) for r in merged_results)

        # agent_result / agent_error 已由 BatchExecutor 通过 push_sse_event 实时推送，
        # 此处不再重复追加到 event_queue，避免前端收到重复事件。

        # 发送执行完成事件
        success_count = len([r for r in merged_results if r.get("success")])
        stopped = any(r.get("status") == "stopped" for r in results)
        if stopped or (stop_checker and stop_checker()):
            from .node_services import stop_workflow
            event_queue.append(stop_workflow(state))
            return {
                "agent_results": existing_results + results,
                "total_tokens": total_tokens,
                "current_phase": "execution_stopped",
                "sse_events": existing_events + event_queue
            }

        fixed_message = build_fixed_sse_message(
            generation_locale,
            "leader.phase.execution_complete",
            {"successful": success_count, "total": total_agents},
        )
        event_queue.append({
            "type": "execution_complete",
            "session_id": session_id,
            "content": fixed_message["message"],
            **fixed_message,
        })

        return {
            "agent_results": merged_results,
            "total_tokens": total_tokens,
            "current_phase": "execution_complete",
            "sse_events": existing_events + event_queue
        }

    except Exception as e:
        logger.error(f"Agent execution failed: {e}", exc_info=True)
        raise RuntimeError(f"Agent 执行失败: {str(e)}") from e


def _check_stop_flag(state: LeaderWorkflowState) -> bool:
    """检查停止标志（用于 BatchExecutor stop_checker）

    统一委托 node_services.should_stop_workflow：先查内存标志，再查 DB stop_requested，
    与需求 / 组建 / 汇总各阶段共用同一判定。state 为冻结快照，不修改，仅返回布尔值。
    """
    from .node_services import should_stop_workflow
    return should_stop_workflow(state)


def _mark_session_stopped(session_id: int) -> None:
    if not session_id:
        return
    try:
        svc = get_services()
        db = svc.db_session
        if db is None:
            return
        from .leader_persistence import mark_session_stopped
        mark_session_stopped(db, session_id)
    except Exception as e:
        logger.error(f"Failed to mark session stopped: {e}", exc_info=True)
