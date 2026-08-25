"""Agent Teams 集成管理 API。"""

import hashlib
import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.deps import get_admin_user
from database import get_db
from models import SystemConfig, User
from services.agentteams_integration_account import (
    AGENTTEAMS_INTEGRATION_ENABLED,
    AGENTTEAMS_SERVICE_ACCOUNT_USERNAME,
    DEFAULT_SERVICE_ACCOUNT_USERNAME,
    ensure_agentteams_service_account,
    get_agentteams_capacity,
)
from services.integration_client_service import IntegrationClientService
from services.agentteams_integration_launch import (
    AGENTTEAMS_EMBED_TOKEN_TTL_SECONDS,
    AGENTTEAMS_INTEGRATION_KEY,
    DEFAULT_EMBED_TOKEN_TTL_SECONDS,
)
from utils.time_utils import utcnow_naive


router = APIRouter(tags=["admin-agentteams-integration"])


class AgentTeamsIntegrationUpdateRequest(BaseModel):
    enabled: bool = True
    integration_key: str = Field(default="")
    # These are deployment/advanced settings.  Keep them optional so the
    # normal connection form cannot accidentally reset an existing value when
    # it only submits enabled + integration_key.
    embed_token_ttl_seconds: int | None = Field(default=None, ge=60)
    service_account_username: str | None = Field(default=None, min_length=1, max_length=100)


def _get_config(db_session: Session, key: str, default: str = "") -> str:
    row = db_session.query(SystemConfig).filter_by(key=key).first()
    if row is None or row.value is None:
        return default
    return str(row.value)


def _set_config(db_session: Session, key: str, value: str, description: str) -> None:
    row = db_session.query(SystemConfig).filter_by(key=key).first()
    if row is None:
        db_session.add(SystemConfig(key=key, value=value, description=description))
    else:
        row.value = value
        row.description = row.description or description
        row.updated_at = utcnow_naive()


def _hash_key(integration_key: str) -> str:
    digest = hashlib.sha256(integration_key.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _mask_key(stored_value: str) -> str:
    value = (stored_value or "").strip()
    if not value:
        return ""
    if value.startswith("sha256:"):
        digest = value.removeprefix("sha256:")
        return f"sha256:{digest[:8]}...{digest[-6:]}"
    if len(value) <= 8:
        return "****"
    return f"{value[:3]}****{value[-4:]}"


def _snapshot(db_session: Session, generated_key: str | None = None) -> dict:
    stored_key = _get_config(db_session, AGENTTEAMS_INTEGRATION_KEY, "").strip()
    capacity = get_agentteams_capacity(db_session)
    return {
        "enabled": _get_config(db_session, AGENTTEAMS_INTEGRATION_ENABLED, "true").strip().lower()
        in {"1", "true", "yes", "on"},
        "has_integration_key": bool(stored_key),
        "integration_key_masked": _mask_key(stored_key),
        "generated_integration_key": generated_key or "",
        "embed_token_ttl_seconds": int(
            _get_config(db_session, AGENTTEAMS_EMBED_TOKEN_TTL_SECONDS, str(DEFAULT_EMBED_TOKEN_TTL_SECONDS))
        ),
        "service_account_username": _get_config(
            db_session,
            AGENTTEAMS_SERVICE_ACCOUNT_USERNAME,
            DEFAULT_SERVICE_ACCOUNT_USERNAME,
        ),
        "capacity": capacity,
    }


@router.get("/agentteams-integration")
def get_agentteams_integration_config(
    db_session: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """读取 Agent Teams 集成配置，不暴露明文密钥。"""
    return _snapshot(db_session)


@router.put("/agentteams-integration")
def update_agentteams_integration_config(
    request: AgentTeamsIntegrationUpdateRequest,
    db_session: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """更新 Agent Teams 集成配置，并确保服务账户存在。"""
    key = request.integration_key.strip()
    if key and not key.startswith("****"):
        _set_config(db_session, AGENTTEAMS_INTEGRATION_KEY, _hash_key(key), "Agent Teams 集成密钥哈希")

    _set_config(db_session, AGENTTEAMS_INTEGRATION_ENABLED, "true" if request.enabled else "false", "Agent Teams 集成开关")
    if request.embed_token_ttl_seconds is not None:
        _set_config(
            db_session,
            AGENTTEAMS_EMBED_TOKEN_TTL_SECONDS,
            str(request.embed_token_ttl_seconds),
            "Agent Teams 嵌入令牌有效期（秒）",
        )
    if request.service_account_username is not None:
        _set_config(
            db_session,
            AGENTTEAMS_SERVICE_ACCOUNT_USERNAME,
            request.service_account_username.strip(),
            "Agent Teams 服务账户用户名",
        )

    service_account = ensure_agentteams_service_account(db_session)
    IntegrationClientService.sync_agentteams_client(db_session, service_account.id)
    db_session.commit()
    return _snapshot(db_session)


@router.post("/agentteams-integration/generate-key")
def generate_agentteams_integration_key(
    db_session: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """生成新的集成密钥，仅存储其哈希，并一次性返回明文。"""
    generated_key = f"op_{secrets.token_urlsafe(32)}"
    _set_config(db_session, AGENTTEAMS_INTEGRATION_KEY, _hash_key(generated_key), "Agent Teams 集成密钥哈希")
    _set_config(db_session, AGENTTEAMS_INTEGRATION_ENABLED, "true", "Agent Teams 集成开关")
    service_account = ensure_agentteams_service_account(db_session)
    IntegrationClientService.sync_agentteams_client(db_session, service_account.id)
    db_session.commit()
    return _snapshot(db_session, generated_key=generated_key)
