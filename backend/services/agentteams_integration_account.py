"""Agent Teams 集成服务账户原语。"""
import logging
import secrets

from sqlalchemy.orm import Session

from models import SystemConfig, User
from utils.time_utils import utcnow_naive


logger = logging.getLogger(__name__)

AGENTTEAMS_INTEGRATION_ENABLED = 'AGENTTEAMS_INTEGRATION_ENABLED'
AGENTTEAMS_SERVICE_ACCOUNT_USERNAME = 'AGENTTEAMS_SERVICE_ACCOUNT_USERNAME'

DEFAULT_SERVICE_ACCOUNT_USERNAME = 'agentteams-service'


def _get_config_value(db_session: Session, key: str, default: str) -> str:
    config = db_session.query(SystemConfig).filter_by(key=key).first()
    if not config or config.value is None:
        return default
    return str(config.value)


def _parse_bool(value: str) -> bool:
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


def get_agentteams_service_account_username(db_session: Session) -> str:
    username = _get_config_value(
        db_session,
        AGENTTEAMS_SERVICE_ACCOUNT_USERNAME,
        DEFAULT_SERVICE_ACCOUNT_USERNAME,
    ).strip()
    return username or DEFAULT_SERVICE_ACCOUNT_USERNAME


def ensure_agentteams_service_account(db_session: Session) -> User:
    """创建或规范化 Agent Teams 服务账户。

    服务账户只承载集成创建会话的数据归属，不可普通登录、不拥有
    admin 权限；开源自部署下不再有任何余额/计量概念。
    """
    username = get_agentteams_service_account_username(db_session)

    user = db_session.query(User).filter_by(username=username).first()
    created = False
    if user is None:
        user = User(
            username=username,
            email=None,
            account_type='service',
            login_disabled=True,
            is_admin=False,
            role='viewer',
        )
        user.set_password(secrets.token_urlsafe(48))
        db_session.add(user)
        db_session.flush()
        created = True
    elif user.account_type != 'service' or not user.login_disabled:
        user.token_version += 1

    user.account_type = 'service'
    user.login_disabled = True
    user.is_admin = False
    user.role = 'viewer'

    db_session.flush()
    logger.info(
        "Agent Teams service account %s: user_id=%s username=%s",
        "created" if created else "ensured",
        user.id,
        user.username,
    )
    return user


def resolve_agentteams_service_account(db_session: Session) -> User | None:
    """解析已配置的 Agent Teams 服务账户，而不实际创建它。"""
    username = get_agentteams_service_account_username(db_session)
    user = db_session.query(User).filter_by(username=username).first()
    if (
        not user
        or user.account_type != 'service'
        or not user.login_disabled
        or user.is_admin
    ):
        return None
    return user


def get_agentteams_capacity(db_session: Session) -> dict:
    """返回 Agent Teams 服务账户的状态（无余额概念）。"""
    enabled = _parse_bool(
        _get_config_value(db_session, AGENTTEAMS_INTEGRATION_ENABLED, 'true')
    )
    user = resolve_agentteams_service_account(db_session)
    if user is None:
        return {
            'configured': False,
            'enabled': enabled,
            'user_id': None,
            'username': None,
        }

    return {
        'configured': True,
        'enabled': enabled,
        'user_id': user.id,
        'username': user.username,
    }
