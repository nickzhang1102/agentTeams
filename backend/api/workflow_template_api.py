"""
Workflow Template API Router
提供工作流模板的 CRUD 和一键启动端点
"""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from database import get_db
from api.deps import get_current_user, resolve_request_locale
from leader.locale_generation import resolve_generation_locale
from models import User, Conversation
from schemas.leader import normalize_category_key
from utils.rate_limit import limiter, get_limit
from utils.time_utils import utcnow_naive
from schemas.workflow_template import (
    WorkflowTemplateCreateRequest,
    WorkflowTemplateUpdateRequest,
    ApplyTemplateRequest,
)
from services.workflow_template_service import WorkflowTemplateService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workflow-templates", tags=["workflow-templates"])


@router.get('')
def list_templates(
    request: Request,
    category: str = Query(default=None),
    is_system: bool = Query(default=None),
    skip_assessment: bool = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    locale: str = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    request_locale = resolve_request_locale(request, locale, user)
    service = WorkflowTemplateService(db)
    templates, total = service.list_templates(
        user_id=user.id,
        category=category,
        is_system=is_system,
        skip_assessment=skip_assessment,
        page=page,
        per_page=per_page,
    )
    return {
        'items': service.serialize_templates(templates, request_locale),
        'total': total,
        'page': page,
        'per_page': per_page,
    }


@router.get('/{template_id}')
def get_template(
    template_id: int,
    request: Request,
    locale: str = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    request_locale = resolve_request_locale(request, locale, user)
    service = WorkflowTemplateService(db)
    template = service.get_template(template_id, user_id=user.id)
    if not template:
        raise HTTPException(status_code=404, detail={'error': '模板不存在'})
    return service.serialize_template(template, request_locale)


@router.post('', status_code=201)
@limiter.limit(get_limit('agent_create'))
def create_template(
    request: Request,
    body: WorkflowTemplateCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = WorkflowTemplateService(db)

    # pack_id 和 agents 二选一校验
    agents_list = None
    if body.pack_id and body.agents:
        raise HTTPException(status_code=400, detail={'error': 'pack_id 和 agents 不能同时指定'})
    if body.agents:
        agents_list = [a.model_dump() for a in body.agents]
        invalid = service.validate_agents([a['agent_id'] for a in agents_list])
        if invalid:
            raise HTTPException(
                status_code=400,
                detail={'error': '以下 Agent 无效或已禁用', 'invalid_agents': invalid}
            )

    # 快速模式必须有 agents
    if body.skip_assessment and not body.pack_id and not agents_list:
        raise HTTPException(
            status_code=400,
            detail={'error': '快速模式必须指定至少一个 Agent（通过 pack_id 或 agents）'}
        )

    template = service.create_template(
        name=body.name,
        user_id=user.id,
        is_admin=user.is_admin,
        description=body.description,
        category=body.category,
        pack_id=body.pack_id,
        agents=agents_list,
        skip_assessment=body.skip_assessment,
        assessment_threshold=body.assessment_threshold,
        system_prompt_addition=body.system_prompt_addition,
    )
    request_locale = resolve_request_locale(request, None, user)
    return service.serialize_template(template, request_locale)


@router.put('/{template_id}')
@limiter.limit(get_limit('agent_update'))
def update_template(
    template_id: int,
    request: Request,
    body: WorkflowTemplateUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = WorkflowTemplateService(db)
    update_data = body.model_dump(exclude_unset=True)

    if 'agents' in update_data and update_data['agents'] is not None:
        agents_list = [a if isinstance(a, dict) else a.model_dump() for a in update_data['agents']]
        invalid = service.validate_agents([a['agent_id'] for a in agents_list])
        if invalid:
            raise HTTPException(
                status_code=400,
                detail={'error': '以下 Agent 无效或已禁用', 'invalid_agents': invalid}
            )
        update_data['agents'] = agents_list

    try:
        template = service.update_template(template_id, user_id=user.id, is_admin=user.is_admin, **update_data)
        request_locale = resolve_request_locale(request, None, user)
        return service.serialize_template(template, request_locale)
    except ValueError as e:
        raise HTTPException(status_code=404, detail={'error': str(e)})
    except PermissionError as e:
        raise HTTPException(status_code=403, detail={'error': str(e)})


@router.delete('/{template_id}', status_code=204)
@limiter.limit(get_limit('agent_delete'))
def delete_template(
    template_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = WorkflowTemplateService(db)
    try:
        service.delete_template(template_id, user_id=user.id, is_admin=user.is_admin)
    except ValueError as e:
        raise HTTPException(status_code=404, detail={'error': str(e)})
    except PermissionError as e:
        raise HTTPException(status_code=403, detail={'error': str(e)})


@router.post('/{template_id}/apply')
@limiter.limit(get_limit('agent_create'))
async def apply_template(
    template_id: int,
    request: Request,
    body: ApplyTemplateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """从模板一键启动 Leader 会话"""
    from api.leader_api import _start_leader_workflow

    try:
        resolve_generation_locale(explicit_locale=body.locale)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail={'code': 'UNSUPPORTED_LOCALE', 'error': '不支持的语言'},
        )

    service = WorkflowTemplateService(db)
    template = service.get_template(template_id, user_id=user.id)
    if not template:
        raise HTTPException(status_code=404, detail={'error': '模板不存在'})

    # 解析 agent_id 列表
    agent_ids = service.resolve_agent_ids(template)
    if template.skip_assessment and not agent_ids:
        raise HTTPException(
            status_code=400,
            detail={'error': '模板快速模式但无可用 Agent，请检查 pack 或 agents 配置'}
        )

    # 快速模式不会经过需求评估，默认使用团队方案分类给“我的案例”兜底。
    conversation = db.get(Conversation, body.conversation_id)
    if not conversation or conversation.user_id != user.id:
        raise HTTPException(status_code=404, detail={'error': '对话不存在或无权访问'})

    case_category = service.resolve_case_category(template)
    if normalize_category_key(conversation.category) == 'other' and case_category != 'other':
        conversation.category = case_category

    # 递增 usage_count（try/finally 确保即使后续 workflow 失败也记录使用次数）
    template.usage_count += 1
    template.last_used_at = utcnow_naive()
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.warning(f'Failed to update usage_count for template {template_id}')

    return await _start_leader_workflow(
        conversation_id=body.conversation_id,
        message=body.message,
        file_ids=body.file_ids or [],
        user=user,
        db_session=db,
        skip_to_execution=template.skip_assessment,
        pre_selected_agents=agent_ids if template.skip_assessment else None,
        assessment_threshold=template.assessment_threshold,
        system_prompt_addition=template.system_prompt_addition,
        explicit_locale=body.locale,
        accept_language=request.headers.get('accept-language'),
    )

