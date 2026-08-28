"""
Leader Persistence

持久化函数：Agent 结果、Leader 消息、最终报告、消息序号缓存。
从 workflow_nodes.py 提取（2026-06-18 workflow-nodes-split refactor）。
"""
import logging
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from utils.time_utils import utcnow_naive

logger = logging.getLogger(__name__)

EVIDENCE_PERSISTENCE_FAILED = "evidence_persistence_failed"


def _degrade_structured_report(
    structured_report: Optional[dict],
    reason: str,
) -> Optional[dict]:
    """Return a degraded report projection without mutating caller-owned state."""
    if not isinstance(structured_report, dict):
        return structured_report
    return {
        **structured_report,
        "source_quality_status": "degraded",
        "source_degradation_reasons": list(dict.fromkeys([
            *(structured_report.get("source_degradation_reasons") or []),
            reason,
        ])),
    }


def _mark_run_evidence_degraded(
    db_session: Any,
    session_id: int,
    reason: str,
) -> None:
    """Best-effort run quality update isolated from core result persistence."""
    from services.decision_run_service import DecisionRunService

    try:
        with db_session.begin_nested():
            run_service = DecisionRunService(db_session)
            run = run_service.get_for_session(session_id, for_update=True)
            if run is not None:
                run_service.mark_quality(run, "degraded", [reason])
    except Exception:
        logger.exception(
            "Failed to mark evidence persistence degradation for session %s",
            session_id,
        )


# ==================== 消息序号缓存 ====================

# ContextVar 隔离的消息序号缓存（每个请求/协程独立，避免并发冲突）
_message_seq_cache_var: ContextVar[Dict[int, int]] = ContextVar('_message_seq_cache', default=None)


def _get_message_seq_cache() -> Dict[int, int]:
    """获取当前上下文的消息序号缓存（惰性初始化）"""
    cache = _message_seq_cache_var.get()
    if cache is None:
        cache = {}
        _message_seq_cache_var.set(cache)
    return cache


def clear_message_seq_cache(session_id: int = None) -> None:
    """清除消息序号缓存

    在 workflow 恢复（continue）前调用，避免外部直接 db.add() 写入的
    消息（如 answer）导致缓存与实际 DB 序号不一致。

    Args:
        session_id: 指定 session 清除，None 则清除全部
    """
    cache = _get_message_seq_cache()
    if session_id is not None:
        cache.pop(session_id, None)
    else:
        cache.clear()


def _get_next_msg_sequence(db_session: Any, session_id: int) -> int:
    """获取 Message 表的下一个序号（带 ContextVar 缓存）

    Args:
        db_session: 数据库会话
        session_id: LeaderSession ID

    Returns:
        int: 下一个序号
    """
    from models import Message

    cache = _get_message_seq_cache()

    if session_id not in cache:
        last_msg = db_session.query(Message).filter(
            Message.leader_session_id == session_id,
            Message.sequence_number.isnot(None)
        ).order_by(Message.sequence_number.desc()).first()
        cache[session_id] = (last_msg.sequence_number if last_msg else 0)

    cache[session_id] += 1
    return cache[session_id]


# ==================== 持久化函数 ====================


def _save_leader_message(
    db_session: Any,
    conversation_id: int,
    session_id: int,
    message_type: str,
    content: dict,
    content_locale: Optional[str] = None,
) -> bool:
    """保存 Leader 流程消息到 Message 表

    与旧版 LeaderCoordinator._create_leader_message 行为一致，
    保证历史会话恢复时前端能获取完整消息列表。

    Args:
        db_session: 数据库会话
        conversation_id: 对话 ID
        session_id: LeaderSession ID
        message_type: 消息类型（assessment/question/team_config/progress）
        content: JSON 内容

    Returns:
        bool: True 表示保存成功，False 表示失败
    """
    from models import Message

    if db_session is None or conversation_id is None:
        return False

    try:
        seq = _get_next_msg_sequence(db_session, session_id)
        message = Message.create_leader_message(
            conversation_id=conversation_id,
            leader_session_id=session_id,
            message_type=message_type,
            content=content,
            sequence_number=seq,
            content_locale=content_locale,
        )
        db_session.add(message)
        db_session.commit()
        logger.info(f"Saved leader message: type={message_type}, seq={seq}, session={session_id}")
        return True
    except Exception as e:
        db_session.rollback()
        logger.error(f"Failed to save leader message (type={message_type}, session={session_id}): {e}")
        return False


