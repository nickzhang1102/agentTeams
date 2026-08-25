"""
Agent Pack API Router
提供 Agent 组合包的 CRUD 和克隆端点
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from database import get_db
from api.deps import get_current_user, resolve_request_locale
from models import User
from utils.rate_limit import limiter, get_limit
from schemas.agent_pack import (
    AgentPackCreateRequest,
    AgentPackUpdateRequest,
)
from services.agent_pack_service import AgentPackService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent-packs", tags=["agent-packs"])


@router.get('')
def list_packs(
    request: Request,
    category: str = Query(default=None),
    is_system: bool = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    locale: str = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    request_locale = resolve_request_locale(request, locale, user)
    service = AgentPackService(db)
    packs, total = service.list_packs(
        user_id=user.id,
        category=category,
        is_system=is_system,
        page=page,
        per_page=per_page,
    )
    return {
        'items': [service.serialize_pack(p, request_locale) for p in packs],
        'total': total,
        'page': page,
        'per_page': per_page,
    }


@router.get('/{pack_id}')
def get_pack(
    pack_id: int,
    request: Request,
    locale: str = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    request_locale = resolve_request_locale(request, locale, user)
    service = AgentPackService(db)
    pack = service.get_pack(pack_id, user_id=user.id)
    if not pack:
        raise HTTPException(status_code=404, detail={'error': '组合包不存在'})
    return service.serialize_pack(pack, request_locale)


@router.post('', status_code=201)
@limiter.limit(get_limit('agent_create'))
def create_pack(
    request: Request,
    body: AgentPackCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = AgentPackService(db)

    # 校验 agents 引用有效性
    agents_list = [a.model_dump() for a in body.agents]
    invalid = service.validate_agents(agents_list)
    if invalid:
        raise HTTPException(
            status_code=400,
            detail={'error': '以下 Agent 无效或已禁用', 'invalid_agents': invalid}
        )

    pack = service.create_pack(
        name=body.name,
        agents=agents_list,
        user_id=user.id,
        description=body.description,
        category=body.category,
        tags=body.tags,
    )
    request_locale = resolve_request_locale(request, None, user)
    return service.serialize_pack(pack, request_locale)


@router.put('/{pack_id}')
@limiter.limit(get_limit('agent_update'))
def update_pack(
    pack_id: int,
    request: Request,
    body: AgentPackUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = AgentPackService(db)

    # 如果更新了 agents，校验引用有效性
    update_data = body.model_dump(exclude_unset=True)
    if 'agents' in update_data and update_data['agents'] is not None:
        agents_list = [a if isinstance(a, dict) else a.model_dump() for a in update_data['agents']]
        invalid = service.validate_agents(agents_list)
        if invalid:
            raise HTTPException(
                status_code=400,
                detail={'error': '以下 Agent 无效或已禁用', 'invalid_agents': invalid}
            )
        update_data['agents'] = agents_list

    try:
        pack = service.update_pack(pack_id, user_id=user.id, is_admin=user.is_admin, **update_data)
        request_locale = resolve_request_locale(request, None, user)
        return service.serialize_pack(pack, request_locale)
    except ValueError as e:
        raise HTTPException(status_code=404, detail={'error': str(e)})
    except PermissionError as e:
        raise HTTPException(status_code=403, detail={'error': str(e)})


@router.delete('/{pack_id}', status_code=204)
@limiter.limit(get_limit('agent_delete'))
def delete_pack(
    pack_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = AgentPackService(db)
    try:
        service.delete_pack(pack_id, user_id=user.id, is_admin=user.is_admin)
    except ValueError as e:
        raise HTTPException(status_code=404, detail={'error': str(e)})
    except PermissionError as e:
        raise HTTPException(status_code=403, detail={'error': str(e)})


@router.post('/{pack_id}/clone', status_code=201)
@limiter.limit(get_limit('agent_create'))
def clone_pack(
    pack_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = AgentPackService(db)
    try:
        clone = service.clone_pack(pack_id, user_id=user.id)
        request_locale = resolve_request_locale(request, None, user)
        return service.serialize_pack(clone, request_locale)
    except ValueError as e:
        raise HTTPException(status_code=404, detail={'error': str(e)})
    except PermissionError as e:
        raise HTTPException(status_code=403, detail={'error': str(e)})
