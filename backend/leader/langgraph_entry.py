"""
LangGraph Workflow Entry Point

提供 LangGraph workflow 的统一入口函数（异步版）

包含：
- async_run_leader_workflow（启动新会话）
- async_continue_leader_workflow（用户回答/Agent 审核决策后恢复）
"""
import logging
from typing import Dict, List, Any, Optional, AsyncGenerator

from sqlalchemy import text

from .workflow_state import LeaderWorkflowState
from .langgraph_workflow import create_leader_workflow_graph
from .sse_streamer import SSEStreamer, is_background_task_running
from .terminal_state import ensure_terminal_state_sync, TERMINAL_STATES
from .workflow_nodes import (
    initialize_node_services,
    initialize_executor_services,
    initialize_summarize_services,
    clear_message_seq_cache
)
from .leader_persistence import (
    create_leader_session,
    mark_session_failed,
    is_session_stop_requested,
    load_agent_results,
    load_team_config,
    load_qa_history,
)
from .locale_generation import resolve_generation_locale
from .leader_events import build_fixed_sse_message, make_execution_stopped_event
from services.decision_run_service import DecisionRunService

logger = logging.getLogger(__name__)

# ==================== Async 版本（FastAPI StreamingResponse） ====================

async def async_run_leader_workflow(
    conversation_id: int,
    message: str,
    history: List[Dict],
    config: Dict,
    shared_evidence: Optional[List[str]] = None,
    user_id: Optional[int] = None,
    skip_to_execution: bool = False,
    pre_selected_agents: Optional[List[str]] = None,
    assessment_threshold: int = 60,
    system_prompt_addition: Optional[str] = None,
    locale: Optional[str] = None,
    existing_session_id: Optional[int] = None,
) -> AsyncGenerator[Dict, None]:
    """
    异步版 LangGraph workflow 入口函数（FastAPI SSE 用）

    Args:
        conversation_id: 对话 ID
        message: 用户消息
        history: 对话历史
        config: 配置字典
        shared_evidence: 共享证据列表（文件内容、搜索结果等）
        skip_to_execution: 跳过评估和团队组建，直接执行
        pre_selected_agents: 用户指定的 agent_id 列表

    Yields:
        Dict: SSE 事件
    """
    from db import db  # scoped_session
    from models import LeaderSession, Message

    # === 1. 创建或复用 LeaderSession（通过 persistence 层）===
    existing_agent_results: List[Dict] = []
    restored_selected_agents: List[Dict] = []
    restored_dag_plan: Dict = {}
    restored_qa_history: List[Dict] = []
    restored_all_asked: List[Dict] = []
    restored_requirement_loop_count = 0
    if existing_session_id is not None:
        session_id = existing_session_id
        session = db.get(LeaderSession, session_id)
        if session is None:
            raise ValueError(f"LeaderSession {session_id} not found")
        if session.locale not in ('zh-CN', 'en-US'):
            logger.error("LeaderSession %s has invalid locale %r; falling back to zh-CN", session_id, session.locale)
        generation_locale = resolve_generation_locale(session_locale=session.locale)

        # 崩溃的 worker 可能在 Leader 已到达持久化边界后仍残留过期的启动租约。
        # 应对这些状态进行协调，而不是在同一个会话上重新构建一次新的图运行。
        if session.state in TERMINAL_STATES:
            if session.state == 'completed':
                yield {
                    "type": "done",
                    "session_id": session_id,
                    **build_fixed_sse_message(generation_locale, "leader.status.done"),
                }
            elif session.state == 'stopped':
                yield make_execution_stopped_event(session_id, generation_locale)
            else:
                yield {
                    "type": "error",
                    "session_id": session_id,
                    "message": session.error_message or "Leader workflow failed",
                }
            return

        restored_requirement_loop_count = session.requirement_loop_count or 0
        recoverable_states = {
            'assessing', 'forming_team', 'web_search', 'monitoring',
            'summarizing', 'questioning', 'idle',
        }
        if session.state in recoverable_states:
            if session.state == 'questioning':
                latest_message = db.query(Message).filter(
                    Message.leader_session_id == session_id,
                    Message.sequence_number.isnot(None),
                ).order_by(Message.sequence_number.desc()).first()
                if latest_message is None or latest_message.message_type != 'answer':
                    # 等待用户是一个持久且非运行的边界。
                    # 启动 worker 只会将其状态收敛为 questioning。
                    return

            existing_agent_results = load_agent_results(db, session_id)
            team_config = load_team_config(db, session_id)
            restored_selected_agents = team_config["selected_agents"]
            restored_dag_plan = team_config["dag_plan"]
            restored_qa_history = load_qa_history(db, session_id)
            restored_all_asked = [
                {"question": pair["question"], "options": []}
                for pair in restored_qa_history
            ]
            skip_to_execution = skip_to_execution or bool(
                restored_selected_agents and restored_dag_plan
            )
    else:
        generation_locale = resolve_generation_locale(explicit_locale=locale)
        session = create_leader_session(
            db_session=db,
            conversation_id=conversation_id,
            message=message,
            assessment_threshold=assessment_threshold,
            system_prompt_addition=system_prompt_addition,
            locale=generation_locale,
        )
        session_id = session.id

    DecisionRunService(db).mark_started(
        session_id,
        stage='execution' if skip_to_execution else 'assessment',
    )
    db.commit()

    # === 2. 初始化服务依赖 ===
    await _initialize_services(config, db)

    # === 3. 初始化 Workflow State ===
    initial_state: LeaderWorkflowState = {
        "conversation_id": conversation_id,
        "session_id": session_id,
        "user_id": user_id,
        "locale": generation_locale,
        "user_message": message,
        "history": history,
        "shared_evidence": shared_evidence or [],
        "requirement_loop_count": restored_requirement_loop_count,
        "requirement_passed": False,
        "requirement_questions": [],
        "all_asked_questions": restored_all_asked,
        "qa_history": restored_qa_history,
        "user_answers": [],
        "assessment_result": {},
        "selected_agents": restored_selected_agents,
        "dag_execution_plan": restored_dag_plan,
        "agent_results": existing_agent_results,
        "current_agent_index": 0,
        "agent_retry_counts": {},
        "final_report": "",
        "stop_requested": False,
        "current_phase": "starting",
        "skip_to_execution": skip_to_execution,
        "pre_selected_agents": pre_selected_agents or [],
        "assessment_threshold": assessment_threshold,
        "system_prompt_addition": system_prompt_addition,
        "sse_events": []
    }

    # === 4. 执行 LangGraph（实时流式）===
    graph = create_leader_workflow_graph()
    streamer = SSEStreamer(session_id=session_id)
    stop_event_emitted = False

    try:
        async for event in streamer.astream_graph_events(graph, initial_state):
            if event.get("type") == "execution_stopped":
                stop_event_emitted = True
            yield event

        stopped = is_session_stop_requested(db, session_id)
        if stopped and not stop_event_emitted:
            yield make_execution_stopped_event(session_id, generation_locale)
        elif not stopped:
            yield {
                "type": "done",
                "session_id": session_id,
                **build_fixed_sse_message(generation_locale, "leader.status.done"),
            }

        logger.info(f"LangGraph workflow completed for session {session_id}")

    except Exception as e:
        logger.error(f"LangGraph workflow failed: {e}", exc_info=True)

        if is_session_stop_requested(db, session_id):
            from .leader_persistence import mark_session_stopped
            mark_session_stopped(db, session_id)
            if not stop_event_emitted:
                yield make_execution_stopped_event(session_id, generation_locale)
            return

        # 更新 session 状态
        mark_session_failed(db, session_id, str(e))

        yield {"type": "error", "session_id": session_id, "message": str(e)}

    finally:
        # 【兜底】若 session 未达终态（图中途被截断 / 新 early return 路径），强制标记 failed
        # 注：SSE 断开后，后台任务可能仍在运行，终态检查会延迟到任务完成回调中执行
        ensure_terminal_state_sync(
            session_id,
            skip_if_background=True,
            background_check=is_background_task_running,
        )


