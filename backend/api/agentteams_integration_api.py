"""Agent Teams 集成 API。"""
import logging
from typing import Any, List, Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, sessionmaker

from database import get_db
from config import Config
from models import AgentTeamsLaunch
from services.agentteams_integration_launch import (
    EXTERNAL_REQUEST_ID_MAX_LENGTH,
    LAUNCH_TITLE_MAX_LENGTH,
    AgentTeamsLaunchError,
    build_integration_capabilities,
    check_integration_protocol_version,
    get_agentteams_embed_session,
    get_agentteams_embed_status,
    get_agentteams_launch_by_request_id,
    launch_agentteams_consultation,
    resolve_agentteams_embed_answer_session,
    persist_agentteams_workflow_progress_events,
    claim_agentteams_answer_launch,
    release_agentteams_answer_claim,
    run_claimed_agentteams_workflow_events,
    schedule_agentteams_launch,
    stream_agentteams_embed_events,
)
from services.integration_client_service import IntegrationClientError
from services.integration_gateway import IntegrationGateway, register_builtin_adapters
from api.leader_api import build_llm_config, HEARTBEAT_INTERVAL, LEADER_SSE_MAX_DURATION
from leader.question_answers import create_question_answer_events
from services.llm_service import resolve_model_info
from utils.sse_async import create_sse_streaming_response


logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/integrations/agentteams", tags=["agentteams-integration"])
generic_router = APIRouter(prefix="/api/integrations/v1", tags=["integration-gateway"])


class AgentTeamsLaunchRequest(BaseModel):
    source: str = "agentteams"
    source_user_id: Optional[str] = None
    source_patient_id: Optional[str] = None
    source_conversation_id: Optional[Any] = None
    title: Optional[str] = Field(default="Agent Teams consultation", max_length=LAUNCH_TITLE_MAX_LENGTH)
    message: Optional[str] = None
    locale: Literal['zh-CN', 'en-US'] = 'zh-CN'
    metadata: Optional[dict[str, Any]] = None


class AgentTeamsEmbedAnswersRequest(BaseModel):
    session_id: int = Field(..., gt=0)
    answers: List[str] = Field(..., min_length=1)


class IntegrationLaunchRequest(BaseModel):
    """与提供商无关的启动载荷；不含任何患者专属字段名。

    长度约束由服务层（_validate_launch_payload）统一校验并返回契约内
    ``invalid_payload`` 错误码，避免模型层 422 破坏错误形状。
    """

    user_ref: Optional[str] = None
    subject_ref: Optional[str] = None
    conversation_ref: Optional[str] = None
    title: Optional[str] = None
    message: str
    locale: str = 'zh-CN'
    metadata: Optional[dict[str, Any]] = None


def _raise_launch_error(error: AgentTeamsLaunchError) -> None:
    raise HTTPException(
        status_code=error.status_code,
        detail={'error': error.error_code, 'message': error.message},
    )


def _set_embed_security_headers(response: Response) -> None:
    frame_ancestors = str(Config.AGENTTEAMS_EMBED_FRAME_ANCESTORS or "'self'")
    if '\r' in frame_ancestors or '\n' in frame_ancestors:
        frame_ancestors = "'self'"
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = f'frame-ancestors {frame_ancestors}'


