"""性能监控 API

提供性能概览、Token 趋势、Agent 执行统计排名。
"""

import logging
from datetime import datetime, timedelta, timezone

from utils.time_utils import utcnow_naive
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from database import get_db
from api.deps import get_admin_user
from models import User, AgentConfig, ToolCallLog, LeaderAgentResult


logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin-performance"])

COST_PER_1K = 0.006  # 简化成本估算


@router.get('/performance/overview')
def get_performance_overview(
    db_session: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
    period: str = Query(default='week', description="时间范围（day/week/month）"),
):
    """获取性能概览统计"""
    try:
        if period not in ('day', 'week', 'month'):
            period = 'week'

        # 统一用 naive UTC 与 naive DateTime 列比较（非 UTC 会话时区下偏移会污染统计窗口）
        now = utcnow_naive()
        period_map = {'day': 1, 'week': 7, 'month': 30}
        days = period_map[period]
        since = now - timedelta(days=days)

        token_stats = db_session.query(
            func.coalesce(func.sum(LeaderAgentResult.tokens_used), 0).label('total_tokens')
        ).filter(LeaderAgentResult.created_at >= since).first()

        total_tokens = int(token_stats.total_tokens) if token_stats else 0
        daily_avg_tokens = round(total_tokens / max(days, 1))

        mid_point = since + timedelta(days=days // 2)
        first_half = db_session.query(
            func.coalesce(func.sum(LeaderAgentResult.tokens_used), 0).label('tokens')
        ).filter(LeaderAgentResult.created_at >= since, LeaderAgentResult.created_at < mid_point).first()
        second_half = db_session.query(
            func.coalesce(func.sum(LeaderAgentResult.tokens_used), 0).label('tokens')
        ).filter(LeaderAgentResult.created_at >= mid_point).first()

        first_tokens = int(first_half.tokens) if first_half else 0
        second_tokens = int(second_half.tokens) if second_half else 0
        if first_tokens > 0:
            trend = 'up' if second_tokens > first_tokens else ('down' if second_tokens < first_tokens else 'flat')
        else:
            trend = 'up' if second_tokens > 0 else 'flat'

        total_cost = round(total_tokens * COST_PER_1K / 1000, 2)
        daily_avg_cost = round(total_cost / max(days, 1), 2)

        agent_stats = db_session.query(
            func.coalesce(func.sum(AgentConfig.total_calls), 0).label('total'),
            func.coalesce(func.sum(AgentConfig.success_calls), 0).label('success'),
            func.coalesce(func.avg(AgentConfig.avg_execution_time), 0).label('avg_time')
        ).first()

        total_calls = int(agent_stats.total) if agent_stats else 0
        success_calls = int(agent_stats.success) if agent_stats else 0
        avg_time = round(float(agent_stats.avg_time), 2) if agent_stats else 0.0
        success_rate = round((success_calls / total_calls) * 100, 2) if total_calls > 0 else 0.0

        error_stats = db_session.query(
            func.count(ToolCallLog.id).label('total'),
            func.sum(case((ToolCallLog.status.in_(['failed', 'timeout']), 1), else_=0)).label('errors')
        ).filter(ToolCallLog.created_at >= since).first()

        total_tool_calls = int(error_stats.total) if error_stats else 0
        total_errors = int(error_stats.errors or 0) if error_stats else 0
        error_rate = round(total_errors / total_tool_calls, 4) if total_tool_calls > 0 else 0.0

        return {
            'period': period,
            'token_usage': {'total': total_tokens, 'daily_avg': daily_avg_tokens, 'trend': trend},
            'cost': {'total': total_cost, 'daily_avg': daily_avg_cost},
            'agent_execution': {'total_calls': total_calls, 'avg_time': avg_time, 'success_rate': success_rate},
            'errors': {'total': total_errors, 'rate': error_rate}
        }

    except Exception:
        logger.exception('Failed to fetch performance overview')
        raise HTTPException(status_code=500, detail={'error': 'Failed to fetch performance overview', 'message': 'An internal error occurred'})


@router.get('/performance/tokens')
def get_performance_tokens(
    db_session: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    granularity: str = Query(default='day'),
):
    """获取 Token 消耗趋势数据"""
    try:
        if granularity not in ('hour', 'day'):
            granularity = 'day'

        now = utcnow_naive()

        def _parse_naive_utc(value: str) -> datetime:
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
            return parsed

        try:
            end_date_dt = _parse_naive_utc(end_date) if end_date else now
            start_date_dt = _parse_naive_utc(start_date) if start_date else now - timedelta(days=7)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail={'error': 'Invalid date format', 'message': 'start_date and end_date must be in ISO format'})

        date_expr = func.date_trunc('hour' if granularity == 'hour' else 'day', LeaderAgentResult.created_at)

        results = db_session.query(
            date_expr.label('period'),
            func.coalesce(func.sum(LeaderAgentResult.tokens_used), 0).label('tokens')
        ).filter(
            LeaderAgentResult.created_at >= start_date_dt,
            LeaderAgentResult.created_at <= end_date_dt
        ).group_by('period').order_by('period').all()

        data = [{'date': row.period if isinstance(row.period, str) else row.period.isoformat(),
                 'tokens': int(row.tokens),
                 'cost': round(int(row.tokens) * COST_PER_1K / 1000, 2)} for row in results]

        return {'granularity': granularity, 'data': data}

    except HTTPException:
        raise
    except Exception:
        logger.exception('Failed to fetch token trend')
        raise HTTPException(status_code=500, detail={'error': 'Failed to fetch token trend', 'message': 'An internal error occurred'})


@router.get('/performance/agents')
def get_performance_agents(db_session: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    """获取 Agent 执行统计排名"""
    try:
        agents = db_session.query(AgentConfig).order_by(AgentConfig.total_calls.desc()).all()
        return {'agents': [{
            'agent_id': agent.agent_id, 'name': agent.name,
            'total_calls': agent.total_calls or 0,
            'success_rate': round((agent.success_calls / agent.total_calls) * 100, 2) if agent.total_calls and agent.total_calls > 0 else 0.0,
            'avg_time': round(agent.avg_execution_time or 0.0, 2),
            'total_tokens': agent.total_tokens or 0
        } for agent in agents]}

    except Exception:
        logger.exception('Failed to fetch agent performance')
        raise HTTPException(status_code=500, detail={'error': 'Failed to fetch agent performance', 'message': 'An internal error occurred'})
