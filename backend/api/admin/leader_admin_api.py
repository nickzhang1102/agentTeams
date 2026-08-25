"""Leader 会话管理 API

提供 Leader 会话列表、详情、统计、强制停止。
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from api.deps import get_admin_user, audit_log
from models import User, LeaderSession, LeaderAgentResult, Message
from leader.leader_persistence import mark_session_stopped
from leader.sse_streamer import cancel_background_task
from leader.terminal_state import TERMINAL_STATES


logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin-leader"])


class BatchDeleteRequest(BaseModel):
    session_ids: list[int]


@router.get('/leader/sessions')
def list_leader_sessions(
    db_session: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    state: Optional[str] = Query(default=None),
    risk_level: Optional[str] = Query(default=None),
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
):
    """Leader 会话列表（分页、筛选）"""
    try:
        query = db_session.query(LeaderSession)

        if state:
            query = query.filter(LeaderSession.state == state.strip())
        if risk_level:
            query = query.filter(LeaderSession.risk_level == risk_level.strip())
        if start_date:
            try:
                query = query.filter(LeaderSession.started_at >= datetime.fromisoformat(start_date))
            except ValueError:
                pass
        if end_date:
            try:
                query = query.filter(LeaderSession.started_at <= datetime.fromisoformat(end_date))
            except ValueError:
                pass

        query = query.order_by(LeaderSession.started_at.desc())

        session_ids = [s.id for s in query.order_by(
            LeaderSession.started_at.desc()
        ).offset((page - 1) * per_page).limit(per_page).all()]

        agent_count_sub = (
            db_session.query(
                LeaderAgentResult.leader_session_id,
                func.count(LeaderAgentResult.id).label('cnt')
            )
            .filter(LeaderAgentResult.leader_session_id.in_(session_ids))
            .group_by(LeaderAgentResult.leader_session_id)
            .subquery()
        )

        sessions_with_counts = (
            db_session.query(LeaderSession, func.coalesce(agent_count_sub.c.cnt, 0).label('agent_count'))
            .outerjoin(agent_count_sub, LeaderSession.id == agent_count_sub.c.leader_session_id)
            .filter(LeaderSession.id.in_(session_ids))
            .order_by(LeaderSession.started_at.desc())
            .all()
        )

        total = query.count()
        pages = (total + per_page - 1) // per_page if total > 0 else 0

        items = [{
            'id': session.id, 'conversation_id': session.conversation_id,
            'user_message': session.user_message[:100] + '...' if session.user_message and len(session.user_message) > 100 else session.user_message,
            'state': session.state, 'assessment_score': session.assessment_score,
            'risk_level': session.risk_level, 'agent_count': int(agent_count),
            'total_tokens': session.total_tokens,
            'started_at': session.started_at.isoformat() + 'Z' if session.started_at else None,
            'completed_at': session.completed_at.isoformat() + 'Z' if session.completed_at else None,
            'stop_requested': session.stop_requested, 'error_message': session.error_message,
        } for session, agent_count in sessions_with_counts]

        return {'items': items, 'total': total, 'page': page, 'per_page': per_page, 'pages': pages}

    except Exception:
        logger.exception('Failed to list leader sessions')
        raise HTTPException(status_code=500, detail={'error': 'Failed to list leader sessions', 'message': 'An internal error occurred'})


@router.get('/leader/sessions/{session_id}')
def get_leader_session_detail(session_id: int, db_session: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    """Leader 会话详情（含 agent 结果和最终报告）"""
    try:
        session = db_session.get(LeaderSession, session_id)
        if not session:
            raise HTTPException(status_code=404, detail={'error': 'Not found', 'message': f'Leader session {session_id} not found'})

        result = session.to_dict()
        team_config_msg = (
            db_session.query(Message)
            .filter(
                Message.leader_session_id == session_id,
                Message.message_type == 'team_config'
            )
            .order_by(Message.sequence_number.desc())
            .first()
        )
        team_config = team_config_msg.content if team_config_msg and team_config_msg.content else {}

        agent_results = (
            db_session.query(LeaderAgentResult)
            .filter(LeaderAgentResult.leader_session_id == session_id)
            .order_by(LeaderAgentResult.sequence_number.asc())
            .all()
        )

        result['team_config'] = team_config
        result['dag_plan'] = team_config.get('dag_plan', team_config.get('dag_execution_plan', {}))
        result['agent_results'] = [ar.to_dict() for ar in agent_results]

        if session.final_report:
            result['final_report'] = session.final_report[0].to_dict() if isinstance(session.final_report, list) else session.final_report.to_dict()
        else:
            result['final_report'] = None

        result['tool_call_logs'] = [tcl.to_dict() if hasattr(tcl, 'to_dict') else {
            'id': tcl.id, 'tool_name': tcl.tool_name, 'status': tcl.status,
            'execution_time': tcl.execution_time,
            'created_at': tcl.created_at.isoformat() + 'Z' if tcl.created_at else None,
        } for tcl in session.tool_call_logs]

        return result

    except HTTPException:
        raise
    except Exception:
        logger.exception(f'Failed to get leader session detail: {session_id}')
        raise HTTPException(status_code=500, detail={'error': 'Failed to get leader session detail', 'message': 'An internal error occurred'})


@router.get('/leader/stats')
def get_leader_stats(db_session: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    """Leader 会话统计"""
    try:
        total = db_session.query(func.count(LeaderSession.id)).scalar() or 0

        state_counts = dict(
            db_session.query(LeaderSession.state, func.count(LeaderSession.id))
            .group_by(LeaderSession.state).all()
        )

        completed = state_counts.get('completed', 0)
        failed = state_counts.get('failed', 0)
        stopped = state_counts.get('stopped', 0)
        finished = completed + failed + stopped
        success_rate = round(completed / finished * 100, 1) if finished > 0 else 0

        avg_tokens = db_session.query(
            func.avg(LeaderSession.total_tokens)
        ).filter(LeaderSession.total_tokens > 0).scalar() or 0

        avg_duration = db_session.query(
            func.avg(func.extract('epoch', LeaderSession.completed_at - LeaderSession.started_at))
        ).filter(LeaderSession.completed_at.isnot(None), LeaderSession.started_at.isnot(None)).scalar() or 0

        risk_counts = dict(
            db_session.query(LeaderSession.risk_level, func.count(LeaderSession.id))
            .group_by(LeaderSession.risk_level).all()
        )

        return {
            'total': total, 'state_counts': state_counts,
            'success_rate': success_rate, 'avg_tokens': round(avg_tokens, 1),
            'avg_duration_seconds': round(avg_duration, 1), 'risk_counts': risk_counts,
        }

    except Exception:
        logger.exception('Failed to get leader stats')
        raise HTTPException(status_code=500, detail={'error': 'Failed to get leader stats', 'message': 'An internal error occurred'})


@router.post('/leader/sessions/{session_id}/stop')
def admin_stop_leader_session(session_id: int, db_session: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    """管理员强制停止 Leader 会话"""
    try:
        session = db_session.get(LeaderSession, session_id)
        if not session:
            raise HTTPException(status_code=404, detail={'error': 'Not found', 'message': f'Leader session {session_id} not found'})

        active_states = ['assessing', 'questioning', 'forming_team', 'web_search', 'monitoring', 'summarizing']
        if session.state not in active_states:
            raise HTTPException(status_code=400, detail={'error': 'Invalid state', 'message': f'Session is in {session.state} state, cannot stop'})

        mark_session_stopped(db_session, session_id, reason="admin_requested")

        return {'message': f'Leader session {session_id} stop requested', 'session_id': session_id, 'state': session.state}

    except HTTPException:
        raise
    except Exception:
        db_session.rollback()
        logger.exception(f'Failed to stop leader session: {session_id}')
        raise HTTPException(status_code=500, detail={'error': 'Failed to stop leader session', 'message': 'An internal error occurred'})


@router.post('/leader/sessions/batch-delete')
def batch_delete_leader_sessions(
    body: BatchDeleteRequest,
    db_session: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """批量删除 Leader 会话（含关联数据级联清理）"""
    try:
        session_ids = body.session_ids
        if not session_ids:
            raise HTTPException(status_code=400, detail={'error': 'Bad request', 'message': 'session_ids is required'})

        existing = db_session.query(LeaderSession).filter(LeaderSession.id.in_(session_ids)).all()
        existing_ids = {s.id for s in existing}
        failed_ids = [sid for sid in session_ids if sid not in existing_ids]

        if existing:
            # 活动工作流必须先走统一停止契约：持久化跨 worker 取消墓碑
            # 并收敛状态；本进程任务取消只是低延迟优化。
            active_sessions = [
                session for session in existing
                if session.state not in TERMINAL_STATES
            ]
            for session in active_sessions:
                mark_session_stopped(
                    db_session,
                    session.id,
                    reason="admin_deleted",
                )
                cancel_background_task(session.id)

            # LeaderAgentResult 无 ORM 级联，手动删除
            db_session.query(LeaderAgentResult).filter(
                LeaderAgentResult.leader_session_id.in_(existing_ids)
            ).delete(synchronize_session=False)

            # 删除 LeaderSession，ORM 级联清理 messages + harness_mappings
            for session in existing:
                db_session.delete(session)

            # 批量删除属敏感操作，落 SecurityLog 审计
            audit_log(
                user_id=admin.id,
                action='admin.leader_session.batch_delete',
                resource_type='leader_session',
                details={'session_ids': sorted(existing_ids)},
                db_session=db_session,
            )

            db_session.commit()

        return {'deleted': len(existing), 'failed_ids': failed_ids}

    except HTTPException:
        raise
    except Exception:
        db_session.rollback()
        logger.exception('Failed to batch delete leader sessions')
        raise HTTPException(status_code=500, detail={'error': 'Failed to batch delete', 'message': 'An internal error occurred'})