def _persist_agent_results(
    db_session: Any,
    conversation_id: int,
    session_id: int,
    results: List[Dict]
) -> None:
    """持久化 Agent 执行结果到 LeaderAgentResult 表

    与旧版 LeaderCoordinator._monitor_execution_phase 行为一致。

    Args:
        db_session: 数据库会话
        conversation_id: 对话 ID
        session_id: LeaderSession ID
        results: Agent 执行结果列表
    """
    from models import LeaderAgentResult, LeaderSession
    from services.decision_evidence_service import DecisionEvidenceService

    if db_session is None:
        logger.warning("DB session not available, skipping agent result persistence")
        return

    if not results:
        return

    try:
        # LeaderSession 行是同一次工作流结果写入的串行化边界。lease 交接期间旧
        # worker 可能迟到，锁内按 agent_id 去重可避免重复 AgentResult。
        session_row = db_session.query(LeaderSession).filter(
            LeaderSession.id == session_id
        ).with_for_update().first()
        if session_row is None:
            db_session.rollback()
            logger.warning("LeaderSession %s no longer exists; skipping agent results", session_id)
            return

        existing_agent_ids = {
            agent_id for (agent_id,) in db_session.query(LeaderAgentResult.agent_id).filter_by(
                leader_session_id=session_id
            ).all()
        }
        unique_results = []
        for result in results:
            agent_id = result.get("agent_id", "unknown")
            if agent_id in existing_agent_ids:
                logger.info(
                    "Skipping already persisted agent result: session=%s agent=%s",
                    session_id,
                    agent_id,
                )
                continue
            existing_agent_ids.add(agent_id)
            unique_results.append(result)

        if not unique_results:
            db_session.commit()
            return

        last_result = db_session.query(LeaderAgentResult).filter_by(
            leader_session_id=session_id
        ).order_by(LeaderAgentResult.sequence_number.desc()).first()
        start_seq = (last_result.sequence_number if last_result else 0) + 1

        evidence_service = DecisionEvidenceService(db_session)
        for i, result in enumerate(unique_results):
            seq = start_seq + i
            evidence_map = result.get("evidence_map")
            structured_report = result.get("structured_report")
            projected_evidence = None
            try:
                with db_session.begin_nested():
                    projected_evidence = evidence_service.persist_for_session(
                        session_id,
                        evidence_map,
                        raw_tool_results=result.get("raw_tool_results") or {},
                    )
                    if projected_evidence is not None and isinstance(structured_report, dict):
                        claims = structured_report.get("claims")
                        if isinstance(claims, list):
                            claim_result = evidence_service.persist_claims_for_session(
                                session_id,
                                claims,
                            )
                            structured_report = {
                                **structured_report,
                                "claims": [
                                    evidence_service.claim_projection(claim)
                                    for claim in claim_result.claims
                                ],
                            }
            except Exception:
                logger.exception(
                    "Evidence enrichment failed for agent result: session=%s agent=%s seq=%s",
                    session_id,
                    result.get("agent_id"),
                    seq,
                )
                projected_evidence = None
                structured_report = _degrade_structured_report(
                    structured_report,
                    EVIDENCE_PERSISTENCE_FAILED,
                )
                _mark_run_evidence_degraded(
                    db_session,
                    session_id,
                    EVIDENCE_PERSISTENCE_FAILED,
                )
            agent_result = LeaderAgentResult(
                conversation_id=conversation_id,
                leader_session_id=session_id,
                agent_id=result.get("agent_id", "unknown"),
                agent_name=result.get("agent_name", result.get("agent_id", "unknown")),
                status="success" if result.get("success") else "failed",
                content=result.get("content"),
                content_locale=result.get("content_locale", "zh-CN"),
                error=result.get("error"),
                tool_calls=result.get("tool_calls"),
                decomposition=result.get("decomposition"),
                summary=result.get("summary"),
                structured_report=structured_report,
                raw_tool_results=result.get("raw_tool_results"),
                evidence_map=(
                    projected_evidence
                    if projected_evidence is not None
                    else evidence_map
                ),
                tokens_used=result.get("tokens_used", 0),
                execution_time=result.get("execution_time", 0.0),
                iterations=result.get("iterations", 1),
                sequence_number=seq
            )
            db_session.add(agent_result)
            db_session.flush()
            logger.info(f"Queued agent result: {result.get('agent_id')} seq={seq}")

        db_session.commit()
        logger.info(f"Persisted {len(unique_results)} agent results for session {session_id}")
    except Exception as e:
        db_session.rollback()
        logger.error(f"Failed to persist agent results for session {session_id}: {e}")