@generic_router.post('/{client_key}/consultation-launches')
async def create_generic_consultation_launch(
    client_key: str,
    request: IntegrationLaunchRequest,
    response: Response,
    x_integration_key: Optional[str] = Header(default=None, alias='X-Integration-Key'),
    x_request_id: Optional[str] = Header(default=None, alias='X-Request-Id'),
    x_protocol_version: Optional[str] = Header(default=None, alias='X-Integration-Protocol-Version'),
    db_session: Session = Depends(get_db),
):
    """通用启动契约；遗留的 Agent Teams 路由保持不变。"""
    _set_embed_security_headers(response)
    register_builtin_adapters()
    try:
        check_integration_protocol_version(x_protocol_version)
        gateway = IntegrationGateway(db_session)
        client = gateway.authenticate(client_key, x_integration_key)
        normalized_request_id = _generic_request_id(x_request_id)
        payload = {
            'source': client.client_key,
            'source_user_id': request.user_ref,
            'source_patient_id': request.subject_ref,
            'source_conversation_id': request.conversation_ref,
            'title': request.title or f'{client.display_name} consultation',
            'message': request.message,
            'locale': request.locale,
            'metadata': request.metadata or {},
        }
        result = gateway.launch(
            client,
            payload=payload,
            request_id=normalized_request_id,
        )
    except IntegrationClientError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={'error': error.error_code, 'message': error.message},
        )
    except AgentTeamsLaunchError as error:
        _raise_launch_error(error)

    try:
        gateway.schedule_launch(
            client,
            result=result,
            request_id=normalized_request_id,
        )
    except Exception:
        # 启动事务已由适配器提交。调度器故障绝不能把
        # 已持久化的启动请求变成可重试的 500；
        # 恢复监控稍后可通过其持久化的请求 ID 与租约状态认领它。
        logger.exception(
            "Generic integration launch committed but scheduling failed: "
            "client=%s request_id=%s",
            client.client_key,
            normalized_request_id,
        )
    return result


def _generic_request_id(value: str | None) -> str:
    normalized = str(value or '').strip()
    if not normalized:
        raise IntegrationClientError(400, 'invalid_payload', 'X-Request-Id is required')
    if len(normalized) > 100:
        raise IntegrationClientError(400, 'invalid_payload', 'X-Request-Id must be at most 100 characters')
    return normalized


@generic_router.get('/{client_key}/consultation-launches/{request_id}')
def get_generic_consultation_status(
    client_key: str,
    request_id: str,
    response: Response,
    x_integration_key: Optional[str] = Header(default=None, alias='X-Integration-Key'),
    x_protocol_version: Optional[str] = Header(default=None, alias='X-Integration-Protocol-Version'),
    db_session: Session = Depends(get_db),
):
    """读取与提供商无关的启动状态，不创建工作。"""
    _set_embed_security_headers(response)
    register_builtin_adapters()
    try:
        check_integration_protocol_version(x_protocol_version)
        gateway = IntegrationGateway(db_session)
        client = gateway.authenticate(client_key, x_integration_key)
        return gateway.get_status(client, request_id=_generic_request_id(request_id))
    except IntegrationClientError as error:
        raise HTTPException(status_code=error.status_code, detail={'error': error.error_code, 'message': error.message})
    except AgentTeamsLaunchError as error:
        _raise_launch_error(error)


@generic_router.post('/{client_key}/consultation-launches/{request_id}/embed-token')
def reissue_generic_consultation_embed_token(
    client_key: str,
    request_id: str,
    response: Response,
    x_integration_key: Optional[str] = Header(default=None, alias='X-Integration-Key'),
    x_protocol_version: Optional[str] = Header(default=None, alias='X-Integration-Protocol-Version'),
    db_session: Session = Depends(get_db),
):
    """为已有启动重签一个嵌入令牌（不创建、不调度、不重启工作流）。

    供宿主在打开历史会诊时重新获取有效令牌；仅铸造令牌，不产生
    额外的计费或执行副作用。
    """
    _set_embed_security_headers(response)
    register_builtin_adapters()
    try:
        check_integration_protocol_version(x_protocol_version)
        gateway = IntegrationGateway(db_session)
        client = gateway.authenticate(client_key, x_integration_key)
        return gateway.reissue_embed(client, request_id=_generic_request_id(request_id))
    except IntegrationClientError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={'error': error.error_code, 'message': error.message},
        )
    except AgentTeamsLaunchError as error:
        _raise_launch_error(error)


