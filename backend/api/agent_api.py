"""用户端 Agent API

提供普通用户的 Agent CRUD 端点。
- GET /api/agents — 列表（所有 is_enabled=True 的 Agent）
- GET /api/agents/{id} — 详情
- POST /api/agents — 创建（source=db, is_system=False, is_enabled=False）
- PUT /api/agents/{id} — 编辑（仅 created_by=自己）
- DELETE /api/agents/{id} — 删除（仅 created_by=自己）
"""

import json
import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session

from database import get_db
from utils.time_utils import utcnow_naive
from api.deps import get_current_user, resolve_request_locale
from models import User, AgentConfig
from services.catalog_localization_service import catalog_localization_service
from utils.locale_utils import SupportedLocale
from utils.rate_limit import limiter, get_limit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/user/agents", tags=["user-agents"])


def _localized_agent(agent: AgentConfig, locale: SupportedLocale) -> dict:
    return catalog_localization_service.localize_item(
        data=agent.to_dict(),
        entity_type='agent',
        key=agent.agent_id,
        source_name=agent.name,
        is_system=agent.is_system,
        locale=locale,
    )


# ==================== 请求模型 ====================

from pydantic import BaseModel, Field, field_validator


class UserAgentCreateRequest(BaseModel):
    """用户创建 Agent 请求"""
    agent_id: str = Field(..., min_length=3, max_length=50, pattern=r'^[a-zA-Z0-9\-]+$', description="Agent 标识")
    name: str = Field(..., min_length=1, max_length=100, description="Agent 名称")
    description: Optional[str] = Field(default="", description="Agent 描述")
    model: Optional[str] = Field(default="inherit", description="使用的模型")
    content: str = Field(..., min_length=1, description="System prompt 内容")
    role: Optional[str] = Field(default=None, max_length=200)
    persona: Optional[str] = Field(default=None)
    expertise: Optional[str] = Field(default=None)
    approach: Optional[str] = Field(default=None)
    capabilities: Optional[List[str]] = Field(default=[])
    skill_level: int = Field(default=3, ge=1, le=5)
    tags: Optional[List[str]] = Field(default=[])
    preferred_contexts: Optional[List[str]] = Field(default=[])
    portrait_url: Optional[str] = Field(default=None, max_length=500)

    @field_validator('portrait_url')
    @classmethod
    def validate_portrait_url(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v != '':
            if not v.startswith(('http://', 'https://')):
                raise ValueError('portrait_url 必须以 http:// 或 https:// 开头')
        return v


class UserAgentUpdateRequest(BaseModel):
    """用户更新 Agent 请求"""
    name: Optional[str] = Field(default=None, max_length=100)
    description: Optional[str] = Field(default=None)
    model: Optional[str] = Field(default=None)
    content: Optional[str] = Field(default=None)
    role: Optional[str] = Field(default=None, max_length=200)
    persona: Optional[str] = Field(default=None)
    expertise: Optional[str] = Field(default=None)
    approach: Optional[str] = Field(default=None)
    capabilities: Optional[List[str]] = Field(default=None)
    skill_level: Optional[int] = Field(default=None, ge=1, le=5)
    tags: Optional[List[str]] = Field(default=None)
    preferred_contexts: Optional[List[str]] = Field(default=None)
    portrait_url: Optional[str] = Field(default=None, max_length=500)

    @field_validator('portrait_url')
    @classmethod
    def validate_portrait_url(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v != '':
            if not v.startswith(('http://', 'https://')):
                raise ValueError('portrait_url 必须以 http:// 或 https:// 开头')
        return v


# ==================== 路由 ====================

@router.get('')
@limiter.limit(get_limit('agent_list'))
def list_agents(
    request: Request,
    db_session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=500),
    search: Optional[str] = Query(default=None),
    tags: Optional[str] = Query(default=None),
    is_system: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    locale: Optional[str] = Query(default=None),
):
    """获取可用 Agent 列表（系统 + 自建）"""
    request_locale = resolve_request_locale(request, locale, user)
    try:
        # 返回所有启用的 Agent + 自己创建的（含未启用的）
        query = db_session.query(AgentConfig).filter(
            or_(
                AgentConfig.is_enabled == True,
                AgentConfig.created_by == user.id
            )
        )

        if search and search.strip():
            search_pattern = f'%{search.strip()}%'
            search_conditions = [
                AgentConfig.agent_id.ilike(search_pattern),
                AgentConfig.name.ilike(search_pattern),
                AgentConfig.description.ilike(search_pattern),
            ]
            label_keys = catalog_localization_service.matching_keys(
                'agent', request_locale, search
            )
            if label_keys:
                search_conditions.append(AgentConfig.agent_id.in_(label_keys))
            query = query.filter(or_(*search_conditions))

        # 系统/自建筛选
        if is_system is not None:
            if is_system.lower() in ('true', '1', 'yes'):
                query = query.filter(AgentConfig.is_system == True)
            elif is_system.lower() in ('false', '0', 'no'):
                query = query.filter(AgentConfig.is_system == False)

        # 分类筛选
        if category:
            from services.agent_category_service import apply_category_filter
            query = apply_category_filter(query, category, db=db_session)

        # JSONB tags 包含过滤（@> 操作符，精确匹配）
        if tags:
            tag_list = tags.split(',') if ',' in tags else [tags]
            for tag in tag_list:
                query = query.filter(AgentConfig.tags.op('@>')(json.dumps([tag.strip()])))

        query = query.order_by(AgentConfig.priority.asc(), AgentConfig.agent_id)
        total = query.count()
        agents = query.offset((page - 1) * per_page).limit(per_page).all()

        result = []
        for a in agents:
            d = _localized_agent(a, request_locale)
            d.pop('content', None)  # 列表不返回 content
            result.append(d)

        return {
            'agents': result,
            'total': total,
            'page': page,
            'per_page': per_page,
            'pages': (total + per_page - 1) // per_page
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception('Failed to list agents')
        raise HTTPException(status_code=500, detail='Internal server error')


@router.get('/{agent_id}')
@limiter.limit(get_limit('agent_detail'))
def get_agent(
    agent_id: str,
    request: Request,
    db_session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    locale: Optional[str] = Query(default=None),
):
    """获取 Agent 详情"""
    request_locale = resolve_request_locale(request, locale, user)
    agent = db_session.query(AgentConfig).filter_by(agent_id=agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail='Agent not found')

    # 系统 Agent 只返回启用的
    if agent.is_system and not agent.is_enabled:
        raise HTTPException(status_code=404, detail='Agent not found')

    # 自建 Agent：非 owner 只能看已启用的，且不返回 content
    if not agent.is_system and agent.created_by != user.id:
        if not agent.is_enabled:
            raise HTTPException(status_code=404, detail='Agent not found')
        d = _localized_agent(agent, request_locale)
        d.pop('content', None)  # 隐藏 system prompt
        return {'agent': d}

    return {'agent': _localized_agent(agent, request_locale)}


@router.post('', status_code=201)
@limiter.limit(get_limit('agent_create'))
def create_agent(
    request: Request,
    body: UserAgentCreateRequest,
    db_session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """创建自定义 Agent"""
    # 检查 agent_id 唯一
    existing = db_session.query(AgentConfig).filter_by(agent_id=body.agent_id).first()
    if existing:
        raise HTTPException(status_code=409, detail=f'Agent {body.agent_id} already exists')

    agent = AgentConfig(
        agent_id=body.agent_id,
        name=body.name,
        description=body.description or '',
        model=body.model or 'inherit',
        source='db',
        is_system=False,
        created_by=user.id,
        is_enabled=False,  # 需管理员审核
        content=body.content,
        role=body.role,
        persona=body.persona,
        expertise=body.expertise,
        approach=body.approach,
        capabilities=body.capabilities or [],
        skill_level=body.skill_level,
        tags=body.tags or [],
        preferred_contexts=body.preferred_contexts or [],
        portrait_url=body.portrait_url,
    )
    db_session.add(agent)
    try:
        db_session.commit()
        db_session.refresh(agent)
    except Exception:
        db_session.rollback()
        logger.exception(f'Failed to create agent: {body.agent_id}')
        raise HTTPException(status_code=500, detail='Failed to create agent')

    logger.info(f'User agent created: {body.agent_id} by user {user.id}')
    return {'agent': agent.to_dict()}


@router.put('/{agent_id}')
@limiter.limit(get_limit('agent_update'))
def update_agent(
    agent_id: str,
    request: Request,
    body: UserAgentUpdateRequest,
    db_session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """编辑自定义 Agent（仅限自己创建的）"""
    agent = db_session.query(AgentConfig).filter_by(agent_id=agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail='Agent not found')

    if agent.is_system:
        raise HTTPException(status_code=403, detail='System agents cannot be modified')

    if agent.created_by != user.id:
        raise HTTPException(status_code=403, detail='You can only edit your own agents')

    # 更新字段
    if body.name is not None: agent.name = body.name
    if body.description is not None: agent.description = body.description
    if body.model is not None: agent.model = body.model
    if body.content is not None: agent.content = body.content
    if body.role is not None: agent.role = body.role
    if body.persona is not None: agent.persona = body.persona
    if body.expertise is not None: agent.expertise = body.expertise
    if body.approach is not None: agent.approach = body.approach
    if body.capabilities is not None: agent.capabilities = body.capabilities
    if body.skill_level is not None: agent.skill_level = body.skill_level
    if body.tags is not None: agent.tags = body.tags
    if body.preferred_contexts is not None: agent.preferred_contexts = body.preferred_contexts
    if body.portrait_url is not None: agent.portrait_url = body.portrait_url
    agent.updated_at = utcnow_naive()

    try:
        db_session.commit()
        db_session.refresh(agent)
    except Exception:
        db_session.rollback()
        logger.exception(f'Failed to update agent: {agent_id}')
        raise HTTPException(status_code=500, detail='Failed to update agent')

    return {'agent': agent.to_dict()}


@router.delete('/{agent_id}')
@limiter.limit(get_limit('agent_delete'))
def delete_agent(
    agent_id: str,
    request: Request,
    db_session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """删除自定义 Agent（仅限自己创建的）"""
    agent = db_session.query(AgentConfig).filter_by(agent_id=agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail='Agent not found')

    if agent.is_system:
        raise HTTPException(status_code=403, detail='System agents cannot be deleted')

    if agent.created_by != user.id:
        raise HTTPException(status_code=403, detail='You can only delete your own agents')

    # 检查 Pack/Template 引用，防止悬挂引用
    from models import AgentPack, WorkflowTemplate

    refs = []
    # 仅加载 name + agents 字段（避免全量加载其他大字段）
    all_packs = db_session.query(AgentPack.name, AgentPack.agents).all()
    for name, agents in all_packs:
        if any(a.get('agent_id') == agent_id for a in (agents or [])):
            refs.append(f'Pack:{name}')
    all_templates = db_session.query(WorkflowTemplate.name, WorkflowTemplate.agents).all()
    for name, agents in all_templates:
        if any(a.get('agent_id') == agent_id for a in (agents or [])):
            refs.append(f'Template:{name}')
    if refs:
        raise HTTPException(
            status_code=409,
            detail=f'Agent 被以下组合包/模板引用，请先解绑: {", ".join(refs)}'
        )

    db_session.delete(agent)
    try:
        db_session.commit()
    except Exception:
        db_session.rollback()
        logger.exception(f'Failed to delete agent: {agent_id}')
        raise HTTPException(status_code=500, detail='Failed to delete agent')

    logger.info(f'User agent deleted: {agent_id} by user {user.id}')
    return {'message': f'Agent {agent_id} deleted'}