def _persist_final_report(
    db_session: Any,
    session_id: int,
    report: str,
    completed_at: datetime,
    content_locale: str = "zh-CN",
    executive_summary: Optional[dict] = None,
    structured_report: Optional[dict] = None,
    evidence_map: Optional[list] = None,
    state: dict | None = None,
    quality_status: str = "passed",
    degradation_reasons: Optional[List[str]] = None,
    evidence_context_dropped_count: int = 0,
) -> Any:
    """持久化最终报告到数据库

    Args:
        db_session: 数据库会话
        session_id: LeaderSession ID
        report: 最终报告（Markdown）
        content_locale: 最终报告用户可见内容的实际语言
        executive_summary: 最终报告摘要 payload
        structured_report: 最终报告完整结构化 payload
        evidence_map: 最终报告证据引用列表
        completed_at: 完成时间
        state: 工作流状态字典，用于回写 total_tokens/total_cost（可空）
    """
    from models import LeaderFinalReport, LeaderSession
    from services.decision_evidence_service import DecisionEvidenceService

    # 与 mark_session_stopped 使用相同的 LeaderSession 行锁作为完成/停止的
    # 原子裁决点。谁先取得锁并提交，谁决定该工作流的终态；停止已经生效时，
    # 迟到的汇总不得再写报告或把状态覆盖回 completed。
    leader_session = db_session.get(
        LeaderSession,
        session_id,
        with_for_update=True,
        populate_existing=True,
    )
    if leader_session is None:
        logger.warning(
            "LeaderSession %s 不存在（可能已随对话删除），跳过最终报告落库",
            session_id,
        )
        return None
    if leader_session.state == "stopped" or is_session_stop_requested(
        db_session,
        session_id,
    ):
        logger.info(
            "LeaderSession %s 已收到停止请求，丢弃迟到的最终报告",
            session_id,
        )
        return None

    original_evidence_map = evidence_map
    original_structured_report = structured_report
    original_degradation_reasons = list(degradation_reasons or [])
    degradation_reasons = list(original_degradation_reasons)
    projected_evidence = None
    claim_degradation_reasons: List[str] = []
    try:
        with db_session.begin_nested():
            evidence_service = DecisionEvidenceService(db_session)
            projected_evidence = evidence_service.persist_for_session(
                session_id,
                evidence_map,
            )
            if projected_evidence is not None:
                evidence_map = projected_evidence
                if isinstance(structured_report, dict) and isinstance(
                    structured_report.get("claims"), list
                ):
                    claim_result = evidence_service.persist_claims_for_session(
                        session_id,
                        structured_report["claims"],
                    )
                    structured_report = {
                        **structured_report,
                        "claims": [
                            evidence_service.claim_projection(claim)
                            for claim in claim_result.claims
                        ],
                    }
                    degradation_reasons = list(dict.fromkeys([
                        *degradation_reasons,
                        *claim_result.degradation_reasons,
                    ]))
                    claim_degradation_reasons = list(claim_result.degradation_reasons)
                    if degradation_reasons:
                        quality_status = "degraded"
                evidence_service.record_context_dropped_for_session(
                    session_id,
                    evidence_context_dropped_count,
                )
    except Exception:
        logger.exception("Evidence enrichment failed for final report: session=%s", session_id)
        evidence_map = original_evidence_map
        structured_report = _degrade_structured_report(
            original_structured_report,
            EVIDENCE_PERSISTENCE_FAILED,
        )
        degradation_reasons = list(dict.fromkeys([
            *original_degradation_reasons,
            EVIDENCE_PERSISTENCE_FAILED,
        ]))
        quality_status = "degraded"
    if claim_degradation_reasons and isinstance(structured_report, dict):
        structured_report["source_quality_status"] = "degraded"
        structured_report["source_degradation_reasons"] = list(dict.fromkeys([
            *(structured_report.get("source_degradation_reasons") or []),
            *claim_degradation_reasons,
        ]))
    if (
        isinstance(original_structured_report, dict)
        and isinstance(structured_report, dict)
        and original_structured_report is not structured_report
    ):
        original_structured_report.clear()
        original_structured_report.update(structured_report)
        structured_report = original_structured_report

    # 写入/更新 LeaderFinalReport
    existing_report = db_session.query(LeaderFinalReport).filter_by(
        leader_session_id=session_id
    ).first()

    if existing_report:
        existing_report.report = report
        existing_report.content_locale = content_locale
        existing_report.executive_summary = executive_summary
        existing_report.structured_report = structured_report
        existing_report.evidence_map = evidence_map
        existing_report.created_at = completed_at
        final_report_record = existing_report
    else:
        new_report = LeaderFinalReport(
            conversation_id=leader_session.conversation_id,
            leader_session_id=session_id,
            report=report,
            content_locale=content_locale,
            executive_summary=executive_summary,
            structured_report=structured_report,
            evidence_map=evidence_map,
        )
        db_session.add(new_report)
        final_report_record = new_report

    # 更新 LeaderSession 状态
    if leader_session is not None:
        leader_session.completed_at = completed_at
        leader_session.state = "completed"

        # 【FIX】更新 total_tokens 和 total_cost（state 由调用方传入，防御 None）
        total_tokens = (state or {}).get("total_tokens", 0)
        leader_session.total_tokens = total_tokens
        if total_tokens > 0:
            # 简化成本计算：$0.01 / 1K tokens（实际应根据模型定价）
            leader_session.total_cost = round(total_tokens * 0.01 / 1000, 4)
        logger.info(f"Updated session {session_id}: total_tokens={total_tokens}, total_cost={leader_session.total_cost}")

        # 【FIX】更新 Conversation 的 status='completed'（修复首页显示问题）
        from models import Conversation
        conversation = db_session.get(Conversation, leader_session.conversation_id)
        if conversation:
            conversation.status = 'completed'
            logger.info(f"Updated conversation {leader_session.conversation_id}: status=completed")

        from services.decision_run_service import DecisionRunService
        DecisionRunService(db_session).mark_report_persisted(
            session_id,
            quality_status=quality_status,
            degradation_reasons=degradation_reasons or [],
        )

    db_session.commit()
    db_session.refresh(final_report_record)
    logger.info(f"Final report persisted for session {session_id}")
    return final_report_record