@generic_router.post('/{client_key}/consultation-launches/{request_id}/reconcile')
def reconcile_generic_consultation(
    client_key: str,
    request_id: str,
    response: Response,
    x_integration_key: Optional[str] = Header(default=None, alias='X-Integration-Key'),
    x_protocol_version: Optional[str] = Header(default=None, alias='X-Integration-Protocol-Version'),
    db_session: Session = Depends(get_db),
):
    """通过适配器 SPI 执行一次只读的对账查询。"""
    _set_embed_security_headers(response)
    register_builtin_adapters()
    try:
        check_integration_protocol_version(x_protocol_version)
        gateway = IntegrationGateway(db_session)
        client = gateway.authenticate(client_key, x_integration_key)
        return gateway.reconcile(client, request_id=_generic_request_id(request_id))
    except IntegrationClientError as error:
        raise HTTPException(status_code=error.status_code, detail={'error': error.error_code, 'message': error.message})
    except AgentTeamsLaunchError as error:
        _raise_launch_error(error)


@generic_router.get('/{client_key}/capabilities')
def get_generic_integration_capabilities(
    client_key: str,
    response: Response,
    x_integration_key: Optional[str] = Header(default=None, alias='X-Integration-Key'),
    db_session: Session = Depends(get_db),
):
    """宣告协议版本、能力、限额与状态/错误码词表（契约 v1 的运行时事实源）。

    只读、不创建会话、不调度工作流；认证失败时返回契约内认证错误码。
    """
    _set_embed_security_headers(response)
    register_builtin_adapters()
    try:
        gateway = IntegrationGateway(db_session)
        client = gateway.authenticate(client_key, x_integration_key)
        return build_integration_capabilities(client)
    except IntegrationClientError as error:
        raise HTTPException(status_code=error.status_code, detail={'error': error.error_code, 'message': error.message})
    except AgentTeamsLaunchError as error:
        _raise_launch_error(error)


@router.post("/consultation-launches")
async def create_consultation_launch(
    request: AgentTeamsLaunchRequest,
    response: Response,
    x_integration_key: Optional[str] = Header(default=None, alias="X-Integration-Key"),
    x_request_id: Optional[str] = Header(default=None, alias="X-Request-Id"),
    db_session: Session = Depends(get_db),
):
    """创建由 Agent Teams 支撑的 AgentTeams 对话与嵌入令牌。"""
    _set_embed_security_headers(response)
    # 外部契约上限在 API 层把关；存储宽度（含命名空间前缀）由服务层负责。
    if x_request_id and len(x_request_id.strip()) > EXTERNAL_REQUEST_ID_MAX_LENGTH:
        raise HTTPException(
            status_code=400,
            detail={
                'error': 'invalid_payload',
                'message': 'X-Request-Id must be at most 100 characters',
            },
        )
    try:
        result = launch_agentteams_consultation(
            db_session=db_session,
            payload=request.model_dump(),
            request_id=x_request_id or '',
            integration_key=x_integration_key,
        )
    except AgentTeamsLaunchError as error:
        _raise_launch_error(error)

    start_background = bool(result.pop('_start_background', False))
    if start_background:
        launch = db_session.query(AgentTeamsLaunch).filter_by(
            source='agentteams',
            request_id=x_request_id,
        ).one()
        try:
            schedule_agentteams_launch(launch.id)
        except Exception:
            # 保留已提交的幂等/启动记录。稍后由恢复监控
            # 负责调度它。
            logger.exception(
                "Agent Teams launch committed but scheduling failed: request_id=%s",
                x_request_id,
            )

    return result


@router.get("/consultation-launches/{request_id}")
def get_consultation_launch(
    request_id: str,
    x_integration_key: Optional[str] = Header(default=None, alias="X-Integration-Key"),
    db_session: Session = Depends(get_db),
):
    """在不创建、不调度工作的前提下，对账单个启动请求的状态。"""
    try:
        return get_agentteams_launch_by_request_id(
            db_session=db_session,
            request_id=request_id,
            integration_key=x_integration_key,
        )
    except AgentTeamsLaunchError as error:
        _raise_launch_error(error)


