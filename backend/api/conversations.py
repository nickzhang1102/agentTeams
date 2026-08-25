"""
FastAPI 对话管理路由模块

实现对话 CRUD API：
- GET / - 获取对话列表
- POST / - 创建新对话
- GET /{id} - 获取对话详情
- PUT /{id} - 更新对话
- DELETE /{id} - 删除对话
- POST /{id}/archive - 归档对话
- GET /share/{token} - 公开分享访问
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, asc
from sqlalchemy.orm import Session

from models import Conversation, Message, File
from api.deps import get_current_user, get_db, audit_log
from schemas.leader import normalize_category_key
from utils.time_utils import utcnow_naive

logger = logging.getLogger(__name__)

# 创建对话管理路由
router = APIRouter(prefix="/api/conversations", tags=["conversations"])


# ==================== Pydantic 模型 ====================

class CreateConversationRequest(BaseModel):
    title: str = Field(..., min_length=1)
    is_review_mode: bool = False
    model: Optional[str] = None


class UpdateMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=50000)


class UpdateConversationRequest(BaseModel):
    title: Optional[str] = None
    is_review_mode: Optional[bool] = None
    model: Optional[str] = None


# ==================== 辅助函数 ====================

def _assessment_category_map(db_session: Session, conversation_ids: list[int]) -> dict[int, str]:
    """Return non-other categories found in persisted assessment messages."""
    if not conversation_ids:
        return {}

    rows = db_session.query(
        Message.conversation_id,
        Message.content
    ).filter(
        Message.conversation_id.in_(conversation_ids),
        Message.message_type == 'assessment'
    ).order_by(
        desc(Message.created_at),
        desc(Message.id)
    ).all()

    categories: dict[int, str] = {}
    for conversation_id, content in rows:
        if conversation_id in categories or not isinstance(content, dict):
            continue

        category = normalize_category_key(content.get('category'))
        if category != 'other':
            categories[conversation_id] = category

    return categories


def _conversation_dict_with_category(conv: Conversation, fallback_categories: dict[int, str]) -> dict:
    """Serialize a conversation with normalized category and assessment fallback."""
    conv_dict = conv.to_dict()
    category = normalize_category_key(conv_dict.get('category'))
    if category == 'other':
        category = fallback_categories.get(conv.id, category)
    conv_dict['category'] = category
    return conv_dict

# ==================== 路由端点 ====================

@router.get("")
async def get_conversations(
    user = Depends(get_current_user),
    db_session: Session = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    sort: str = Query(default="updated_at:desc"),
    archived: str = Query(default="false")
):
    """获取用户的对话列表"""
    try:
        # 解析排序参数
        sort_parts = sort.split(':')
        if len(sort_parts) != 2:
            raise HTTPException(
                status_code=400,
                detail={'error': '排序参数格式错误'}
            )

        sort_field, sort_order = sort_parts
        if sort_field not in ['created_at', 'updated_at']:
            raise HTTPException(
                status_code=400,
                detail={'error': '排序字段不支持'}
            )
        if sort_order not in ['asc', 'desc']:
            raise HTTPException(
                status_code=400,
                detail={'error': '排序方式不支持'}
            )

        # 解析归档参数
        archived_only = archived.lower() == 'true'

        # 查询用户的对话（包含精选对话，确保用户可同时在"我的案例"和"精选案例"中看到）
        own_query = db_session.query(Conversation).filter_by(
            user_id=user.id
        )

        if archived_only:
            own_query = own_query.filter_by(is_archived=True)
        else:
            own_query = own_query.filter_by(is_archived=False)

        # 应用排序
        order_func = desc if sort_order == 'desc' else asc
        own_query = own_query.order_by(order_func(getattr(Conversation, sort_field)))

        # 应用 limit
        own_conversations = own_query.limit(limit).all()
        fallback_categories = _assessment_category_map(
            db_session,
            [conv.id for conv in own_conversations]
        )

        # 为每个对话添加 is_owner 字段
        conversations_list = []
        for conv in own_conversations:
            conv_dict = _conversation_dict_with_category(conv, fallback_categories)
            conv_dict['is_owner'] = True  # 用户自己的对话
            conversations_list.append(conv_dict)

        return {'conversations': conversations_list}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取对话列表错误: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={'error': '获取对话列表失败'}
        )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_conversation(
    request: CreateConversationRequest,
    user = Depends(get_current_user),
    db_session: Session = Depends(get_db)
):
    """创建新对话"""
    try:
        # 创建对话
        conversation = Conversation(
            title=request.title.strip(),
            user_id=user.id,
            is_review_mode=bool(request.is_review_mode),
            model_override=request.model,
            share_token=Conversation.generate_share_token()
        )

        db_session.add(conversation)
        db_session.flush()  # 获取 conversation.id

        # 审计日志
        audit_log(user.id, 'conversation.create', 'conversation', conversation.id,
                  {'title': conversation.title}, db_session)
        db_session.commit()

        return conversation.to_dict()

    except Exception as e:
        db_session.rollback()
        logger.error(f"创建对话错误: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={'error': '创建对话失败'}
        )


# ==================== 精选案例端点（无需认证） ====================

@router.get("/featured")
async def get_featured_conversations(
    db_session: Session = Depends(get_db)
):
    """获取精选案例列表（公开，无需认证）

    返回 is_featured=True 的对话，按 featured_order ASC 排序。
    description 优先从 LeaderFinalReport 提取，否则使用对话标题。
    """
    try:
        # 查询精选对话
        featured = db_session.query(Conversation).filter_by(
            is_featured=True,
            is_archived=False
        ).order_by(Conversation.featured_order.asc()).limit(50).all()

        if not featured:
            return []

        # 批量查询 LeaderFinalReport（避免 N+1 查询）
        conv_ids = [conv.id for conv in featured]
        from models import LeaderFinalReport
        reports = db_session.query(
            LeaderFinalReport.conversation_id,
            LeaderFinalReport.report
        ).filter(
            LeaderFinalReport.conversation_id.in_(conv_ids)
        ).all()

        # 构建 conversation_id -> report 的映射
        report_map = {r.conversation_id: r.report for r in reports}

        # 构建结果
        fallback_categories = _assessment_category_map(db_session, conv_ids)
        result = []
        for conv in featured:
            description = ''

            # 优先从 LeaderFinalReport 提取描述
            if conv.id in report_map:
                report = report_map[conv.id]
                # 跳过 Markdown 标题和分隔符，提取正文
                lines = [line.strip() for line in report.split('\n') if line.strip()]
                for line in lines:
                    if not line.startswith('#') and line != '---' and len(line) > 20:
                        description = line[:150] + ('...' if len(line) > 150 else '')
                        break

            # 如果没有提取到描述，使用空字符串（避免显示与标题重复的内容）
            if not description:
                description = ''

            result.append({
                'id': conv.id,
                'title': conv.title,
                'category': _conversation_dict_with_category(conv, fallback_categories)['category'],
                'share_token': conv.share_token,
                'description': description,
                'updated_at': conv.updated_at.isoformat() + 'Z' if conv.updated_at else None
            })

        return result

    except Exception as e:
        logger.error(f"获取精选案例错误: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={'error': '获取精选案例失败'}
        )


@router.get("/{conversation_id}")
async def get_conversation_detail(
    conversation_id: int,
    user = Depends(get_current_user),
    db_session: Session = Depends(get_db),
    page: int = Query(default=1, ge=1, description="消息页码"),
    per_page: int = Query(default=200, ge=1, le=500, description="每页消息数"),
):
    """获取对话详情（包括消息，支持分页）"""
    try:
        # 查询对话
        conversation = db_session.get(Conversation, conversation_id)

        if not conversation:
            raise HTTPException(
                status_code=404,
                detail={'error': '对话不存在'}
            )

        # 检查权限：只有所有者可以访问
        if conversation.user_id != user.id:
            raise HTTPException(
                status_code=403,
                detail={'error': '无权访问此对话'}
            )

        # 获取对话入口消息；Leader 内部过程事件由 Leader API 单独提供
        msg_query = db_session.query(Message).filter_by(
            conversation_id=conversation_id
        ).filter(
            Message.role.in_(['user', 'assistant'])
        )

        total_messages = msg_query.count()

        msg_query = msg_query.order_by(asc(Message.created_at), asc(Message.sequence_number))

        offset = (page - 1) * per_page
        messages = msg_query.offset(offset).limit(per_page).all()

        # 构建返回数据 - 前端期望分开的 conversation 和 messages
        return {
            'conversation': conversation.to_dict(),
            'messages': [msg.to_dict() for msg in messages],
            'pagination': {
                'total': total_messages,
                'page': page,
                'per_page': per_page,
                'pages': (total_messages + per_page - 1) // per_page if total_messages > 0 else 0
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取对话详情错误: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={'error': '获取对话详情失败'}
        )


@router.put("/{conversation_id}")
async def update_conversation(
    conversation_id: int,
    request: UpdateConversationRequest,
    user = Depends(get_current_user),
    db_session: Session = Depends(get_db)
):
    """更新对话标题"""
    try:
        # 查询对话
        conversation = db_session.get(Conversation, conversation_id)

        if not conversation:
            raise HTTPException(
                status_code=404,
                detail={'error': '对话不存在'}
            )

        # 检查权限：只有所有者可以更新
        if conversation.user_id != user.id:
            raise HTTPException(
                status_code=403,
                detail={'error': '无权修改此对话'}
            )

        # 更新标题
        if request.title is not None:
            title = request.title
            if not title or not title.strip():
                raise HTTPException(
                    status_code=400,
                    detail={'error': '标题不能为空'}
                )
            conversation.title = title.strip()

        # 更新评审模式
        if request.is_review_mode is not None:
            conversation.is_review_mode = request.is_review_mode

        # 更新模型覆盖
        if request.model is not None:
            conversation.model_override = request.model or None

        db_session.commit()

        return conversation.to_dict()

    except HTTPException:
        raise
    except Exception as e:
        db_session.rollback()
        logger.error(f"更新对话错误: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={'error': '更新对话失败'}
        )


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: int,
    user = Depends(get_current_user),
    db_session: Session = Depends(get_db)
):
    """删除对话"""
    try:
        # 查询对话
        conversation = db_session.get(Conversation, conversation_id)

        if not conversation:
            raise HTTPException(
                status_code=404,
                detail={'error': '对话不存在'}
            )

        # 检查权限：只有所有者可以删除
        if conversation.user_id != user.id:
            raise HTTPException(
                status_code=403,
                detail={'error': '无权删除此对话'}
            )

        # 删除对话（消息会级联删除）前记录审计日志
        audit_log(user.id, 'conversation.delete', 'conversation', conversation_id,
                  {'title': conversation.title}, db_session)

        # 删除前联动停止该对话的运行中 Leader 工作流。持久化取消记录没有
        # Conversation/LeaderSession 外键，级联删除后其它 worker 仍能看到它。
        from leader.sse_streamer import cancel_background_task
        from leader.terminal_state import TERMINAL_STATES
        from leader.leader_persistence import mark_session_stopped
        from models import LeaderSession

        running_sessions = db_session.query(LeaderSession).filter(
            LeaderSession.conversation_id == conversation_id,
            LeaderSession.state.notin_(TERMINAL_STATES),
        ).all()
        if running_sessions:
            for s in running_sessions:
                mark_session_stopped(
                    db_session,
                    s.id,
                    reason="conversation_deleted",
                )
                cancel_background_task(s.id)

        db_session.delete(conversation)
        db_session.commit()

        return None  # 204 No Content

    except HTTPException:
        raise
    except Exception as e:
        db_session.rollback()
        logger.error(f"删除对话错误: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={'error': '删除对话失败'}
        )


@router.put("/messages/{message_id}")
async def edit_message(
    message_id: int,
    request: UpdateMessageRequest,
    user = Depends(get_current_user),
    db_session: Session = Depends(get_db)
):
    """编辑 Leader 分析的用户问题（role=user, message_type=normal）。"""
    try:
        message = db_session.get(Message, message_id)
        if not message:
            raise HTTPException(status_code=404, detail={'error': '消息不存在'})

        # 校验对话归属
        conversation = db_session.get(Conversation, message.conversation_id)
        if not conversation or conversation.user_id != user.id:
            raise HTTPException(status_code=403, detail={'error': '无权修改此消息'})

        # normal 是 Leader 用户问题的持久化类型；不允许编辑内部流程事件
        if message.role != 'user' or message.message_type != 'normal':
            raise HTTPException(status_code=400, detail={'error': '仅支持编辑用户消息'})

        # 更新内容与编辑时间
        message.content = {'text': request.content}
        message.raw_content = request.content
        message.edited_at = utcnow_naive()
        db_session.commit()

        return message.to_dict()

    except HTTPException:
        raise
    except Exception as e:
        db_session.rollback()
        logger.error(f"编辑消息错误: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={'error': '编辑消息失败'}
        )


@router.post("/{conversation_id}/archive")
async def archive_conversation(
    conversation_id: int,
    user = Depends(get_current_user),
    db_session: Session = Depends(get_db)
):
    """归档对话"""
    try:
        # 查询对话
        conversation = db_session.get(Conversation, conversation_id)

        if not conversation:
            raise HTTPException(
                status_code=404,
                detail={'error': '对话不存在'}
            )

        # 检查权限：只有所有者可以归档
        if conversation.user_id != user.id:
            raise HTTPException(
                status_code=403,
                detail={'error': '无权归档此对话'}
            )

        # 标记为已归档
        conversation.is_archived = True
        db_session.commit()

        return {'success': True}

    except HTTPException:
        raise
    except Exception as e:
        db_session.rollback()
        logger.error(f"归档对话错误: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={'error': '归档对话失败'}
        )


# ==================== 搜索端点 ====================

@router.get("/search")
async def search_messages(
    q: str = Query(..., min_length=1, max_length=200),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    user = Depends(get_current_user),
    db_session: Session = Depends(get_db)
):
    """搜索消息内容（利用 pg_trgm GIN 索引加速 ILIKE）"""
    try:
        # 使用 JOIN 替代子查询，让 PostgreSQL 优化器更高效地利用索引
        query = db_session.query(Message).join(
            Conversation, Message.conversation_id == Conversation.id
        ).filter(
            Conversation.user_id == user.id,
            Message.raw_content.ilike(f'%{q}%')
        ).order_by(Message.created_at.desc())

        total = query.count()
        messages = query.offset((page - 1) * per_page).limit(per_page).all()

        # 批量加载所属对话信息
        conv_ids = list({msg.conversation_id for msg in messages})
        convs = {c.id: c for c in db_session.query(Conversation).filter(Conversation.id.in_(conv_ids)).all()}

        results = []
        for msg in messages:
            conv = convs.get(msg.conversation_id)
            content_text = msg.raw_content or (str(msg.content) if msg.content else '')
            idx = content_text.lower().find(q.lower())
            start = max(0, idx - 100)
            end = min(len(content_text), idx + len(q) + 100)
            snippet = content_text[start:end]

            results.append({
                'message_id': msg.id,
                'conversation_id': msg.conversation_id,
                'conversation_title': conv.title if conv else '',
                'role': msg.role,
                'snippet': snippet,
                'created_at': msg.created_at.isoformat() if msg.created_at else None
            })

        return {
            'messages': results,
            'pagination': {
                'total': total,
                'page': page,
                'per_page': per_page,
                'pages': (total + per_page - 1) // per_page if total > 0 else 0
            }
        }

    except Exception as e:
        logger.error(f"搜索消息错误: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={'error': '搜索消息失败'}
        )


# ==================== 公开分享端点（无需认证） ====================

@router.get("/share/{share_token}")
async def get_conversation_by_share_token(
    share_token: str,
    db_session: Session = Depends(get_db)
):
    """通过分享令牌公开访问对话详情（无需认证）"""
    try:
        # 通过 share_token 查询对话
        conversation = db_session.query(Conversation).filter_by(
            share_token=share_token
        ).first()

        if not conversation:
            raise HTTPException(
                status_code=404,
                detail={'error': '对话不存在或链接已失效'}
            )

        # 获取对话入口消息；Leader 内部过程事件由 Leader API 单独提供
        messages = db_session.query(Message).filter_by(
            conversation_id=conversation.id
        ).filter(
            Message.role.in_(['user', 'assistant'])
        ).order_by(Message.created_at, Message.sequence_number).all()

        # 获取对话的附件文件
        files = db_session.query(File).filter_by(
            conversation_id=conversation.id
        ).all()

        # 构建返回数据
        return {
            'conversation': conversation.to_dict(),
            'messages': [msg.to_dict() for msg in messages],
            'files': [f.to_dict() for f in files]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取分享对话详情错误: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={'error': '获取对话详情失败'}
        )