# ==================== Session 生命周期 ====================


def create_leader_session(
    db_session: Any,
    conversation_id: int,
    message: str,
    assessment_threshold: int = 60,
    system_prompt_addition: Optional[str] = None,
    locale: str = 'zh-CN',
    auto_commit: bool = True,
    decision_source: str = 'web',
    decision_source_ref: Optional[str] = None,
) -> "LeaderSession":
    """创建 LeaderSession 并持久化

    Args:
        db_session: 数据库会话
        conversation_id: 对话 ID
        message: 用户消息
        assessment_threshold: 评估阈值
        system_prompt_addition: 系统提示追加内容
        locale: 本次生成的语言快照

    Returns:
        LeaderSession: 已持久化的 session 对象（含 id）
    """
    from models import LeaderSession

    session = LeaderSession(
        conversation_id=conversation_id,
        user_message=message,
        state="assessing",
        started_at=utcnow_naive(),  # 与项目既有 naive UTC 惯例保持一致（leader_api 亦用 utcnow）
        assessment_threshold=assessment_threshold,
        system_prompt_addition=system_prompt_addition,
        locale=locale,
    )
    db_session.add(session)
    db_session.flush()

    from services.decision_run_service import DecisionRunService
    DecisionRunService(db_session).create_for_leader_session(
        session,
        source=decision_source,
        source_ref=decision_source_ref,
    )
    if auto_commit:
        db_session.commit()
    logger.info(f"Created LeaderSession {session.id}")
    return session