@router.get("/embed-sessions/{embed_token}")
async def get_embed_session(
    embed_token: str,
    response: Response,
    db_session: Session = Depends(get_db),
):
    """读取一个 Agent Teams 嵌入会话快照。"""
    _set_embed_security_headers(response)
    try:
        return get_agentteams_embed_session(db_session, embed_token)
    except AgentTeamsLaunchError as error:
        _raise_launch_error(error)


@router.get("/embed-sessions/{embed_token}/status")
async def get_embed_session_status(
    embed_token: str,
    response: Response,
    db_session: Session = Depends(get_db),
):
    """为轮询读取轻量的版本与状态。"""
    _set_embed_security_headers(response)
    try:
        return get_agentteams_embed_status(db_session, embed_token)
    except AgentTeamsLaunchError as error:
        _raise_launch_error(error)


@router.get("/embed-sessions/{embed_token}/events")
async def stream_embed_session_events(
    embed_token: str,
    db_session: Session = Depends(get_db, scope="function"),
) -> StreamingResponse:
    """针对绑定到此嵌入令牌的单个会话，流式推送版本变化。"""
    try:
        get_agentteams_embed_status(db_session, embed_token)
    except AgentTeamsLaunchError as error:
        _raise_launch_error(error)

    response = create_sse_streaming_response(
        stream_agentteams_embed_events(embed_token),
        heartbeat_interval=HEARTBEAT_INTERVAL,
        max_duration=LEADER_SSE_MAX_DURATION,
        detach_on_disconnect=False,
    )
    _set_embed_security_headers(response)
    return response


@router.post("/embed-sessions/{embed_token}/answers")
async def answer_embed_session_questions(
    embed_token: str,
    request: AgentTeamsEmbedAnswersRequest,
    db_session: Session = Depends(get_db),
) -> StreamingResponse:
    """仅继续绑定到此嵌入令牌的提问中的 Leader 会话。"""
    try:
        leader_session, service_user_id = resolve_agentteams_embed_answer_session(
            db_session,
            embed_token,
            request.session_id,
        )
    except AgentTeamsLaunchError as error:
        _raise_launch_error(error)

    conversation = leader_session.conversation
    config = build_llm_config(
        model_info=resolve_model_info(
            conversation.model_override,
            db_session=db_session,
        )
    )
    launch = db_session.query(AgentTeamsLaunch).filter_by(
        agentteams_leader_session_id=leader_session.id,
    ).order_by(AgentTeamsLaunch.id.desc()).first()
    if launch is None:
        _raise_launch_error(AgentTeamsLaunchError(
            404,
            'embed_session_not_found',
            'Embed session not found',
        ))

    progress_session_factory = sessionmaker(bind=db_session.get_bind())
    try:
        lease_owner = claim_agentteams_answer_launch(db_session, launch.id)
    except AgentTeamsLaunchError as error:
        _raise_launch_error(error)

    try:
        events = create_question_answer_events(
            db_session=db_session,
            session=leader_session,
            answers=request.answers,
            config=config,
            user_id=service_user_id,
        )
        events = persist_agentteams_workflow_progress_events(
            launch.id,
            events,
            progress_session_factory,
        )
        events = run_claimed_agentteams_workflow_events(
            launch.id,
            lease_owner,
            events,
            progress_session_factory,
        )
    except Exception:
        release_agentteams_answer_claim(
            launch.id,
            lease_owner,
            progress_session_factory,
        )
        raise
    response = create_sse_streaming_response(
        events,
        heartbeat_interval=HEARTBEAT_INTERVAL,
        max_duration=LEADER_SSE_MAX_DURATION,
    )
    _set_embed_security_headers(response)
    return response