async def async_continue_leader_workflow(
    session_id: int,
    answers: List[str],
    config: Dict,
    skip_to_execution: bool = False,
    user_id: Optional[int] = None,
) -> AsyncGenerator[Dict, None]:
    """
    异步版继续 Leader workflow（FastAPI SSE 用）

    两种恢复模式：
    1. 用户回答问题后恢复（skip_to_execution=False）：从需求评估重新开始
    2. Agent 审核决策后恢复（skip_to_execution=True）：跳过需求评估和团队组建，直接进入 Agent 执行

    Args:
        session_id: Leader 会话 ID
        answers: 用户答案列表
        config: 配置字典
        skip_to_execution: 是否跳过需求评估和团队组建

    Yields:
        Dict: SSE 事件
    """
    from db import db  # scoped_session
    from models import LeaderSession
    from sqlalchemy.exc import OperationalError

    session = db.get(LeaderSession, session_id)
    if not session:
        db.session.rollback()
        yield {
            "type": "error",
            **build_fixed_sse_message("zh-CN", "leader.error.session_not_found"),
        }
        return

    if session.locale not in ('zh-CN', 'en-US'):
        logger.error("LeaderSession %s has invalid locale %r; falling back to zh-CN", session_id, session.locale)
    generation_locale = resolve_generation_locale(session_locale=session.locale)

    # === DB 行锁防重入（跨 worker 生效）===
    try:
        db.session.execute(
            text("SELECT id FROM leader_sessions WHERE id = :sid FOR UPDATE NOWAIT"),
            {"sid": session_id}
        )
    except OperationalError:
        db.session.rollback()
        logger.warning(f"[防重入] Session {session_id} 行锁获取失败，其他 worker 正在执行")
        yield {
            "type": "error",
            **build_fixed_sse_message(generation_locale, "leader.error.already_running"),
        }
        return

    # 状态检查：只允许明确的可恢复态继续。终态会话必须创建新 session 重跑，
    # 避免重复写 AgentResult 或覆盖 FinalReport。
    if session.state in TERMINAL_STATES:
        logger.warning(f"[防重入] Session {session_id} state={session.state} 已结束，拒绝恢复")
        db.session.rollback()
        yield {
            "type": "error",
            **build_fixed_sse_message(generation_locale, "leader.error.session_finished"),
        }
        return

    if session.state not in ('idle', 'questioning'):
        logger.warning(f"[防重入] Session {session_id} state={session.state}，拒绝恢复")
        db.session.rollback()
        yield {
            "type": "error",
            **build_fixed_sse_message(generation_locale, "leader.error.already_running"),
        }
        return

    # 原子性状态锁定：确保并发请求中只有一个能成功
    try:
        result = db.session.execute(
            text(
                "UPDATE leader_sessions SET state = 'assessing' "
                "WHERE id = :sid AND state IN ('idle', 'questioning')"
            ),
            {"sid": session_id}
        )
        if result.rowcount == 0:
            db.session.rollback()
            yield {
                "type": "error",
                **build_fixed_sse_message(generation_locale, "leader.error.already_running"),
            }
            return
        db.session.commit()
    except Exception:
        db.session.rollback()
        yield {
            "type": "error",
            **build_fixed_sse_message(generation_locale, "leader.error.session_lock_failed"),
        }
        return

    session = db.get(LeaderSession, session_id)
    if not session:
        yield {
            "type": "error",
            **build_fixed_sse_message(generation_locale, "leader.error.session_not_found"),
        }
        return

    DecisionRunService(db).mark_started(
        session_id,
        stage='execution' if skip_to_execution else 'assessment',
    )
    db.commit()

    conversation_id = session.conversation_id

    # 初始化服务
    await _initialize_services(config, db)

    # 清除消息序号缓存，避免外部直接写入（如 answer 消息）导致序号冲突
    clear_message_seq_cache(session_id)

    # 恢复执行时加载已有 Agent 结果
    existing_agent_results = []
    restored_selected_agents = []
    restored_dag_plan = {}
    if skip_to_execution:
        # 加载 DB 中剩余的 agent_results
        existing_agent_results = load_agent_results(db, session_id)

        # 从 team_config 消息恢复 selected_agents 和 dag_execution_plan
        team_config = load_team_config(db, session_id)
        restored_selected_agents = team_config["selected_agents"]
        restored_dag_plan = team_config["dag_plan"]

        # 防御性检查：恢复数据不完整时降级为重新组建
        if not restored_selected_agents:
            logger.warning(
                f"skip_to_execution=True but no team_config found for session {session_id}, "
                "falling back to full workflow (re-assess + re-form team)"
            )
            skip_to_execution = False

    # 加载历史 Q&A（从 DB 恢复之前轮次的问题和答案，用于评估上下文累积）
    qa_history = load_qa_history(db, session_id)
    all_asked = [{"question": qa["question"], "options": []} for qa in qa_history]

    # 构建 Workflow State
    initial_state: LeaderWorkflowState = {
        "conversation_id": conversation_id,
        "session_id": session_id,
        "user_id": user_id,
        "locale": generation_locale,
        "user_message": session.user_message,
        "history": [],
        "shared_evidence": [],
        "requirement_loop_count": session.requirement_loop_count,
        "requirement_passed": True if skip_to_execution else False,
        "requirement_questions": [],
        "all_asked_questions": all_asked,
        "qa_history": qa_history,
        "user_answers": answers,
        "assessment_result": {},
        "selected_agents": restored_selected_agents,
        "dag_execution_plan": restored_dag_plan,
        "agent_results": existing_agent_results,
        "current_agent_index": 0,
        "agent_retry_counts": {},
        "final_report": "",
        "stop_requested": False,
        "current_phase": "continuing",
        "skip_to_execution": skip_to_execution,
        "assessment_threshold": session.assessment_threshold or 60,
        "system_prompt_addition": session.system_prompt_addition,
        "sse_events": []
    }

    message_key = (
        "leader.phase.resuming"
        if skip_to_execution else
        "leader.phase.reassessing"
    )
    fixed_message = build_fixed_sse_message(generation_locale, message_key)
    yield {
        "type": "leader_thinking",
        "session_id": session_id,
        "phase": "assessing",
        "content": fixed_message["message"],
        **fixed_message,
    }

    graph = create_leader_workflow_graph()
    streamer = SSEStreamer(session_id=session_id)
    stop_event_emitted = False

    try:
        async for event in streamer.astream_graph_events(graph, initial_state):
            if event.get("type") == "execution_stopped":
                stop_event_emitted = True
            yield event

        stopped = is_session_stop_requested(db, session_id)
        if stopped and not stop_event_emitted:
            yield make_execution_stopped_event(session_id, generation_locale)
        elif not stopped:
            yield {
                "type": "done",
                "session_id": session_id,
                **build_fixed_sse_message(generation_locale, "leader.status.done"),
            }
        logger.info(f"Continue workflow completed for session {session_id}")

    except Exception as e:
        logger.error(f"Continue workflow failed: {e}", exc_info=True)

        if is_session_stop_requested(db, session_id):
            from .leader_persistence import mark_session_stopped
            mark_session_stopped(db, session_id)
            if not stop_event_emitted:
                yield make_execution_stopped_event(session_id, generation_locale)
            return

        mark_session_failed(db, session_id, str(e))

        yield {"type": "error", "session_id": session_id, "message": str(e)}

    finally:
        # 【兜底】若 session 未达终态（图中途被截断 / 新 early return 路径），强制标记 failed
        ensure_terminal_state_sync(
            session_id,
            skip_if_background=True,
            background_check=is_background_task_running,
        )


