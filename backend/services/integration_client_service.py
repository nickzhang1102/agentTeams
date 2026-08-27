"""通用集成客户端的认证与策略查询。

该服务刻意不包含工作流副作用。它仅负责认证调用方，
并返回启动适配器可能使用的、客户端所有的能力配置。
Agent Teams 遗留的 SystemConfig 键在迁移窗口期内仍然作为
只读回退；新客户端必须在 ``integration_clients`` 表中注册。
"""

from dataclasses import dataclass
from datetime import timedelta
import hashlib
import logging
import re
import secrets

from sqlalchemy.orm import Session

from models import IntegrationClient, User, SystemConfig
from services.agentteams_integration_account import (
    AGENTTEAMS_INTEGRATION_ENABLED,
    resolve_agentteams_service_account,
)
from utils.time_utils import utcnow_naive

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IntegrationClientContext:
    client_key: str
    adapter_key: str
    display_name: str
    enabled: bool
    service_account_id: int | None
    capabilities: dict
    legacy_fallback: bool = False


class IntegrationClientError(Exception):
    def __init__(self, status_code: int, error_code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.message = message


def hash_integration_key(value: str) -> str:
    return hashlib.sha256(str(value).encode('utf-8')).hexdigest()


def _credential_matches(expected: str, supplied: str) -> bool:
    """仅接受 ``sha256:`` 前缀的哈希凭证（fail-closed）。

    明文遗留值不再被接受：认证直接失败并提示运维轮换为哈希存储。
    """
    if not expected or not supplied:
        return False
    if not expected.startswith('sha256:'):
        logger.warning(
            "Integration credential is stored in plaintext; rotate it to 'sha256:<hex>'"
        )
        return False
    return secrets.compare_digest(
        expected.removeprefix('sha256:'), hash_integration_key(supplied)
    )


def _get_config_value(db_session: Session, key: str, default: str = '') -> str:
    row = db_session.query(SystemConfig).filter_by(key=key).first()
    return str(row.value) if row and row.value is not None else default


def _parse_bool(value: str) -> bool:
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


class IntegrationClientService:
    """认证外部客户端，而无需耦合到工作流。"""

    _CLIENT_KEY_PATTERN = re.compile(r'^[a-z][a-z0-9_-]{1,49}$')
    MAX_ROTATION_WINDOW_SECONDS = 7 * 24 * 60 * 60

    @staticmethod
    def get(db_session: Session, client_key: str) -> IntegrationClient | None:
        return db_session.query(IntegrationClient).filter_by(
            client_key=str(client_key or '').strip()
        ).one_or_none()

    @classmethod
    def is_enabled_for_embed_access(cls, db_session: Session, client_key: str) -> bool:
        """返回已颁发（already-issued）的本地嵌入访问是否可使用。

        嵌入请求不携带集成凭证，因此无法使用 ``authenticate``。它们仍
        继承客户端生命周期边界：已注册的客户端会被直接检查，而遗留的
        Agent Teams 客户端回退到其现有的集成启用标志。未知的非遗留客户端
        采用失败关闭（fail closed）策略。
        """
        normalized = str(client_key or '').strip()
        if not normalized:
            return False
        client = cls.get(db_session, normalized)
        if client is not None:
            return bool(client.enabled)
        if normalized != 'agentteams':
            return False
        return _parse_bool(_get_config_value(db_session, AGENTTEAMS_INTEGRATION_ENABLED, 'true'))

    @classmethod
    def _require_safe_service_account(cls, db_session: Session, service_account_id: int) -> User:
        service_account = db_session.get(User, service_account_id)
        if (
            service_account is None
            or service_account.account_type != 'service'
            or not service_account.login_disabled
            or service_account.is_admin
        ):
            raise IntegrationClientError(
                422,
                'unsafe_service_account',
                'Integration service account must be a non-admin disabled-login service account',
            )
        return service_account

    @classmethod
    def _validate_key(cls, value: str, field: str) -> str:
        normalized = str(value or '').strip()
        if not cls._CLIENT_KEY_PATTERN.fullmatch(normalized):
            raise IntegrationClientError(
                422,
                'invalid_integration_client',
                f'{field} must be 2-50 lowercase letters, digits, underscores, or hyphens',
            )
        return normalized

    @staticmethod
    def _new_plaintext_key() -> str:
        return f'ik_{secrets.token_urlsafe(32)}'

    @staticmethod
    def _hash_key(value: str) -> str:
        return f'sha256:{hash_integration_key(value)}'

    @classmethod
    def create_client(
        cls,
        db_session: Session,
        *,
        client_key: str,
        adapter_key: str,
        display_name: str,
        service_account_id: int,
        capabilities: dict | None = None,
    ) -> tuple[IntegrationClient, str]:
        normalized_client_key = cls._validate_key(client_key, 'client_key')
        if normalized_client_key == 'agentteams':
            raise IntegrationClientError(
                409,
                'legacy_client_managed_separately',
                'The Agent Teams compatibility client is managed by the legacy integration configuration',
            )
        normalized_adapter_key = cls._validate_key(adapter_key, 'adapter_key')
        if not str(display_name or '').strip():
            raise IntegrationClientError(422, 'invalid_integration_client', 'display_name is required')
        if cls.get(db_session, normalized_client_key) is not None:
            raise IntegrationClientError(409, 'integration_client_exists', 'Integration client already exists')
        cls._require_safe_service_account(db_session, service_account_id)
        plaintext_key = cls._new_plaintext_key()
        client = IntegrationClient(
            client_key=normalized_client_key,
            adapter_key=normalized_adapter_key,
            display_name=str(display_name).strip(),
            credential_hash=cls._hash_key(plaintext_key),
            service_account_id=service_account_id,
            enabled=True,
            capabilities_json=dict(capabilities or {'launch': True}),
        )
        db_session.add(client)
        db_session.flush()
        return client, plaintext_key

    @classmethod
    def set_enabled(
        cls,
        db_session: Session,
        *,
        client_key: str,
        enabled: bool,
    ) -> IntegrationClient:
        client = db_session.query(IntegrationClient).filter_by(
            client_key=str(client_key or '').strip()
        ).with_for_update().one_or_none()
        if client is None:
            raise IntegrationClientError(404, 'integration_client_not_found', 'Integration client was not found')
        if client.client_key == 'agentteams':
            raise IntegrationClientError(
                409,
                'legacy_client_managed_separately',
                'The Agent Teams compatibility client is managed by the legacy integration configuration',
            )
        if enabled:
            cls._require_safe_service_account(db_session, client.service_account_id or 0)
        client.enabled = bool(enabled)
        client.updated_at = utcnow_naive()
        db_session.flush()
        return client

    @classmethod
    def rotate_key(
        cls,
        db_session: Session,
        *,
        client_key: str,
        rotation_window_seconds: int,
    ) -> tuple[IntegrationClient, str]:
        if not 0 <= rotation_window_seconds <= cls.MAX_ROTATION_WINDOW_SECONDS:
            raise IntegrationClientError(
                422,
                'invalid_rotation_window',
                f'rotation_window_seconds must be between 0 and {cls.MAX_ROTATION_WINDOW_SECONDS}',
            )
        client = db_session.query(IntegrationClient).filter_by(
            client_key=str(client_key or '').strip()
        ).with_for_update().one_or_none()
        if client is None:
            raise IntegrationClientError(404, 'integration_client_not_found', 'Integration client was not found')
        if client.client_key == 'agentteams':
            raise IntegrationClientError(
                409,
                'legacy_client_managed_separately',
                'The Agent Teams compatibility client is managed by the legacy integration configuration',
            )
        cls._require_safe_service_account(db_session, client.service_account_id or 0)
        plaintext_key = cls._new_plaintext_key()
        prior_hash = str(client.credential_hash or '').strip()
        client.credential_hash = cls._hash_key(plaintext_key)
        if prior_hash and rotation_window_seconds:
            client.previous_credential_hash = prior_hash
            client.previous_credential_expires_at = utcnow_naive() + timedelta(seconds=rotation_window_seconds)
        else:
            client.previous_credential_hash = None
            client.previous_credential_expires_at = None
        client.updated_at = utcnow_naive()
        db_session.flush()
        return client, plaintext_key

    @classmethod
    def authenticate(
        cls,
        db_session: Session,
        client_key: str,
        supplied_key: str | None,
    ) -> IntegrationClientContext:
        normalized = str(client_key or '').strip()
        if not normalized:
            raise IntegrationClientError(400, 'invalid_client', 'client_key is required')

        client = cls.get(db_session, normalized)
        if client is None:
            # 兼容性说明：Agent Teams 在 IntegrationClient 出现之前就已配置。
            # 此路径绝不会创建记录。
            if normalized != 'agentteams':
                raise IntegrationClientError(401, 'invalid_integration_key', 'Invalid integration key')
            expected = _get_config_value(db_session, 'AGENTTEAMS_INTEGRATION_KEY', '').strip()
            supplied = str(supplied_key or '').strip()
            valid = False
            if expected and supplied:
                valid = _credential_matches(expected, supplied)
            if not valid:
                raise IntegrationClientError(401, 'invalid_integration_key', 'Invalid integration key')
            service_account = resolve_agentteams_service_account(db_session)
            if service_account is None:
                raise IntegrationClientError(403, 'service_account_not_configured', 'Agent Teams service account is not configured')
            return IntegrationClientContext(
                client_key='agentteams',
                adapter_key='agentteams',
                display_name='Agent Teams',
                enabled=_parse_bool(_get_config_value(db_session, AGENTTEAMS_INTEGRATION_ENABLED, 'true')),
                service_account_id=service_account.id,
                capabilities={
                    'launch': True,
                    'status_query': True,
                    'reconcile': True,
                },
                legacy_fallback=True,
            )

        expected = str(client.credential_hash or '').strip()
        supplied = str(supplied_key or '').strip()
        previous_valid = (
            bool(client.previous_credential_hash)
            and client.previous_credential_expires_at is not None
            and client.previous_credential_expires_at > utcnow_naive()
            and _credential_matches(str(client.previous_credential_hash), supplied)
        )
        if not _credential_matches(expected, supplied) and not previous_valid:
            raise IntegrationClientError(401, 'invalid_integration_key', 'Invalid integration key')
        if not client.enabled:
            raise IntegrationClientError(403, 'integration_disabled', 'Integration is disabled')
        service_account = (
            db_session.get(User, client.service_account_id)
            if client.service_account_id is not None
            else None
        )
        if (
            service_account is None
            or service_account.account_type != 'service'
            or not service_account.login_disabled
            or service_account.is_admin
        ):
            raise IntegrationClientError(
                403,
                'service_account_not_configured',
                'Integration service account is not configured',
            )
        return IntegrationClientContext(
            client_key=client.client_key,
            adapter_key=client.adapter_key or '',
            display_name=client.display_name,
            enabled=client.enabled,
            service_account_id=client.service_account_id,
            capabilities=client.capabilities_json or {},
        )

    @classmethod
    def sync_agentteams_client(
        cls,
        db_session: Session,
        service_account_id: int,
    ) -> IntegrationClient:
        """在管理员配置变更后创建/更新兼容客户端。"""
        client = cls.get(db_session, 'agentteams')
        if client is None:
            client = IntegrationClient(
                client_key='agentteams',
                adapter_key='agentteams',
                display_name='Agent Teams',
                capabilities_json={
                    'launch': True,
                    'status_query': True,
                    'reconcile': True,
                },
            )
            db_session.add(client)
        # Normalize legacy rows so removed capabilities cannot survive an
        # upgrade and accidentally re-enable a retired endpoint.
        client.capabilities_json = {
            'launch': True,
            'status_query': True,
            'reconcile': True,
        }
        configured_key = _get_config_value(
            db_session, 'AGENTTEAMS_INTEGRATION_KEY', ''
        ).strip()
        if configured_key and not configured_key.startswith('sha256:'):
            configured_key = f'sha256:{hash_integration_key(configured_key)}'
        client.credential_hash = configured_key or None
        # 遗留管理路径会原子地替换活动凭证；
        # 替换之后，绝不要让先前生命周期操作产生的轮换密钥仍然有效。
        client.previous_credential_hash = None
        client.previous_credential_expires_at = None
        client.service_account_id = service_account_id
        client.enabled = _parse_bool(_get_config_value(db_session, AGENTTEAMS_INTEGRATION_ENABLED, 'true'))
        client.updated_at = utcnow_naive()
        db_session.flush()
        return client
