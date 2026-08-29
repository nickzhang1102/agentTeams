"""Dashboard 管理 API

提供后台 Dashboard 统计、活动日志、会话管理、用户列表、精选案例管理。
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, desc, func
from sqlalchemy.orm import joinedload, Session

from database import get_db
from api.deps import get_admin_user
from models import User, Conversation, Message, AgentConfig, LeaderReportRating
from api.admin.admin_helpers import paginate
from api.admin.admin_schemas import FeaturedConversationUpdateRequest
from utils.time_utils import utcnow_naive


logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin-dashboard"])

QUALITY_PERIOD_DAYS = {
    "7d": 7,
    "30d": 30,
    "90d": 90,
}

PROBLEM_CLUSTERS = [
    {
        "key": "evidence_gap",
        "label": "证据不足",
        "keywords": ["证据", "来源", "引用", "出处", "依据", "支撑", "source"],
    },
    {
        "key": "unclear_conclusion",
        "label": "结论不清",
        "keywords": ["结论", "不清", "模糊", "看不懂", "重点", "主旨"],
    },
    {
        "key": "too_long",
        "label": "内容过长",
        "keywords": ["太长", "冗长", "啰嗦", "废话", "篇幅", "压缩"],
    },
    {
        "key": "not_actionable",
        "label": "建议不可执行",
        "keywords": ["不可执行", "不落地", "建议", "行动", "下一步", "操作"],
    },
    {
        "key": "accuracy_issue",
        "label": "准确性错误",
        "keywords": ["错误", "不准确", "事实", "幻觉", "错了", "误导"],
    },
    {
        "key": "other",
        "label": "其他",
        "keywords": [],
    },
]


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator * 100, 1)


def _build_rating_summary(total: int, positive_count: int, negative_count: int) -> dict:
    return {
        "total_ratings": total,
        "positive_count": positive_count,
        "negative_count": negative_count,
        "positive_rate": _rate(positive_count, total),
        "negative_rate": _rate(negative_count, total),
    }


def _build_target_breakdown(target_counts: dict[str, dict[str, int]]) -> list[dict]:
    breakdown: list[dict] = []
    for target_type in ["agent_result", "final_report"]:
        counts = target_counts.get(
            target_type,
            {"total": 0, "positive_count": 0, "negative_count": 0},
        )
        summary = _build_rating_summary(
            counts["total"],
            counts["positive_count"],
            counts["negative_count"],
        )
        breakdown.append({
            "target_type": target_type,
            "total": summary["total_ratings"],
            "positive_count": summary["positive_count"],
            "negative_count": summary["negative_count"],
            "positive_rate": summary["positive_rate"],
            "negative_rate": summary["negative_rate"],
        })
    return breakdown


def _cluster_negative_comments(comments: list[str]) -> list[dict]:
    negative_comments = [comment.strip() for comment in comments if comment and comment.strip()]
    if not negative_comments:
        return []

    buckets = {
        cluster["key"]: {
            "key": cluster["key"],
            "label": cluster["label"],
            "count": 0,
            "examples": [],
        }
        for cluster in PROBLEM_CLUSTERS
    }

    for comment in negative_comments:
        normalized = comment.lower()
        matched_key = "other"
        for cluster in PROBLEM_CLUSTERS:
            if cluster["key"] == "other":
                continue
            if any(keyword.lower() in normalized for keyword in cluster["keywords"]):
                matched_key = cluster["key"]
                break

        bucket = buckets[matched_key]
        bucket["count"] += 1
        if len(bucket["examples"]) < 3:
            bucket["examples"].append(comment)

    total = len(negative_comments)
    clusters = []
    order = {cluster["key"]: index for index, cluster in enumerate(PROBLEM_CLUSTERS)}
    for cluster in buckets.values():
        if cluster["count"] == 0:
            continue
        cluster["share"] = _rate(cluster["count"], total)
        clusters.append(cluster)

    return sorted(clusters, key=lambda item: (-item["count"], order[item["key"]]))


def _format_rating_comment(rating: LeaderReportRating) -> dict:
    return {
        "id": rating.id,
        "target_type": rating.target_type,
        "target_id": rating.target_id,
        "comment": rating.comment,
        "created_at": rating.created_at.isoformat() + "Z" if rating.created_at else None,
    }


def _load_rating_summary_counts(db_session: Session, start_date: datetime):
    return (
        db_session.query(
            func.count(LeaderReportRating.id).label("total"),
            func.coalesce(
                func.sum(case((LeaderReportRating.rating == 5, 1), else_=0)),
                0,
            ).label("positive_count"),
            func.coalesce(
                func.sum(case((LeaderReportRating.rating == 1, 1), else_=0)),
                0,
            ).label("negative_count"),
        )
        .filter(LeaderReportRating.created_at >= start_date)
        .one()
    )


def _load_target_breakdown_counts(db_session: Session, start_date: datetime) -> dict[str, dict[str, int]]:
    rows = (
        db_session.query(
            LeaderReportRating.target_type.label("target_type"),
            func.count(LeaderReportRating.id).label("total"),
            func.coalesce(
                func.sum(case((LeaderReportRating.rating == 5, 1), else_=0)),
                0,
            ).label("positive_count"),
            func.coalesce(
                func.sum(case((LeaderReportRating.rating == 1, 1), else_=0)),
                0,
            ).label("negative_count"),
        )
        .filter(LeaderReportRating.created_at >= start_date)
        .group_by(LeaderReportRating.target_type)
        .all()
    )
    return {
        row.target_type: {
            "total": int(row.total or 0),
            "positive_count": int(row.positive_count or 0),
            "negative_count": int(row.negative_count or 0),
        }
        for row in rows
    }


@router.get('/dashboard/stats')
def get_dashboard_stats(db_session: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    """获取Dashboard统计数据"""
    try:
        today = utcnow_naive().date()
        today_start = datetime.combine(today, datetime.min.time())

        total_users = db_session.query(User).count()
        active_today = db_session.query(User).filter(User.last_login >= today_start).count()

        total_conversations = db_session.query(Conversation).count()
        conversations_today = db_session.query(Conversation).filter(Conversation.created_at >= today_start).count()

        total_messages = db_session.query(Message).count()
        messages_today = db_session.query(Message).filter(Message.created_at >= today_start).count()

        total_agents = db_session.query(AgentConfig).count()
        active_agents = db_session.query(AgentConfig).filter_by(is_enabled=True).count()

        agent_stats = db_session.query(
            func.sum(AgentConfig.total_calls).label('total'),
            func.sum(AgentConfig.success_calls).label('success')
        ).first()

        success_rate = 0.0
        if agent_stats and agent_stats.total and agent_stats.total > 0:
            success_rate = round((agent_stats.success / agent_stats.total) * 100, 2)

        return {
            'users': {'total': total_users, 'active_today': active_today},
            'conversations': {'total': total_conversations, 'today': conversations_today},
            'messages': {'total': total_messages, 'today': messages_today},
            'agents': {'total': total_agents, 'active': active_agents, 'success_rate': success_rate}
        }

    except Exception:
        logger.exception('Failed to fetch dashboard stats')
        raise HTTPException(status_code=500, detail={'error': 'Failed to fetch dashboard stats', 'message': 'An internal error occurred'})


@router.get('/dashboard/activities')
def get_dashboard_activities(db_session: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    """获取Dashboard活动日志"""
    try:
        recent_messages = db_session.query(Message).order_by(Message.created_at.desc()).limit(10).all()
        messages_data = [{
            'id': msg.id, 'conversation_id': msg.conversation_id, 'role': msg.role,
            'message_type': msg.message_type, 'content': msg.content,
            'created_at': msg.created_at.isoformat() + 'Z' if msg.created_at else None
        } for msg in recent_messages]

        recent_conversations = db_session.query(Conversation).options(
            joinedload(Conversation.user)
        ).order_by(Conversation.created_at.desc()).limit(10).all()

        activities_data = [{
            'type': 'conversation_created', 'conversation_id': conv.id,
            'user': conv.user.username if conv.user else 'Unknown',
            'title': conv.title,
            'created_at': conv.created_at.isoformat() + 'Z' if conv.created_at else None
        } for conv in recent_conversations]

        return {'recent_messages': messages_data, 'recent_activities': activities_data}

    except Exception:
        logger.exception('Failed to fetch dashboard activities')
        raise HTTPException(status_code=500, detail={'error': 'Failed to fetch dashboard activities', 'message': 'An internal error occurred'})


@router.get('/dashboard/report-quality-insights')
def get_report_quality_insights(
    period: Literal["7d", "30d", "90d"] = Query(default="30d"),
    db_session: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """获取 Leader 报告质量洞察（只读，不影响 Agent 选择/执行）"""
    try:
        period_days = QUALITY_PERIOD_DAYS[period]
        start_date = utcnow_naive() - timedelta(days=period_days)
        summary_counts = _load_rating_summary_counts(db_session, start_date)
        target_counts = _load_target_breakdown_counts(db_session, start_date)
        negative_comment_rows = (
            db_session.query(LeaderReportRating.comment)
            .filter(
                LeaderReportRating.created_at >= start_date,
                LeaderReportRating.rating == 1,
                LeaderReportRating.comment.isnot(None),
                func.trim(LeaderReportRating.comment) != '',
            )
            .all()
        )

        recent_negative_comments = (
            db_session.query(LeaderReportRating)
            .filter(
                LeaderReportRating.created_at >= start_date,
                LeaderReportRating.rating == 1,
                LeaderReportRating.comment.isnot(None),
                func.trim(LeaderReportRating.comment) != '',
            )
            .order_by(desc(LeaderReportRating.created_at))
            .limit(10)
            .all()
        )

        return {
            "period_days": period_days,
            "summary": _build_rating_summary(
                int(summary_counts.total or 0),
                int(summary_counts.positive_count or 0),
                int(summary_counts.negative_count or 0),
            ),
            "target_breakdown": _build_target_breakdown(target_counts),
            "problem_clusters": _cluster_negative_comments([row.comment for row in negative_comment_rows]),
            "recent_negative_comments": [
                _format_rating_comment(rating)
                for rating in recent_negative_comments
            ],
        }

    except Exception:
        logger.exception('Failed to fetch report quality insights')
        raise HTTPException(status_code=500, detail={'error': 'Failed to fetch report quality insights', 'message': 'An internal error occurred'})


@router.get('/conversations')
def list_conversations(
    db_session: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=15, ge=1, le=100),
    user_id: Optional[int] = Query(default=None),
    category: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
):
    """获取会话列表（支持筛选、分页）"""
    try:
        query = db_session.query(Conversation).options(joinedload(Conversation.user))

        if user_id:
            query = query.filter_by(user_id=user_id)
        if category:
            query = query.filter_by(category=category.strip())
        if status:
            query = query.filter_by(status=status.strip())

        query = query.order_by(Conversation.updated_at.desc())
        pagination = paginate(query, page, per_page)

        conversations_data = [{
            'id': conv.id, 'title': conv.title or '无标题', 'user_id': conv.user_id,
            'username': conv.user.username if conv.user else '未知',
            'category': conv.category or 'other', 'status': conv.status or 'new',
            'is_review_mode': conv.is_review_mode, 'is_archived': conv.is_archived,
            'share_token': conv.share_token,
            'created_at': conv.created_at.isoformat() + 'Z' if conv.created_at else None,
            'updated_at': conv.updated_at.isoformat() + 'Z' if conv.updated_at else None,
        } for conv in pagination['items']]

        return {
            'conversations': conversations_data, 'total': pagination['total'],
            'page': pagination['page'], 'per_page': pagination['per_page'],
            'pages': pagination['pages']
        }

    except Exception:
        logger.exception('Failed to list conversations')
        raise HTTPException(status_code=500, detail={'error': 'Failed to list conversations', 'message': 'An internal error occurred'})


@router.get('/users')
def list_users(db_session: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    """获取用户列表（用于筛选下拉框）"""
    try:
        users = db_session.query(User).order_by(User.username.asc()).all()
        return {'users': [{'id': u.id, 'username': u.username} for u in users]}
    except Exception:
        logger.exception('Failed to list users')
        raise HTTPException(status_code=500, detail={'error': 'Failed to list users', 'message': 'An internal error occurred'})


@router.get("/featured-conversations")
async def get_featured_conversations_admin(
    admin=Depends(get_admin_user),
    db_session: Session = Depends(get_db),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
    search: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None)
):
    """获取所有对话列表（含精选状态），供管理员管理"""
    try:
        query = db_session.query(Conversation).filter_by(is_archived=False)

        if search:
            query = query.filter(Conversation.title.ilike(f'%{search}%'))
        if category and category != 'all':
            query = query.filter_by(category=category)

        total = query.count()
        conversations = query.order_by(
            Conversation.is_featured.desc(), Conversation.featured_order.asc(),
            Conversation.updated_at.desc()
        ).offset((page - 1) * per_page).limit(per_page).all()

        return {
            'conversations': [conv.to_dict() for conv in conversations],
            'pagination': {'total': total, 'page': page, 'per_page': per_page,
                           'pages': (total + per_page - 1) // per_page if total > 0 else 0}
        }

    except Exception as e:
        logger.error(f"获取对话列表错误: {str(e)}")
        raise HTTPException(status_code=500, detail={'error': '获取对话列表失败'})


@router.put("/featured-conversations")
async def update_featured_conversation(
    request: FeaturedConversationUpdateRequest,
    admin=Depends(get_admin_user),
    db_session: Session = Depends(get_db)
):
    """更新对话精选状态"""
    try:
        conversation = db_session.get(Conversation, request.conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail={'error': '对话不存在'})

        conversation.is_featured = request.is_featured
        conversation.featured_order = request.featured_order if request.is_featured else 0
        db_session.commit()

        return {'success': True, 'conversation': conversation.to_dict()}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新精选状态错误: {str(e)}")
        raise HTTPException(status_code=500, detail={'error': '更新精选状态失败'})