async def _initialize_services(config: Dict, db_session: Any) -> None:
    """初始化服务依赖（async 版）"""
    from services.llm_service import LLMService
    from services.agent_content_reader import get_agent_content_reader
    from services.harness.harness_coordinator import get_harness_coordinator

    llm_service = LLMService(
        api_key=config.get('LLM_API_KEY'),
        agents_dir=config.get('AGENTS_DIR', ''),
        workspace_dir=config.get('WORKSPACE_DIR', ''),
        base_url=config.get('LLM_BASE_URL'),
        model=config.get('LLM_MODEL')
    )
    max_tokens_limit = config.get('LLM_MAX_TOKENS', 16384)
    agent_reader = get_agent_content_reader(db_session)

    initialize_node_services(
        llm_service=llm_service,
        max_tokens_limit=max_tokens_limit,
        agent_reader=agent_reader,
        db_session=db_session
    )

    if config.get('OPENHARNESS_ENABLED'):
        try:
            harness_coordinator = get_harness_coordinator(config=dict(config))

            # 初始化 KnowledgeRetriever
            from context.knowledge_retriever import KnowledgeRetriever
            knowledge_retriever = KnowledgeRetriever()

            initialize_executor_services(
                harness_coordinator=harness_coordinator,
                max_parallel=config.get('MAX_AGENT_PARALLEL', 5),
                knowledge_retriever=knowledge_retriever
            )
        except Exception as e:
            logger.error(f"Failed to initialize OpenHarness: {e}")

    initialize_summarize_services(db_session=db_session)