def mark_session_failed(
    db_session: Any,
    session_id: int,
    error_message: str,
) -> None:
    """将 LeaderSession 标记为失败，并更新关联 Conversation 状态

    Args:
        db_session: 数据库会话
        session_id: LeaderSession ID
        error_message: 错误信息
    """
    from models import LeaderSession
    from sqlalchemy.exc import PendingRollbackError
    from sqlalchemy.orm.exc import StaleDataError

    if is_session_stop_requested(db_session, session_id):
        mark_session_stopped(db_session, session_id)
        return

    session = db_session.get(LeaderSession, session_id)
    if session:
        if session.state in {"completed", "stopped"}:
            logger.info(
                "Session %s already reached terminal state %s; ignoring late failure",
                session_id,
                session.state,
            )
            return
        session.state = "failed"
        session.error_message = error_message[:2000]

        from models import Conversation
        conversation = db_session.get(Conversation, session.conversation_id)
        if conversation:
            conversation.status = 'error'
            logger.info(f"Updated conversation {session.conversation_id}: status=error")

        from services.decision_run_service import DecisionRunService
        DecisionRunService(db_session).sync_from_leader_session(
            session_id,
            error_code='leader_workflow_failed',
        )

        try:
            db_session.commit()
        except (StaleDataError, PendingRollbackError) as e:
            # session 行已在 DB 中消失（例如所属对话被删除时级联删除），
            # identity map 里的对象已过期，UPDATE 0 行。回滚后安全跳过，
            # 避免二次异常遮蔽真正的工作流错误。
            db_session.rollback()
            logger.warning(
                "标记失败时 session %s 已不存在，跳过本次失败标记（%s）",
                session_id, e,
            )


def request_session_stop(
    db_session: Any,
    session_id: int,
    *,
    reason: str = "user_requested",
) -> bool:
    """Persist a cancellation marker that survives session/conversation deletion."""
    from sqlalchemy.dialects.postgresql import insert
    from models import LeaderSession, LeaderWorkflowCancellation

    statement = insert(LeaderWorkflowCancellation).values(
        session_id=session_id,
        reason=reason,
    ).on_conflict_do_nothing(index_elements=["session_id"])
    executor = getattr(db_session, "session", db_session)
    executor.execute(statement)
    session = db_session.get(LeaderSession, session_id)
    if session is not None:
        session.stop_requested = True
    return session is not None


def is_session_stop_requested(db_session: Any, session_id: int) -> bool:
    """Read the durable marker first, then the compatibility session flag."""
    from models import LeaderSession, LeaderWorkflowCancellation

    cancellation = db_session.get(LeaderWorkflowCancellation, session_id)
    if isinstance(cancellation, LeaderWorkflowCancellation):
        return True
    session = db_session.get(LeaderSession, session_id)
    return session is not None and session.stop_requested is True


