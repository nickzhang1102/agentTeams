"""面向与提供商无关的集成客户的管理生命周期 API。"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from api.deps import audit_log, get_admin_user
from database import get_db
from models import (
    Conversation,
    IntegrationClient,
    IntegrationAccessOperation,
    Message,
    AgentTeamsEmbedToken,
    AgentTeamsLaunch,
    LeaderSession,
    SecurityLog,
    User,
)
from services.integration_client_service import (
    IntegrationClientError,
    IntegrationClientService,
)
from services.agentteams_integration_launch import (
    AgentTeamsLaunchError,
    get_embed_revoke_operation,
    list_embed_revoke_operations,
    revoke_agentteams_embed_access,
)


router = APIRouter(prefix="/integration-clients", tags=["admin-integration-clients"])


class IntegrationClientCreateRequest(BaseModel):
    client_key: str = Field(min_length=2, max_length=50)
    adapter_key: str = Field(min_length=2, max_length=50)
    display_name: str = Field(min_length=1, max_length=100)
    service_account_id: int = Field(gt=0)
    capabilities: dict = Field(default_factory=lambda: {"launch": True})
    reason: str | None = Field(default=None, max_length=500)


class IntegrationClientEnabledRequest(BaseModel):
    enabled: bool
    reason: str | None = Field(default=None, max_length=500)


class IntegrationClientRotateKeyRequest(BaseModel):
    rotation_window_seconds: int = Field(default=3600, ge=0, le=IntegrationClientService.MAX_ROTATION_WINDOW_SECONDS)
    reason: str | None = Field(default=None, max_length=500)


class IntegrationClientEmbedRevokeRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=500)
    operation_id: str | None = Field(default=None, min_length=1, max_length=100)

    @field_validator("request_id", "reason", "operation_id")
    @classmethod
    def reject_blank_values(cls, value: str) -> str:
        if value is None:
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized


def _raise_client_error(error: IntegrationClientError) -> None:
    raise HTTPException(
        status_code=error.status_code,
        detail={"error": error.error_code, "message": error.message},
    )


def _audit(
    db_session: Session,
    admin: User,
    *,
    action: str,
    client: IntegrationClient,
    details: dict,
) -> None:
    audit_log(
        user_id=admin.id,
        action=action,
        resource_type="integration_client",
        resource_id=client.id,
        details={"client_key": client.client_key, **details},
        db_session=db_session,
    )


@router.get("")
def list_integration_clients(
    db_session: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """返回不含凭证机密（credential material）的生命周期元数据。"""
    clients = db_session.query(IntegrationClient).order_by(IntegrationClient.client_key).all()
    return {"items": [client.to_dict() for client in clients]}


@router.get("/{client_key}")
def get_integration_client(
    client_key: str,
    db_session: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    client = IntegrationClientService.get(db_session, client_key)
    if client is None:
        raise HTTPException(status_code=404, detail={"error": "integration_client_not_found"})
    return client.to_dict()


@router.get("/{client_key}/audit")
def list_integration_client_audit(
    client_key: str,
    limit: int = Query(default=100, ge=1, le=200),
    db_session: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """读取单个客户端不含凭证机密的生命周期审计记录。"""
    client = IntegrationClientService.get(db_session, client_key)
    if client is None:
        raise HTTPException(status_code=404, detail={"error": "integration_client_not_found"})
    logs = (
        db_session.query(SecurityLog)
        .filter_by(resource_type="integration_client", resource_id=client.id)
        .order_by(SecurityLog.created_at.desc(), SecurityLog.id.desc())
        .limit(limit)
        .all()
    )
    return {"items": [log.to_dict() for log in logs]}


@router.get("/{client_key}/data-inventory")
def get_integration_client_data_inventory(
    client_key: str,
    db_session: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """返回一份 PHI 安全（不含 PHI 内容）的本地数据清单；无内容或破坏性动作。"""
    client = IntegrationClientService.get(db_session, client_key)
    if client is None:
        raise HTTPException(status_code=404, detail={"error": "integration_client_not_found"})

    # 列投影而非完整实体：避免把 metadata_json 等潜在 PHI 载荷加载进内存，
    # 大租户下也只传输聚合所需的少量列。
    launch_rows = (
        db_session.query(
            AgentTeamsLaunch.agentteams_conversation_id,
            AgentTeamsLaunch.agentteams_leader_session_id,
            AgentTeamsLaunch.status,
            AgentTeamsLaunch.source_patient_id,
        )
        .filter_by(integration_client_key=client.client_key)
        .all()
    )
    launch_count = len(launch_rows)
    conversation_ids = [row[0] for row in launch_rows if row[0] is not None]
    session_ids = [row[1] for row in launch_rows if row[1] is not None]

    status_counts: dict[str, int] = {}
    for row in launch_rows:
        status_counts[row[2] or 'created'] = status_counts.get(row[2] or 'created', 0) + 1

    conversation_count = (
        db_session.query(Conversation)
        .filter(Conversation.id.in_(conversation_ids))
        .count()
        if conversation_ids else 0
    )
    message_count = (
        db_session.query(Message)
        .filter(Message.conversation_id.in_(conversation_ids))
        .count()
        if conversation_ids else 0
    )
    leader_session_count = (
        db_session.query(LeaderSession)
        .filter(LeaderSession.id.in_(session_ids))
        .count()
        if session_ids else 0
    )
    token_count = db_session.query(AgentTeamsEmbedToken).filter_by(
        integration_client_key=client.client_key
    ).count()
    access_operation_count = db_session.query(IntegrationAccessOperation).filter_by(
        client_key=client.client_key,
        action='integration_client_revoke_embed_access',
    ).count()
    security_audit_count = db_session.query(SecurityLog).filter_by(
        resource_type='integration_client',
        resource_id=client.id,
    ).count()

    def category(
        count: int,
        *,
        classification: str,
        retention_basis: str,
        access_revoke: str = 'not_applicable',
    ) -> dict:
        """Return only governance metadata; never project a record payload."""
        return {
            'count': count,
            'source': 'agentteams',
            'owner': {
                'type': 'integration_client',
                'client_key': client.client_key,
            },
            'content_classification': classification,
            'contains_phi_content': bool(count) and classification in {
                'possible_phi',
                'phi_content',
                'operator_metadata_with_possible_phi',
            },
            'retention_basis': retention_basis,
            'actions': {
                'access_revoke': access_revoke,
                'local_delete': 'not_implemented',
                'local_anonymize': 'not_implemented',
                'remote_delete': 'not_implemented',
                'remote_anonymize': 'not_implemented',
            },
        }

    launch_contains_possible_phi = any(bool(row[3]) for row in launch_rows)
    if launch_contains_possible_phi:
        launch_classification = 'possible_phi'
    else:
        launch_classification = 'external_reference'

    return {
        "client_key": client.client_key,
        "source": "agentteams",
        "ownership": {
            "type": "integration_client",
            "client_key": client.client_key,
            "query_boundary": "exact client_key match",
        },
        "contains_phi_content": bool(
            launch_contains_possible_phi or conversation_count or message_count or leader_session_count
        ),
        "destructive_actions": {
            "remote_delete": "not_implemented",
            "local_delete": "not_implemented",
            "local_anonymize": "not_implemented",
            "remote_anonymize": "not_implemented",
            "retention_policy": "not_implemented",
            "manual_review_required": True,
        },
        "categories": {
            "launch_records": {
                **category(
                    launch_count,
                    classification=launch_classification,
                    retention_basis='idempotency_and_reconciliation',
                ),
                "status_counts": status_counts,
            },
            "conversations": category(
                conversation_count,
                classification='phi_content',
                retention_basis='workflow_and_user_record',
            ),
            "messages": category(
                message_count,
                classification='phi_content',
                retention_basis='workflow_and_user_record',
            ),
            "leader_sessions": category(
                leader_session_count,
                classification='phi_content',
                retention_basis='workflow_and_user_record',
            ),
            "embed_tokens": category(
                token_count,
                classification='access_metadata',
                retention_basis='short_lived_access_control',
                access_revoke='available',
            ),
            "access_operations": category(
                access_operation_count,
                classification='governance_metadata',
                retention_basis='access_governance_audit',
            ),
            "security_audit_records": category(
                security_audit_count,
                classification='operator_metadata_with_possible_phi',
                retention_basis='security_audit',
            ),
        },
    }


@router.post("/{client_key}/embed-tokens/revoke")
def revoke_integration_client_embed_access(
    client_key: str,
    request: IntegrationClientEmbedRevokeRequest,
    db_session: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """撤销某个客户端所属启动的本地嵌入访问。

    此端点刻意不删除本地记录，也不调用远程 AgentTeams 删除 API；
    这些破坏性契约仍未定义。
    """
    client = IntegrationClientService.get(db_session, client_key)
    if client is None:
        raise HTTPException(status_code=404, detail={"error": "integration_client_not_found"})
    if client.adapter_key != "agentteams":
        raise HTTPException(
            status_code=501,
            detail={
                "error": "integration_access_revoke_unavailable",
                "message": "Integration adapter does not support local embed access revocation",
            },
        )

    try:
        result = revoke_agentteams_embed_access(
            db_session,
            client_key=client.client_key,
            request_id=request.request_id,
            operation_id=request.operation_id,
            reason=request.reason,
        )
        _audit(
            db_session,
            admin,
            action="integration_client_revoke_embed_access",
            client=client,
            details={
                "request_id": result["request_id"],
                "operation_id": result["operation_id"],
                "reason": request.reason,
                "revoked_count": result["revoked_count"],
                "remote_action": result["remote_action"],
            },
        )
        db_session.commit()
        return result
    except AgentTeamsLaunchError as error:
        db_session.rollback()
        raise HTTPException(
            status_code=error.status_code,
            detail={"error": error.error_code, "message": error.message},
        )


@router.get("/{client_key}/embed-tokens/revoke")
def list_integration_client_embed_revoke_operations(
    client_key: str,
    limit: int = Query(default=100, ge=1, le=200),
    operation_status: str | None = Query(default=None, alias="status", min_length=1, max_length=30),
    db_session: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """列出客户端作用域内的本地访问撤销操作，无副作用。"""
    client = IntegrationClientService.get(db_session, client_key)
    if client is None:
        raise HTTPException(status_code=404, detail={"error": "integration_client_not_found"})
    if client.adapter_key != "agentteams":
        raise HTTPException(
            status_code=501,
            detail={
                "error": "integration_access_revoke_unavailable",
                "message": "Integration adapter does not support local embed access revocation",
            },
        )
    try:
        return {
            "items": list_embed_revoke_operations(
                db_session,
                client_key=client.client_key,
                limit=limit,
                status=operation_status,
            ),
        }
    except AgentTeamsLaunchError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"error": error.error_code, "message": error.message},
        )


@router.get("/{client_key}/embed-tokens/revoke/{operation_id}")
def get_integration_client_embed_revoke_operation(
    client_key: str,
    operation_id: str,
    db_session: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """读取一个客户端作用域内的本地访问撤销操作。"""
    client = IntegrationClientService.get(db_session, client_key)
    if client is None:
        raise HTTPException(status_code=404, detail={"error": "integration_client_not_found"})
    if client.adapter_key != "agentteams":
        raise HTTPException(
            status_code=501,
            detail={
                "error": "integration_access_revoke_unavailable",
                "message": "Integration adapter does not support local embed access revocation",
            },
        )
    try:
        return get_embed_revoke_operation(
            db_session,
            client_key=client.client_key,
            operation_id=operation_id,
        )
    except AgentTeamsLaunchError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"error": error.error_code, "message": error.message},
        )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_integration_client(
    request: IntegrationClientCreateRequest,
    db_session: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    try:
        client, plaintext_key = IntegrationClientService.create_client(
            db_session,
            client_key=request.client_key,
            adapter_key=request.adapter_key,
            display_name=request.display_name,
            service_account_id=request.service_account_id,
            capabilities=request.capabilities,
        )
        _audit(
            db_session,
            admin,
            action="integration_client_create",
            client=client,
            details={"adapter_key": client.adapter_key, "reason": request.reason},
        )
        db_session.commit()
        return {"client": client.to_dict(), "generated_integration_key": plaintext_key}
    except IntegrationClientError as error:
        db_session.rollback()
        _raise_client_error(error)
    except IntegrityError:
        db_session.rollback()
        raise HTTPException(
            status_code=409,
            detail={"error": "integration_client_exists", "message": "Integration client already exists"},
        )


@router.put("/{client_key}/enabled")
def set_integration_client_enabled(
    client_key: str,
    request: IntegrationClientEnabledRequest,
    db_session: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    try:
        client = IntegrationClientService.set_enabled(
            db_session, client_key=client_key, enabled=request.enabled
        )
        _audit(
            db_session,
            admin,
            action="integration_client_enable" if client.enabled else "integration_client_disable",
            client=client,
            details={"enabled": client.enabled, "reason": request.reason},
        )
        db_session.commit()
        return client.to_dict()
    except IntegrationClientError as error:
        db_session.rollback()
        _raise_client_error(error)


@router.post("/{client_key}/rotate-key")
def rotate_integration_client_key(
    client_key: str,
    request: IntegrationClientRotateKeyRequest,
    db_session: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    try:
        client, plaintext_key = IntegrationClientService.rotate_key(
            db_session,
            client_key=client_key,
            rotation_window_seconds=request.rotation_window_seconds,
        )
        _audit(
            db_session,
            admin,
            action="integration_client_rotate_key",
            client=client,
            details={
                "rotation_window_seconds": request.rotation_window_seconds,
                "reason": request.reason,
            },
        )
        db_session.commit()
        return {"client": client.to_dict(), "generated_integration_key": plaintext_key}
    except IntegrationClientError as error:
        db_session.rollback()
        _raise_client_error(error)