def mark_session_stopped(
    db_session: Any,
    session_id: int,
    *,
    reason: str = "user_requested",
) -> bool:
    """Idempotently converge LeaderSession, DecisionRun and Conversation to stopped."""
    from models import Conversation, LeaderSession
    from services.decision_run_service import DecisionRunService

    session = db_session.query(LeaderSession).filter(
        LeaderSession.id == session_id
    ).with_for_update().populate_existing().first()
    if session is None:
        request_session_stop(db_session, session_id, reason=reason)
        db_session.commit()
        return False
    if session.state in {"completed", "failed"}:
        return False

    request_session_stop(db_session, session_id, reason=reason)

    session.state = "stopped"
    session.completed_at = session.completed_at or utcnow_naive()
    session.error_message = None

    conversation = db_session.get(Conversation, session.conversation_id)
    if conversation is not None and conversation.status != "completed":
        conversation.status = "stopped"

    DecisionRunService(db_session).sync_from_leader_session(session_id)
    db_session.commit()
    return True


def load_agent_results(
    db_session: Any,
    session_id: int,
) -> List[Dict]:
    """加载 LeaderSession 已有的 Agent 执行结果

    Args:
        db_session: 数据库会话
        session_id: LeaderSession ID

    Returns:
        List[Dict]: Agent 结果字典列表
    """
    from models import LeaderAgentResult

    db_results = db_session.query(LeaderAgentResult).filter_by(
        leader_session_id=session_id
    ).order_by(LeaderAgentResult.sequence_number.asc()).all()
    return [
        {
            "agent_id": r.agent_id,
            "agent_name": r.agent_name,
            "content": r.content,
            "content_locale": r.content_locale,
            "summary": r.summary,
            "structured_report": r.structured_report,
            "raw_tool_results": r.raw_tool_results,
            "evidence_map": r.evidence_map,
            "success": r.status == "success",
            "error": r.error,
            "tool_calls": r.tool_calls or [],
            "tokens_used": r.tokens_used or 0,
            "execution_time": r.execution_time or 0,
            "decomposition": r.decomposition,
        }
        for r in db_results
    ]


def load_qa_history(
    db_session: Any,
    session_id: int,
) -> List[Dict]:
    """从 DB 加载历史问题和答案（按 sequence_number 排序）

    直接从 answer 消息的 content['answers'] 提取 Q&A 配对——每项 answer
    已含 question 字段（见 leader_api.py answer 持久化），无需依赖 question
    消息队列配对，避免部分作答时 pending_questions 残留导致的后续错位。

    Args:
        db_session: 数据库会话
        session_id: LeaderSession ID

    Returns:
        List[Dict]: [{"question": "问题文本", "answer": "用户答案"}, ...]
    """
    from models import Message

    messages = db_session.query(Message).filter(
        Message.leader_session_id == session_id,
        Message.message_type == 'answer',
    ).order_by(Message.sequence_number.asc()).all()

    qa_pairs: List[Dict] = []
    for msg in messages:
        for a in (msg.content or {}).get('answers', []):
            if isinstance(a, dict):
                qa_pairs.append({
                    # `or ''` 防御历史数据中 question/answer 为 None 的情况：
                    # .get(key, '') 在键存在但值为 None 时返回 None，
                    # 下游 summarize 等处的 .strip() 会直接 AttributeError。
                    'question': str(a.get('question') or ''),
                    'answer': str(a.get('answer') or ''),
                })

    return qa_pairs


def load_team_config(
    db_session: Any,
    session_id: int,
) -> Dict:
    """从 team_config 消息恢复 selected_agents 和 dag_execution_plan

    Args:
        db_session: 数据库会话
        session_id: LeaderSession ID

    Returns:
        Dict: {"selected_agents": [...], "dag_plan": {...}}
    """
    from models import Message

    team_config_msg = db_session.query(Message).filter(
        Message.leader_session_id == session_id,
        Message.message_type == 'team_config'
    ).order_by(Message.sequence_number.desc()).first()

    if team_config_msg and team_config_msg.content:
        tc = team_config_msg.content
        return {
            "selected_agents": tc.get('agent_details', []),
            "dag_plan": tc.get('dag_plan', tc.get('dag_execution_plan', {})),
        }
    return {"selected_agents": [], "dag_plan": {}}

