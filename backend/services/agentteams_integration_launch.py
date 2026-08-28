"""Agent Teams 启动与嵌入会话原语。"""
import asyncio
import contextvars
import copy
import hashlib
import json
import logging
import secrets
from datetime import timedelta
from typing import Any, AsyncGenerator, Callable

from sqlalchemy import and_, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config import Config
from context.context_builder import ContextBuilder
from db import SessionLocal
from leader.langgraph_entry import async_run_leader_workflow
from leader.leader_persistence import create_leader_session, mark_session_failed
from models import (
    Conversation,
    IntegrationAccessOperation,
    LeaderAgentResult,
    LeaderFinalReport,
    LeaderSession,
    Message,
    AgentTeamsEmbedToken,
    AgentTeamsLaunch,
    ToolCallLog,
    SystemConfig,
    User,
)
from services.agentteams_integration_account import (
    AGENTTEAMS_INTEGRATION_ENABLED,
    resolve_agentteams_service_account,
)
from services.integration_client_service import (
    IntegrationClientContext,
    IntegrationClientService,
)
from utils.time_utils import utcnow_naive


logger = logging.getLogger(__name__)

AGENTTEAMS_INTEGRATION_KEY = 'AGENTTEAMS_INTEGRATION_KEY'
AGENTTEAMS_EMBED_TOKEN_TTL_SECONDS = 'AGENTTEAMS_EMBED_TOKEN_TTL_SECONDS'

DEFAULT_EMBED_TOKEN_TTL_SECONDS = 3600
EMBED_TOKEN_RETENTION_SECONDS = 86400
EMBED_TOKEN_CLEANUP_BATCH_SIZE = 100
EMBED_LAST_USED_WRITE_INTERVAL_SECONDS = 300
AGENTTEAMS_SOURCE = 'agentteams'
# 启动载荷上限：message 允许长文本（会诊材料）但封顶；metadata 按序列化后体积限制
AGENTTEAMS_MESSAGE_MAX_LENGTH = 100_000
AGENTTEAMS_METADATA_MAX_LENGTH = 20_000
INTEGRATION_REVOKE_ACTION = 'integration_client_revoke_embed_access'
# 外部契约上限：generic 与遗留路由的调用方可见 request-id 长度。
EXTERNAL_REQUEST_ID_MAX_LENGTH = 100
# 存储列宽：外部 ID 加 client 命名空间前缀（client_key ≤50 + 分隔符）。
REQUEST_ID_STORAGE_MAX_LENGTH = 200
AGENTTEAMS_SUPPORTED_LOCALES = {'zh-CN', 'en-US'}

# 集成协议契约 v1（本地镜像见 oncopath app/services/agentteams_contract.py）：
# 版本握手 + 限额宣告 + 规范状态集。调用方通过 capabilities 端点获取运行时事实。
INTEGRATION_PROTOCOL_VERSION = 1
MIN_INTEGRATION_PROTOCOL_VERSION = 1
LAUNCH_REF_MAX_LENGTH = 100
LAUNCH_TITLE_MAX_LENGTH = 500
# 规范状态集：launch/status 对外可见状态；not_found 仅出现在查询响应中。
INTEGRATION_STATUSES = ['created', 'running', 'completed', 'failed', 'stopped', 'not_found']
# 契约内错误码（admins 管理面错误码不在此列，见 docs/deployment/integration-clients.md）。
INTEGRATION_ERROR_CODES = [
    'invalid_integration_key',
    'invalid_client',
    'invalid_payload',
    'integration_client_not_found',
    'integration_capability_disabled',
    'integration_disabled',
    'service_account_not_configured',
    'integration_adapter_unavailable',
    'idempotency_conflict',
    'unsupported_version',
    'invalid_embed_token',
    'embed_session_not_found',
    'agentteams_launch_not_found',
    'agentteams_launch_failed',
    'agentteams_launch_stopped',
]
INTEGRATION_LIMITS = {
    'message_max_length': AGENTTEAMS_MESSAGE_MAX_LENGTH,
    'metadata_max_length': AGENTTEAMS_METADATA_MAX_LENGTH,
    'request_id_max_length': EXTERNAL_REQUEST_ID_MAX_LENGTH,
    'title_max_length': LAUNCH_TITLE_MAX_LENGTH,
    'ref_max_length': LAUNCH_REF_MAX_LENGTH,
    'min_message_length': 1,
}


def check_integration_protocol_version(declared: str | None) -> None:
    """版本握手：声明版本超出本部署支持范围时抛 426 unsupported_version。

    缺失或空值视为当前版本，兼容尚未接入版本握手的旧调用方。
    """
    if declared is None or not str(declared).strip():
        return
    raw = str(declared).strip()
    try:
        version = int(raw)
    except (TypeError, ValueError):
        raise AgentTeamsLaunchError(
            400,
            'invalid_payload',
            'X-Integration-Protocol-Version must be an integer',
        )
    if version > INTEGRATION_PROTOCOL_VERSION or version < MIN_INTEGRATION_PROTOCOL_VERSION:
        raise AgentTeamsLaunchError(
            426,
            'unsupported_version',
            f'Integration protocol version {raw} is not supported '
            f'(supported range {MIN_INTEGRATION_PROTOCOL_VERSION}-{INTEGRATION_PROTOCOL_VERSION})',
        )


def build_integration_capabilities(client) -> dict[str, Any]:
    """宣告协议版本、能力、限额与词表（契约 v1 的运行时单一事实源）。

    ``client`` 是已认证的 IntegrationClientContext；本函数不触碰数据库。
    """
    return {
        'protocol_version': INTEGRATION_PROTOCOL_VERSION,
        'min_protocol_version': MIN_INTEGRATION_PROTOCOL_VERSION,
        'api_version': 'v1',
        'capabilities': dict(getattr(client, 'capabilities', None) or {}),
        'limits': dict(INTEGRATION_LIMITS),
        'locales': sorted(AGENTTEAMS_SUPPORTED_LOCALES),
        'statuses': list(INTEGRATION_STATUSES),
        'error_codes': list(INTEGRATION_ERROR_CODES),
        'client': {
            'client_key': client.client_key,
            'adapter_key': str(getattr(client, 'adapter_key', '') or ''),
            'display_name': getattr(client, 'display_name', ''),
            'enabled': bool(getattr(client, 'enabled', False)),
            'legacy_fallback': bool(getattr(client, 'legacy_fallback', False)),
        },
    }
AGENTTEAMS_TERMINAL_STATES = {'completed', 'failed', 'stopped'}
AGENTTEAMS_EMBED_EVENT_POLL_SECONDS = 1.0
AGENTTEAMS_EMBED_PROGRESS_KEY = '_embed_progress'
AGENTTEAMS_EMBED_PROGRESS_EVENT_TYPES = {
    'task_decomposition',
    'subtask_started',
    'subtask_completed',
    'task_adjusted',
    'agent_result',
    'agent_error',
}

_DECISION_STAGE_TO_EMBED_STATE = {
    'intake': 'assessing',
    'assessment': 'assessing',
    'team_form': 'forming_team',
    'execution': 'monitoring',
    'review': 'monitoring',
    'synthesis': 'summarizing',
    'persistence': 'summarizing',
}

LAUNCH_LEASE_SECONDS = max(Config.AGENTTEAMS_LAUNCH_LEASE_SECONDS, 30)
LAUNCH_HEARTBEAT_SECONDS = min(
    max(Config.AGENTTEAMS_LAUNCH_HEARTBEAT_SECONDS, 1),
    max(LAUNCH_LEASE_SECONDS // 3, 1),
)

_active_launch_tasks: set[asyncio.Task] = set()
_recovery_monitor_task: asyncio.Task | None = None


class AgentTeamsLaunchError(Exception):
    """预期的 Agent Teams 启动失败异常，携带 HTTP 语义。"""

    def __init__(self, status_code: int, error_code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.message = message


def agentteams_storage_request_id(request_id: str, client_key: str) -> str:
    """返回某个集成客户端的内部 request-id 命名空间。

    遗留的 ``agentteams`` 客户端保留其历史请求 ID。共享此适配器的其他
    客户端都会加前缀，避免相同的外部 ID 与其他租户的启动请求冲突。
    """
    normalized_request_id = str(request_id or '').strip()
    normalized_client_key = str(client_key or '').strip()
    if normalized_client_key == AGENTTEAMS_SOURCE:
        return normalized_request_id
    return f'{normalized_client_key}:{normalized_request_id}'


def default_embed_revoke_operation_id(client_key: str, request_id: str) -> str:
    """当调用方未提供时，派生出一个稳定的操作键。"""
    material = f'{client_key}\x00{request_id}'.encode('utf-8')
    return f'revoke_{hashlib.sha256(material).hexdigest()}'


def _launch_is_recoverable(launch: AgentTeamsLaunch, now=None) -> bool:
    now = now or utcnow_naive()
    return launch.status == 'created' or (
        launch.status == 'running'
        and (launch.lease_expires_at is None or launch.lease_expires_at <= now)
    )


def find_recoverable_agentteams_launch_ids(
    session_factory: Callable[[], Session] = SessionLocal,
) -> list[int]:
    """找出可被安全提交给租约感知工作器的启动请求。"""
    session = session_factory()
    try:
        now = utcnow_naive()
        return [
            launch_id
            for (launch_id,) in session.query(AgentTeamsLaunch.id).filter(
                or_(
                    AgentTeamsLaunch.status == 'created',
                    and_(
                        AgentTeamsLaunch.status == 'running',
                        or_(
                            AgentTeamsLaunch.lease_expires_at.is_(None),
                            AgentTeamsLaunch.lease_expires_at <= now,
                        ),
                    ),
                )
            ).order_by(AgentTeamsLaunch.id.asc()).all()
        ]
    finally:
        session.close()


def schedule_agentteams_launch(launch_id: int) -> asyncio.Task:
    """调度一个持久化启动；数据库租约始终作为所有权边界。"""
    task = asyncio.create_task(
        _run_agentteams_leader_workflow_async(launch_id, SessionLocal),
        name=f'agentteams-launch-{launch_id}',
    )
    _active_launch_tasks.add(task)
    task.add_done_callback(_active_launch_tasks.discard)
    return task


async def _monitor_recoverable_agent_teams_launches() -> None:
    while True:
        try:
            for launch_id in find_recoverable_agentteams_launch_ids():
                schedule_agentteams_launch(launch_id)
        except Exception:
            logger.warning("Agent Teams launch recovery scan failed", exc_info=True)
        await asyncio.sleep(LAUNCH_HEARTBEAT_SECONDS)


def start_agentteams_recovery_monitor() -> asyncio.Task:
    global _recovery_monitor_task
    if _recovery_monitor_task is not None and not _recovery_monitor_task.done():
        return _recovery_monitor_task
    _recovery_monitor_task = asyncio.create_task(
        _monitor_recoverable_agent_teams_launches(),
        name='agentteams-launch-recovery',
    )
    _active_launch_tasks.add(_recovery_monitor_task)
    _recovery_monitor_task.add_done_callback(_active_launch_tasks.discard)
    return _recovery_monitor_task


async def shutdown_agentteams_launch_tasks() -> None:
    global _recovery_monitor_task
    tasks = list(_active_launch_tasks)
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    _recovery_monitor_task = None


def renew_agentteams_launch_lease(
    launch_id: int,
    lease_owner: str,
    session_factory: Callable[[], Session] = SessionLocal,
) -> bool:
    """仅在租约归属者仍匹配时，续延运行中启动请求的租约。"""
    session = session_factory()
    try:
        now = utcnow_naive()
        updated = session.query(AgentTeamsLaunch).filter(
            AgentTeamsLaunch.id == launch_id,
            AgentTeamsLaunch.status == 'running',
            AgentTeamsLaunch.lease_owner == lease_owner,
        ).update(
            {
                AgentTeamsLaunch.heartbeat_at: now,
                AgentTeamsLaunch.lease_expires_at: now + timedelta(seconds=LAUNCH_LEASE_SECONDS),
            },
            synchronize_session=False,
        )
        session.commit()
        return updated == 1
    finally:
        session.close()


def _get_config_value(db_session: Session, key: str, default: str = '') -> str:
    config = db_session.query(SystemConfig).filter_by(key=key).first()
    if not config or config.value is None:
        return default
    return str(config.value)


def _parse_bool(value: str) -> bool:
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


def _parse_ttl_seconds(value: str) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return DEFAULT_EMBED_TOKEN_TTL_SECONDS
    return max(parsed, 60)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def _verify_integration_key(db_session: Session, supplied_key: str | None) -> None:
    expected = _get_config_value(db_session, AGENTTEAMS_INTEGRATION_KEY, '').strip()
    supplied = (supplied_key or '').strip()
    if not expected or not supplied:
        raise AgentTeamsLaunchError(401, 'invalid_integration_key', 'Invalid integration key')

    # 仅接受 sha256: 前缀的哈希配置（fail-closed）；明文遗留值一律拒绝并提示轮换
    if not expected.startswith('sha256:'):
        logger.warning("AGENTTEAMS integration key is stored in plaintext; rotate it to 'sha256:<hex>'")
        raise AgentTeamsLaunchError(401, 'invalid_integration_key', 'Invalid integration key')

    expected_hash = expected.removeprefix('sha256:')
    if not secrets.compare_digest(expected_hash, _hash_token(supplied)):
        raise AgentTeamsLaunchError(401, 'invalid_integration_key', 'Invalid integration key')


def _validate_launch_payload(payload: dict[str, Any], request_id: str | None) -> None:
    if not request_id or not request_id.strip():
        raise AgentTeamsLaunchError(400, 'invalid_payload', 'X-Request-Id is required')
    # 此处校验的是存储命名空间内的完整 ID（含 client 前缀）；
    # 外部契约上限由 API 层按 EXTERNAL_REQUEST_ID_MAX_LENGTH 把关。
    if len(request_id.strip()) > REQUEST_ID_STORAGE_MAX_LENGTH:
        raise AgentTeamsLaunchError(
            400,
            'invalid_payload',
            'X-Request-Id is too long',
        )
    if payload.get('source') not in (None, AGENTTEAMS_SOURCE):
        raise AgentTeamsLaunchError(400, 'invalid_payload', 'source must be agentteams')
    for field in ('source_user_id', 'source_patient_id', 'source_conversation_id'):
        value = payload.get(field)
        if value is not None and len(str(value)) > LAUNCH_REF_MAX_LENGTH:
            raise AgentTeamsLaunchError(
                400,
                'invalid_payload',
                f'{field} must be at most {LAUNCH_REF_MAX_LENGTH} characters',
            )
    if payload.get('title') is not None and len(str(payload.get('title'))) > LAUNCH_TITLE_MAX_LENGTH:
        raise AgentTeamsLaunchError(
            400,
            'invalid_payload',
            f'title must be at most {LAUNCH_TITLE_MAX_LENGTH} characters',
        )
    if not str(payload.get('message') or '').strip():
        raise AgentTeamsLaunchError(400, 'invalid_payload', 'message is required')
    if payload.get('source_conversation_id') in (None, ''):
        raise AgentTeamsLaunchError(400, 'invalid_payload', 'source_conversation_id is required')
    message_text = str(payload.get('message') or '')
    if len(message_text) > AGENTTEAMS_MESSAGE_MAX_LENGTH:
        raise AgentTeamsLaunchError(
            400,
            'invalid_payload',
            f'message must be at most {AGENTTEAMS_MESSAGE_MAX_LENGTH} characters',
        )
    metadata_payload = payload.get('metadata')
    if metadata_payload is not None:
        try:
            metadata_size = len(json.dumps(metadata_payload, ensure_ascii=False))
        except (TypeError, ValueError):
            raise AgentTeamsLaunchError(400, 'invalid_payload', 'metadata must be JSON-serializable')
        if metadata_size > AGENTTEAMS_METADATA_MAX_LENGTH:
            raise AgentTeamsLaunchError(
                400,
                'invalid_payload',
                f'metadata must be at most {AGENTTEAMS_METADATA_MAX_LENGTH} characters when serialized',
            )
    if payload.get('locale', 'zh-CN') not in AGENTTEAMS_SUPPORTED_LOCALES:
        raise AgentTeamsLaunchError(400, 'invalid_payload', 'locale must be zh-CN or en-US')


def _assert_idempotent_launch_matches(launch: AgentTeamsLaunch, payload: dict[str, Any]) -> None:
    """拒绝为不同的咨询请求复用同一个幂等键。"""
    expected_user_id = str(payload.get('source_user_id') or '')
    expected_patient_id = str(payload.get('source_patient_id') or '')
    stored_user_id = str(launch.source_user_id or '')
    stored_patient_id = str(launch.source_patient_id or '')

    leader_session = launch.leader_session
    conversation = launch.conversation
    stored_message = leader_session.user_message if leader_session is not None else None
    stored_locale = conversation.default_locale if conversation is not None else None
    expected_message = str(payload.get('message') or '')
    expected_locale = str(payload.get('locale') or 'zh-CN')

    if (
        stored_user_id != expected_user_id
        or stored_patient_id != expected_patient_id
        or stored_message != expected_message
        or stored_locale != expected_locale
    ):
        raise AgentTeamsLaunchError(
            409,
            'idempotency_conflict',
            'X-Request-Id was already used for a different consultation',
        )


def _create_embed_token(
    db_session: Session,
    conversation_id: int,
    leader_session_id: int | None,
    integration_client_key: str = AGENTTEAMS_SOURCE,
    auto_commit: bool = True,
    revoke_existing: bool = True,
) -> str:
    now = utcnow_naive()
    ttl_seconds = _parse_ttl_seconds(
        _get_config_value(
            db_session,
            AGENTTEAMS_EMBED_TOKEN_TTL_SECONDS,
            str(DEFAULT_EMBED_TOKEN_TTL_SECONDS),
        )
    )
    db_session.query(AgentTeamsEmbedToken).filter(
        AgentTeamsEmbedToken.conversation_id == conversation_id,
        AgentTeamsEmbedToken.source == AGENTTEAMS_SOURCE,
        AgentTeamsEmbedToken.integration_client_key == integration_client_key,
        (AgentTeamsEmbedToken.revoked_at.isnot(None))
        | (AgentTeamsEmbedToken.expires_at <= now),
    ).delete(synchronize_session=False)
    if revoke_existing:
        db_session.query(AgentTeamsEmbedToken).filter(
            AgentTeamsEmbedToken.conversation_id == conversation_id,
            AgentTeamsEmbedToken.source == AGENTTEAMS_SOURCE,
            AgentTeamsEmbedToken.integration_client_key == integration_client_key,
            AgentTeamsEmbedToken.revoked_at.is_(None),
            AgentTeamsEmbedToken.expires_at > now,
        ).update({AgentTeamsEmbedToken.revoked_at: now}, synchronize_session=False)

    cleanup_before = now - timedelta(seconds=EMBED_TOKEN_RETENTION_SECONDS)
    stale_ids = [
        token_id for (token_id,) in db_session.query(AgentTeamsEmbedToken.id).filter(
            (AgentTeamsEmbedToken.expires_at <= cleanup_before)
            | (AgentTeamsEmbedToken.revoked_at <= cleanup_before)
        ).order_by(AgentTeamsEmbedToken.id.asc()).limit(EMBED_TOKEN_CLEANUP_BATCH_SIZE).all()
    ]
    if stale_ids:
        db_session.query(AgentTeamsEmbedToken).filter(
            AgentTeamsEmbedToken.id.in_(stale_ids)
        ).delete(synchronize_session=False)

    token = secrets.token_urlsafe(32)
    record = AgentTeamsEmbedToken(
        token_hash=_hash_token(token),
        conversation_id=conversation_id,
        leader_session_id=leader_session_id,
        source=AGENTTEAMS_SOURCE,
        integration_client_key=integration_client_key,
        expires_at=now + timedelta(seconds=ttl_seconds),
    )
    db_session.add(record)
    if auto_commit:
        db_session.commit()
    else:
        db_session.flush()
    return token


def _launch_response(
    db_session: Session,
    launch: AgentTeamsLaunch,
    embed_token: str,
    status: str = 'created',
    start_background: bool = False,
) -> dict:
    conversation = db_session.get(Conversation, launch.agentteams_conversation_id)
    from services.decision_run_service import DecisionRunService
    decision_run = None
    if launch.agentteams_leader_session_id:
        decision_run = DecisionRunService(db_session).get_for_session(
            launch.agentteams_leader_session_id
        )
    locale = conversation.default_locale if conversation else 'zh-CN'
    run_id = str(decision_run.run_id) if decision_run else None
    share_token = conversation.share_token if conversation else None
    embed_path = f'/embed/conversation/{embed_token}?locale={locale}'
    # 契约 v1 中立信封：provider 无关字段双发（与遗留 agentteams_* 并存过渡）。
    # 外部调用方应优先读取顶层中立字段；provider 明细放入 metadata。
    return {
        'status': status,
        'embed_path': embed_path,
        'remote_conversation_id': launch.agentteams_conversation_id,
        'remote_session_id': launch.agentteams_leader_session_id,
        'conversation_ref': launch.source_conversation_id,
        'subject_ref': launch.source_patient_id,
        'user_ref': launch.source_user_id,
        'metadata': {
            'provider': AGENTTEAMS_SOURCE,
            'embed_token': embed_token,
            'run_id': run_id,
            'agentteams_conversation_id': launch.agentteams_conversation_id,
            'agentteams_session_id': launch.agentteams_leader_session_id,
            'agentteams_share_token': share_token,
        },
        # 遗留字段（过渡期保留；契约标注废弃，迁移完成后移除）
        'run_id': run_id,
        'agentteams_conversation_id': launch.agentteams_conversation_id,
        'agentteams_share_token': share_token,
        'agentteams_session_id': launch.agentteams_leader_session_id,
        'embed_token': embed_token,
        '_start_background': start_background,
    }


def _build_llm_config(db_session: Session | None = None) -> dict:
    from services.llm_service import resolve_model_info

    model_info = resolve_model_info(db_session=db_session)
    return {
        'LLM_API_KEY': model_info['api_key'],
        'LLM_BASE_URL': model_info['base_url'],
        'LLM_MODEL': model_info['model_id'],
        'LLM_MAX_TOKENS': model_info['max_output_tokens'],
        'AGENTS_DIR': Config.AGENTS_DIR or '',
        'WORKSPACE_DIR': Config.WORKSPACE_DIR or '',
        'OPENHARNESS_ENABLED': Config.OPENHARNESS_ENABLED if hasattr(Config, 'OPENHARNESS_ENABLED') else True,
        'MAX_AGENT_PARALLEL': 5,
    }


def _project_progress_subtask(subtask: Any) -> dict:
    """仅保留适合展示且安全的任务规划字段，并省略中间结果主体。"""
    if not isinstance(subtask, dict):
        return {}
    allowed_fields = (
        'id', 'goal', 'status', 'tools', 'depends_on', 'added_dynamically',
    )
    return {
        field: copy.deepcopy(subtask[field])
        for field in allowed_fields
        if field in subtask
    }


def _refresh_progress_summary(agent: dict) -> None:
    decomposition = agent.setdefault('decomposition', {'subtasks': []})
    subtasks = decomposition.setdefault('subtasks', [])
    completed = [
        task for task in subtasks
        if task.get('status') in {'completed', 'skipped'}
    ]
    current = next(
        (task for task in subtasks if task.get('status') == 'running'),
        None,
    ) or next(
        (task for task in subtasks if task.get('status') == 'pending'),
        None,
    )
    decomposition['completedCount'] = len(completed)
    decomposition['totalCount'] = len(subtasks)
    decomposition['currentSubtaskId'] = current.get('id') if current else None
    decomposition['currentSubtaskGoal'] = current.get('goal') if current else None
    agent['currentSubtaskId'] = decomposition['currentSubtaskId']
    agent['currentSubtaskGoal'] = decomposition['currentSubtaskGoal']
    if agent.get('report_ready'):
        agent['status'] = 'completed'
    elif agent.get('status') == 'failed':
        pass
    elif subtasks and len(completed) == len(subtasks):
        # 子任务完成后还要合成 Agent 报告；收到 agent_result 前不能提前显示完成。
        agent['status'] = 'running'
    elif current is not None:
        agent['status'] = 'running'


def _apply_progress_event(progress: dict, event: dict) -> None:
    event_type = event.get('type')
    agent_id = event.get('agent_id')
    if event_type not in AGENTTEAMS_EMBED_PROGRESS_EVENT_TYPES or agent_id in (None, ''):
        return

    agents = progress.setdefault('agents', {})
    agent_key = str(agent_id)
    agent = agents.setdefault(agent_key, {
        'agent_id': agent_id,
        'agent_name': event.get('agent_name') or agent_key,
        'status': 'running',
        'decomposition': {'subtasks': []},
    })
    agent['agent_name'] = event.get('agent_name') or agent.get('agent_name') or agent_key
    decomposition = agent.setdefault('decomposition', {'subtasks': []})
    subtasks = decomposition.setdefault('subtasks', [])

    if event_type == 'task_decomposition':
        agent['status'] = 'running'
        decomposition['subtasks'] = [
            projected
            for projected in (_project_progress_subtask(task) for task in event.get('subtasks') or [])
            if projected.get('id')
        ]
    elif event_type == 'subtask_started':
        agent['status'] = 'running'
        subtask_id = event.get('subtask_id')
        subtask = next((task for task in subtasks if task.get('id') == subtask_id), None)
        if subtask is None:
            subtask = _project_progress_subtask({
                'id': subtask_id,
                'goal': event.get('goal'),
                'tools': event.get('tools') or [],
                'status': 'running',
            })
            if subtask.get('id'):
                subtasks.append(subtask)
        else:
            subtask['status'] = 'running'
            if event.get('goal'):
                subtask['goal'] = event['goal']
            if event.get('tools') is not None:
                subtask['tools'] = copy.deepcopy(event.get('tools') or [])
    elif event_type == 'subtask_completed':
        subtask_id = event.get('subtask_id')
        subtask = next((task for task in subtasks if task.get('id') == subtask_id), None)
        if subtask is not None:
            subtask['status'] = event.get('status') or 'completed'
            if event.get('goal'):
                subtask['goal'] = event['goal']
    elif event_type == 'task_adjusted':
        new_subtasks = [
            projected
            for projected in (_project_progress_subtask(task) for task in event.get('new_subtasks') or [])
            if projected.get('id')
        ]
        action = event.get('action')
        if action == 'add_subtask':
            existing_ids = {task.get('id') for task in subtasks}
            for subtask in new_subtasks:
                subtask['added_dynamically'] = True
                if subtask.get('id') not in existing_ids:
                    subtasks.append(subtask)
                    existing_ids.add(subtask.get('id'))
        elif action == 'modify_subtask':
            for updated in new_subtasks:
                existing = next((task for task in subtasks if task.get('id') == updated.get('id')), None)
                if existing is not None:
                    existing.update(updated)
        elif action == 'skip':
            current_id = decomposition.get('currentSubtaskId')
            current = next((task for task in subtasks if task.get('id') == current_id), None)
            if current is not None:
                current['status'] = 'skipped'
    elif event_type == 'agent_result':
        agent.update({
            'status': 'completed',
            'report_ready': True,
            'content': event.get('content') or '',
            'content_locale': event.get('content_locale'),
            'summary': copy.deepcopy(event.get('summary')),
            'structured_report': copy.deepcopy(event.get('structured_report')),
            'evidence_map': copy.deepcopy(event.get('evidence_map') or []),
            'decomposition': copy.deepcopy(event.get('decomposition') or decomposition),
            'tokens_used': event.get('tokens_used') or 0,
            'execution_time': event.get('execution_time') or 0,
        })
    elif event_type == 'agent_error':
        agent.update({
            'status': 'failed',
            'report_ready': False,
            'content': event.get('content') or '',
            'error': event.get('error') or event.get('content') or '',
        })

    _refresh_progress_summary(agent)
    progress['revision'] = int(progress.get('revision') or 0) + 1


def _persist_agentteams_workflow_progress(
    launch_id: int,
    event: dict,
    session_factory: Callable[[], Session],
) -> None:
    """持久化精简的 Agent 任务快照，供跨工作器的嵌入页面刷新使用。"""
    if event.get('type') not in AGENTTEAMS_EMBED_PROGRESS_EVENT_TYPES:
        return
    progress_session = session_factory()
    try:
        launch = progress_session.query(AgentTeamsLaunch).filter(
            AgentTeamsLaunch.id == launch_id,
        ).with_for_update().first()
        if launch is None:
            return
        metadata = copy.deepcopy(launch.metadata_json or {})
        progress = copy.deepcopy(metadata.get(AGENTTEAMS_EMBED_PROGRESS_KEY) or {
            'revision': 0,
            'agents': {},
        })
        _apply_progress_event(progress, event)
        metadata[AGENTTEAMS_EMBED_PROGRESS_KEY] = progress
        launch.metadata_json = metadata
        progress_session.commit()
    except Exception:
        progress_session.rollback()
        logger.exception(
            'Failed to persist Agent Teams workflow progress: launch_id=%s event=%s',
            launch_id,
            event.get('type'),
        )
    finally:
        progress_session.close()


def _get_agentteams_embed_progress(launch: AgentTeamsLaunch | None) -> dict:
    if launch is None:
        return {'revision': 0, 'agents': {}}
    progress = (launch.metadata_json or {}).get(AGENTTEAMS_EMBED_PROGRESS_KEY) or {}
    agents = progress.get('agents') if isinstance(progress, dict) else {}
    return {
        'revision': int(progress.get('revision') or 0) if isinstance(progress, dict) else 0,
        'agents': agents if isinstance(agents, dict) else {},
    }


def _clear_agentteams_workflow_progress(launch: AgentTeamsLaunch) -> None:
    """在工作流持久化完成后，移除临时的报告/进度副本。"""
    metadata = copy.deepcopy(launch.metadata_json or {})
    if AGENTTEAMS_EMBED_PROGRESS_KEY not in metadata:
        return
    metadata.pop(AGENTTEAMS_EMBED_PROGRESS_KEY, None)
    launch.metadata_json = metadata


def launch_agentteams_consultation(
    db_session: Session,
    payload: dict[str, Any],
    request_id: str,
    integration_key: str | None,
    integration_context: IntegrationClientContext | None = None,
) -> dict:
    """创建或解析一次 Agent Teams 启动，并返回嵌入响应。"""
    # 兼容端点仍使用遗留的 SystemConfig 密钥进行认证。通用网关会传入
    # 已认证的客户端上下文，因此此适配器无需重复凭证策略。
    if integration_context is None:
        _verify_integration_key(db_session, integration_key)
    elif integration_context.adapter_key != AGENTTEAMS_SOURCE:
        raise AgentTeamsLaunchError(400, 'invalid_client', 'Unsupported integration client')
    _validate_launch_payload(payload, request_id)

    request_id = request_id.strip()
    # 幂等命中必须限定在调用方自己的本地归属内：共享适配器的多个
    # 客户端租户使用各自的命名空间，任何一方都不能命中或删除
    # 其他客户端的启动记录（含遗留密钥持有者伪造前缀 ID 的场景）。
    owner_client_key = (
        integration_context.client_key
        if integration_context is not None
        else AGENTTEAMS_SOURCE
    )
    existing = db_session.query(AgentTeamsLaunch).filter_by(
        source=AGENTTEAMS_SOURCE,
        integration_client_key=owner_client_key,
        request_id=request_id,
    ).with_for_update().first()
    if existing and existing.agentteams_conversation_id:
        _assert_idempotent_launch_matches(existing, payload)
        embed_token = _create_embed_token(
            db_session,
            existing.agentteams_conversation_id,
            existing.agentteams_leader_session_id,
            integration_client_key=existing.integration_client_key,
            revoke_existing=False,
        )
        logger.info("Agent Teams launch idempotent hit: request_id=%s launch_id=%s", request_id, existing.id)
        return _launch_response(
            db_session,
            existing,
            embed_token,
            status=existing.status or 'created',
            start_background=_launch_is_recoverable(existing),
        )
    if existing:
        db_session.delete(existing)
        db_session.flush()

    enabled = (
        integration_context.enabled
        if integration_context is not None
        else _parse_bool(_get_config_value(db_session, AGENTTEAMS_INTEGRATION_ENABLED, 'true'))
    )
    if not enabled:
        raise AgentTeamsLaunchError(403, 'integration_disabled', 'Agent Teams integration is disabled')

    service_account = (
        db_session.get(User, integration_context.service_account_id)
        if integration_context is not None and integration_context.service_account_id is not None
        else resolve_agentteams_service_account(db_session)
    )
    if service_account is None:
        raise AgentTeamsLaunchError(
            403,
            'service_account_not_configured',
            'Integration service account is not configured',
        )

    try:
        launch = AgentTeamsLaunch(
            source=AGENTTEAMS_SOURCE,
            integration_client_key=(
                integration_context.client_key
                if integration_context is not None
                else AGENTTEAMS_SOURCE
            ),
            request_id=request_id,
            source_user_id=payload.get('source_user_id'),
            source_patient_id=str(payload.get('source_patient_id')) if payload.get('source_patient_id') is not None else None,
            source_conversation_id=str(payload.get('source_conversation_id')),
            status='created',
            metadata_json=payload.get('metadata') or {},
        )
        db_session.add(launch)

        title = str(payload.get('title') or 'Agent Teams consultation').strip()
        # 校验会拒绝空白输入，但持久化会保留客户端的原始载荷
        # （包括有意义的首尾换行）。
        message = str(payload.get('message'))
        locale = str(payload.get('locale') or 'zh-CN')
        conversation = Conversation(
            title=title,
            user_id=service_account.id,
            is_review_mode=True,
            category='medical',
            status='analyzing',
            default_locale=locale,
            share_token=Conversation.generate_share_token(),
        )
        db_session.add(conversation)
        db_session.flush()

        user_message = Message.create_normal_message(
            conversation_id=conversation.id,
            role='user',
            content=message,
            is_review_mode=True,
            content_locale=locale,
        )
        db_session.add(user_message)

        leader_session = create_leader_session(
            db_session=db_session,
            conversation_id=conversation.id,
            message=message,
            locale=locale,
            auto_commit=False,
            decision_source=AGENTTEAMS_SOURCE,
            decision_source_ref=request_id,
        )
        # 将启动问题绑定到其精确所属的工作流。这样既可保持嵌入令牌
        # 只归属于一个 LeaderSession，即使该会话之后又出现了
        # 其他普通用户消息，也是如此。
        user_message.leader_session_id = leader_session.id

        launch.agentteams_conversation_id = conversation.id
        launch.agentteams_leader_session_id = leader_session.id
        embed_token = _create_embed_token(
            db_session,
            conversation.id,
            leader_session.id,
            integration_client_key=(
                integration_context.client_key
                if integration_context is not None
                else AGENTTEAMS_SOURCE
            ),
            auto_commit=False,
        )
        db_session.commit()
    except IntegrityError:
        db_session.rollback()
        existing = db_session.query(AgentTeamsLaunch).filter_by(
            source=AGENTTEAMS_SOURCE,
            integration_client_key=owner_client_key,
            request_id=request_id,
        ).with_for_update().first()
        if not existing or not existing.agentteams_conversation_id:
            raise
        _assert_idempotent_launch_matches(existing, payload)
        embed_token = _create_embed_token(
            db_session,
            existing.agentteams_conversation_id,
            existing.agentteams_leader_session_id,
            integration_client_key=existing.integration_client_key,
            revoke_existing=False,
        )
        return _launch_response(
            db_session,
            existing,
            embed_token,
            status=existing.status or 'created',
            start_background=_launch_is_recoverable(existing),
        )
    except Exception:
        db_session.rollback()
        raise
    logger.info(
        "Agent Teams launch created: request_id=%s launch_id=%s conversation_id=%s "
        "session_id=%s message_chars=%s",
        request_id,
        launch.id,
        conversation.id,
        leader_session.id,
        len(message),
    )
    return _launch_response(db_session, launch, embed_token, status='created', start_background=True)


def get_agentteams_launch_by_request_id(
    db_session: Session,
    request_id: str,
    integration_key: str | None,
    integration_context: IntegrationClientContext | None = None,
) -> dict[str, Any]:
    """读取一次启动请求用于对账，不创建令牌，也不调度任何工作。"""
    if integration_context is None:
        _verify_integration_key(db_session, integration_key)
    normalized_request_id = str(request_id or '').strip()
    if not normalized_request_id:
        raise AgentTeamsLaunchError(400, 'invalid_payload', 'request_id is required')

    query = db_session.query(AgentTeamsLaunch).filter_by(
        source=AGENTTEAMS_SOURCE,
        request_id=normalized_request_id,
    )
    if integration_context is not None:
        query = query.filter_by(integration_client_key=integration_context.client_key)
    else:
        # 遗留端点只能看到遗留客户端自己的记录；
        # 共享适配器客户端的前缀化 ID 不得通过内部键猜测读取。
        query = query.filter_by(integration_client_key=AGENTTEAMS_SOURCE)
    launch = query.one_or_none()
    if launch is None:
        return {
            'found': False,
            'request_id': normalized_request_id,
            'status': 'not_found',
        }

    return {
        'found': True,
        'request_id': launch.request_id,
        'status': launch.status or 'created',
        # 契约 v1 中立别名（遗留字段保留过渡）
        'remote_conversation_id': launch.agentteams_conversation_id,
        'remote_session_id': launch.agentteams_leader_session_id,
        'agentteams_conversation_id': launch.agentteams_conversation_id,
        'agentteams_session_id': launch.agentteams_leader_session_id,
        'source_conversation_id': launch.source_conversation_id,
        'error_code': launch.error_code,
    }


def reissue_agentteams_embed_token(
    db_session: Session,
    request_id: str,
    integration_key: str | None,
    integration_context: IntegrationClientContext | None = None,
) -> dict[str, Any]:
    """为既有启动记录重签一个嵌入令牌，供宿主重新打开历史会诊。

    与 status 查询共享幂等边界与租户隔离（联动的调用方必须在路由层把
    request-id 规范化为存储键，正如 ``get_agentteams_launch_by_request_id``
    的适配器调用相同）。该终点只铸造令牌，不创建会话、不调度也不重启
    工作流，因此不会带来新的计费或重复执行副作用。启动记录以行锁保护，
    避免并发重签与管理的撤销操作交错。
    """
    if integration_context is None:
        _verify_integration_key(db_session, integration_key)
    normalized_request_id = str(request_id or '').strip()
    if not normalized_request_id:
        raise AgentTeamsLaunchError(400, 'invalid_payload', 'request_id is required')

    owner_client_key = (
        integration_context.client_key
        if integration_context is not None
        else AGENTTEAMS_SOURCE
    )
    launch = (
        db_session.query(AgentTeamsLaunch)
        .filter_by(
            source=AGENTTEAMS_SOURCE,
            integration_client_key=owner_client_key,
            request_id=normalized_request_id,
        )
        .with_for_update()
        .one_or_none()
    )
    if launch is None or launch.agentteams_conversation_id is None:
        raise AgentTeamsLaunchError(
            404,
            'agentteams_launch_not_found',
            'Agent Teams launch not found',
        )

    status = str(launch.status or 'created').strip().lower()
    if status in {'failed', 'stopped'}:
        raise AgentTeamsLaunchError(
            409,
            f'agentteams_launch_{status}',
            f'Agent Teams launch is {status}',
        )

    embed_token = _create_embed_token(
        db_session,
        launch.agentteams_conversation_id,
        launch.agentteams_leader_session_id,
        integration_client_key=owner_client_key,
        revoke_existing=False,
    )
    return _launch_response(
        db_session,
        launch,
        embed_token,
        status=launch.status or 'created',
        start_background=False,
    )


def revoke_agentteams_embed_access(
    db_session: Session,
    *,
    client_key: str,
    request_id: str,
    operation_id: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """撤销某个客户端所拥有的启动请求的所有活动本地嵌入令牌。

    这里有意只做本地访问撤销。对话、工作流和审计记录均保持
    完整，且不会尝试任何远程删除。启动行会被锁定，使并发的管理重试
    能观察到稳定的所有权边界，且该操作具备幂等性。操作记录与令牌
    更新写在同一个事务中；调用方将其与审计条目一起提交。
    """
    normalized_client_key = str(client_key or '').strip()
    normalized_request_id = str(request_id or '').strip()
    if not normalized_client_key:
        raise AgentTeamsLaunchError(400, 'invalid_payload', 'client_key is required')
    if not normalized_request_id:
        raise AgentTeamsLaunchError(400, 'invalid_payload', 'request_id is required')
    if len(normalized_request_id) > 100:
        raise AgentTeamsLaunchError(400, 'invalid_payload', 'request_id must be at most 100 characters')
    normalized_reason = str(reason or '').strip()
    if not normalized_reason:
        raise AgentTeamsLaunchError(400, 'invalid_payload', 'reason is required')
    if len(normalized_reason) > 500:
        raise AgentTeamsLaunchError(400, 'invalid_payload', 'reason must be at most 500 characters')

    normalized_operation_id = str(operation_id or '').strip() or default_embed_revoke_operation_id(
        normalized_client_key,
        normalized_request_id,
    )
    if len(normalized_operation_id) > 100:
        raise AgentTeamsLaunchError(400, 'invalid_payload', 'operation_id must be at most 100 characters')

    storage_request_id = agentteams_storage_request_id(
        normalized_request_id,
        normalized_client_key,
    )
    launch = (
        db_session.query(AgentTeamsLaunch)
        .filter_by(
            source=AGENTTEAMS_SOURCE,
            integration_client_key=normalized_client_key,
            request_id=storage_request_id,
        )
        .with_for_update()
        .one_or_none()
    )
    if launch is None or launch.agentteams_conversation_id is None:
        raise AgentTeamsLaunchError(
            404,
            'agentteams_launch_not_found',
            'Agent Teams launch not found',
        )

    existing_operation = (
        db_session.query(IntegrationAccessOperation)
        .filter_by(
            client_key=normalized_client_key,
            action=INTEGRATION_REVOKE_ACTION,
            operation_id=normalized_operation_id,
        )
        .with_for_update()
        .one_or_none()
    )
    if existing_operation is not None:
        # 查询已按 client_key + action + operation_id 过滤，
        # 此处只需比较 request_id 是否与当前操作一致。
        if existing_operation.request_id != normalized_request_id:
            raise AgentTeamsLaunchError(
                409,
                'integration_operation_conflict',
                'operation_id is already bound to another integration action',
            )
        return existing_operation.to_dict()

    operation = IntegrationAccessOperation(
        operation_id=normalized_operation_id,
        client_key=normalized_client_key,
        action=INTEGRATION_REVOKE_ACTION,
        request_id=normalized_request_id,
        status='requested',
        reason=normalized_reason,
        remote_action='not_implemented',
    )
    db_session.add(operation)
    db_session.flush()

    now = utcnow_naive()
    revoked_count = (
        db_session.query(AgentTeamsEmbedToken)
        .filter(
            AgentTeamsEmbedToken.source == AGENTTEAMS_SOURCE,
            AgentTeamsEmbedToken.integration_client_key == normalized_client_key,
            AgentTeamsEmbedToken.conversation_id == launch.agentteams_conversation_id,
            AgentTeamsEmbedToken.revoked_at.is_(None),
            AgentTeamsEmbedToken.expires_at > now,
        )
        .update(
            {AgentTeamsEmbedToken.revoked_at: now},
            synchronize_session=False,
        )
    )

    # 撤销共享链接通道：share_token 与嵌入令牌同属本地访问面，
    # 否则"本地访问撤销"后对话仍可经旧共享链接读取，治理语义不完整
    db_session.query(Conversation).filter(
        Conversation.id == launch.agentteams_conversation_id,
        Conversation.share_token.isnot(None),
    ).update(
        {Conversation.share_token: None},
        synchronize_session=False,
    )
    operation.status = 'completed'
    operation.revoked_count = int(revoked_count)
    operation.updated_at = utcnow_naive()
    db_session.flush()
    return operation.to_dict()


def get_embed_revoke_operation(
    db_session: Session,
    *,
    client_key: str,
    operation_id: str,
) -> dict[str, Any]:
    """无副作用地读取某个客户端作用域内的本地访问操作。"""
    normalized_client_key = str(client_key or '').strip()
    normalized_operation_id = str(operation_id or '').strip()
    if not normalized_client_key or not normalized_operation_id:
        raise AgentTeamsLaunchError(400, 'invalid_payload', 'client_key and operation_id are required')
    operation = (
        db_session.query(IntegrationAccessOperation)
        .filter_by(
            client_key=normalized_client_key,
            operation_id=normalized_operation_id,
            action=INTEGRATION_REVOKE_ACTION,
        )
        .one_or_none()
    )
    if operation is None:
        raise AgentTeamsLaunchError(
            404,
            'integration_operation_not_found',
            'Integration access operation not found',
        )
    return operation.to_dict()


def list_embed_revoke_operations(
    db_session: Session,
    *,
    client_key: str,
    limit: int = 100,
    status: str | None = None,
) -> list[dict[str, Any]]:
    """仅列出某个集成客户端的本地访问撤销操作。"""
    normalized_client_key = str(client_key or '').strip()
    if not normalized_client_key:
        raise AgentTeamsLaunchError(400, 'invalid_payload', 'client_key is required')
    if not 1 <= int(limit) <= 200:
        raise AgentTeamsLaunchError(400, 'invalid_payload', 'limit must be between 1 and 200')
    normalized_status = str(status or '').strip()
    if len(normalized_status) > 30:
        raise AgentTeamsLaunchError(400, 'invalid_payload', 'status must be at most 30 characters')

    query = db_session.query(IntegrationAccessOperation).filter_by(
        client_key=normalized_client_key,
        action=INTEGRATION_REVOKE_ACTION,
    )
    if normalized_status:
        query = query.filter_by(status=normalized_status)
    operations = query.order_by(
        IntegrationAccessOperation.created_at.desc(),
        IntegrationAccessOperation.id.desc(),
    ).limit(int(limit)).all()
    return [operation.to_dict() for operation in operations]


def run_agentteams_leader_workflow(launch_id: int, session_factory: Callable[[], Session] = SessionLocal) -> None:
    """在同步工作器/测试上下文中运行一次租约感知的启动请求。"""
    asyncio.run(_run_agentteams_leader_workflow_async(launch_id, session_factory))


def _claim_agentteams_launch(
    session: Session,
    launch_id: int,
    lease_owner: str,
) -> bool:
    now = utcnow_naive()
    claimed = session.query(AgentTeamsLaunch).filter(
        AgentTeamsLaunch.id == launch_id,
        or_(
            AgentTeamsLaunch.status == 'created',
            and_(
                AgentTeamsLaunch.status == 'running',
                or_(
                    AgentTeamsLaunch.lease_expires_at.is_(None),
                    AgentTeamsLaunch.lease_expires_at <= now,
                ),
            ),
        ),
    ).update(
        {
            AgentTeamsLaunch.status: 'running',
            AgentTeamsLaunch.lease_owner: lease_owner,
            AgentTeamsLaunch.lease_expires_at: now + timedelta(seconds=LAUNCH_LEASE_SECONDS),
            AgentTeamsLaunch.heartbeat_at: now,
            AgentTeamsLaunch.attempt_count: func.coalesce(AgentTeamsLaunch.attempt_count, 0) + 1,
        },
        synchronize_session=False,
    )
    session.commit()
    return claimed == 1


def claim_agentteams_answer_launch(db_session: Session, launch_id: int) -> str:
    """在持久化新一轮答案之前，认领一次正在提问的启动请求。"""
    now = utcnow_naive()
    lease_owner = secrets.token_hex(16)
    claimed = db_session.query(AgentTeamsLaunch).filter(
        AgentTeamsLaunch.id == launch_id,
        AgentTeamsLaunch.status.in_(['questioning', 'created']),
        or_(
            AgentTeamsLaunch.lease_owner.is_(None),
            AgentTeamsLaunch.lease_expires_at.is_(None),
            AgentTeamsLaunch.lease_expires_at <= now,
        ),
    ).update(
        {
            AgentTeamsLaunch.status: 'running',
            AgentTeamsLaunch.lease_owner: lease_owner,
            AgentTeamsLaunch.lease_expires_at: now + timedelta(seconds=LAUNCH_LEASE_SECONDS),
            AgentTeamsLaunch.heartbeat_at: now,
            AgentTeamsLaunch.attempt_count: func.coalesce(AgentTeamsLaunch.attempt_count, 0) + 1,
        },
        synchronize_session=False,
    )
    db_session.commit()
    if claimed != 1:
        raise AgentTeamsLaunchError(
            409,
            'embed_session_already_running',
            'This embed session is already processing an answer',
        )
    return lease_owner


def release_agentteams_answer_claim(
    launch_id: int,
    lease_owner: str,
    session_factory: Callable[[], Session] = SessionLocal,
    *,
    status: str = 'questioning',
) -> None:
    session = session_factory()
    try:
        session.query(AgentTeamsLaunch).filter(
            AgentTeamsLaunch.id == launch_id,
            AgentTeamsLaunch.lease_owner == lease_owner,
        ).update(
            {
                AgentTeamsLaunch.status: status,
                AgentTeamsLaunch.lease_owner: None,
                AgentTeamsLaunch.lease_expires_at: None,
            },
            synchronize_session=False,
        )
        session.commit()
    finally:
        session.close()


async def run_claimed_agentteams_workflow_events(
    launch_id: int,
    lease_owner: str,
    events: AsyncGenerator[dict, None],
    session_factory: Callable[[], Session] = SessionLocal,
) -> AsyncGenerator[dict, None]:
    """在维持其持久化启动租约的同时，驱动答案的延续。"""
    heartbeat_task = asyncio.create_task(
        _maintain_agentteams_launch_lease(launch_id, lease_owner, session_factory)
    )
    next_event_task: asyncio.Task | None = None
    completed = False
    # 每个事件都在独立的 task 中恢复生成器；task 创建时会快照 contextvars。
    # async_continue_leader_workflow 在首个事件里通过 _initialize_services
    # 写入的 NodeServices contextvar 会随该 task 的 context 副本一起丢失，
    # 后续图节点（human_input_node 等）只能拿到空服务：questioning 状态不再
    # 持久化，会话停在 assessing，最终被终态兜底标记为 failed。
    # 这里让所有 anext 共享同一个可变 Context，使 contextvar 写入跨事件保留。
    shared_context = contextvars.copy_context()
    try:
        event_iterator = events.__aiter__()
        while True:
            next_event_task = asyncio.create_task(
                anext(event_iterator),
                context=shared_context,
            )
            done, _ = await asyncio.wait(
                {next_event_task, heartbeat_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if heartbeat_task in done and not await heartbeat_task:
                next_event_task.cancel()
                await asyncio.gather(next_event_task, return_exceptions=True)
                raise RuntimeError('Agent Teams continuation lost its launch lease')

            try:
                event = await next_event_task
            except StopAsyncIteration:
                completed = True
                break
            yield event
    finally:
        if next_event_task is not None and not next_event_task.done():
            next_event_task.cancel()
            await asyncio.gather(next_event_task, return_exceptions=True)
        heartbeat_task.cancel()
        await asyncio.gather(heartbeat_task, return_exceptions=True)
        if completed:
            session = session_factory()
            try:
                launch = session.query(AgentTeamsLaunch).filter(
                    AgentTeamsLaunch.id == launch_id,
                    AgentTeamsLaunch.lease_owner == lease_owner,
                ).first()
                if launch is not None:
                    leader_session = session.get(LeaderSession, launch.agentteams_leader_session_id)
                    leader_state = leader_session.state if leader_session else 'failed'
                    stable_states = {*AGENTTEAMS_TERMINAL_STATES, 'questioning'}
                    launch.status = leader_state if leader_state in stable_states else 'running'
                    launch.lease_owner = None
                    launch.lease_expires_at = (
                        None if leader_state in stable_states else utcnow_naive()
                    )
                    if launch.status == 'completed':
                        _clear_agentteams_workflow_progress(launch)
                    session.commit()
            finally:
                session.close()
        else:
            # 在断开连接的取消或进程本地的延续失败之后，仍保持启动请求可恢复，
            # 使其始终处于恢复监控的可认领窗口内。
            session = session_factory()
            try:
                now = utcnow_naive()
                session.query(AgentTeamsLaunch).filter(
                    AgentTeamsLaunch.id == launch_id,
                    AgentTeamsLaunch.lease_owner == lease_owner,
                ).update(
                    {AgentTeamsLaunch.lease_expires_at: now},
                    synchronize_session=False,
                )
                session.commit()
            finally:
                session.close()


async def _maintain_agentteams_launch_lease(
    launch_id: int,
    lease_owner: str,
    session_factory: Callable[[], Session],
) -> bool:
    while True:
        await asyncio.sleep(LAUNCH_HEARTBEAT_SECONDS)
        try:
            if not renew_agentteams_launch_lease(launch_id, lease_owner, session_factory):
                return False
        except Exception:
            logger.error(
                "Agent Teams lease heartbeat failed: launch_id=%s owner=%s",
                launch_id,
                lease_owner,
                exc_info=True,
            )
            return False


async def _run_agentteams_leader_workflow_async(launch_id: int, session_factory: Callable[[], Session]) -> None:
    session = session_factory()
    lease_owner = secrets.token_hex(16)
    workflow_task = None
    heartbeat_task = None
    try:
        if not _claim_agentteams_launch(session, launch_id, lease_owner):
            return

        launch = session.get(AgentTeamsLaunch, launch_id)
        if not launch or not launch.agentteams_conversation_id or not launch.agentteams_leader_session_id:
            raise RuntimeError('Agent Teams launch is missing workflow identifiers')

        leader_session = session.get(LeaderSession, launch.agentteams_leader_session_id)
        service_user_id = leader_session.conversation.user_id if leader_session and leader_session.conversation else None
        message = leader_session.user_message if leader_session else ''
        history = [{'role': 'user', 'content': message}]
        pack = ContextBuilder.build(message, None)
        llm_config = _build_llm_config(session)

        async def consume_workflow() -> None:
            events = async_run_leader_workflow(
                conversation_id=launch.agentteams_conversation_id,
                message=pack.task_description,
                history=history,
                config=llm_config,
                user_id=service_user_id,
                existing_session_id=launch.agentteams_leader_session_id,
            )
            async for _event in persist_agentteams_workflow_progress_events(
                launch_id,
                events,
                session_factory,
            ):
                pass

        workflow_task = asyncio.create_task(consume_workflow())
        heartbeat_task = asyncio.create_task(
            _maintain_agentteams_launch_lease(launch_id, lease_owner, session_factory)
        )
        done, _ = await asyncio.wait(
            {workflow_task, heartbeat_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if heartbeat_task in done:
            lease_retained = await heartbeat_task
            if not lease_retained:
                workflow_task.cancel()
                await asyncio.gather(workflow_task, return_exceptions=True)
                logger.warning(
                    "Agent Teams workflow stopped after lease loss: launch_id=%s owner=%s",
                    launch_id,
                    lease_owner,
                )
                return

        await workflow_task
        heartbeat_task.cancel()
        await asyncio.gather(heartbeat_task, return_exceptions=True)

        session.expire_all()
        refreshed = session.get(LeaderSession, launch.agentteams_leader_session_id)
        completed_status = refreshed.state if refreshed else 'completed'
        session.query(AgentTeamsLaunch).filter(
            AgentTeamsLaunch.id == launch_id,
            AgentTeamsLaunch.lease_owner == lease_owner,
        ).update(
            {
                AgentTeamsLaunch.status: completed_status,
                AgentTeamsLaunch.lease_owner: None,
                AgentTeamsLaunch.lease_expires_at: None,
            },
            synchronize_session=False,
        )
        completed_launch = session.get(AgentTeamsLaunch, launch_id)
        if completed_status == 'completed' and completed_launch is not None:
            _clear_agentteams_workflow_progress(completed_launch)
        session.commit()
    except asyncio.CancelledError:
        session.rollback()
        now = utcnow_naive()
        session.query(AgentTeamsLaunch).filter(
            AgentTeamsLaunch.id == launch_id,
            AgentTeamsLaunch.lease_owner == lease_owner,
        ).update(
            {
                AgentTeamsLaunch.lease_owner: None,
                AgentTeamsLaunch.lease_expires_at: now,
            },
            synchronize_session=False,
        )
        session.commit()
        raise
    except Exception as exc:
        logger.error("Agent Teams background workflow failed: launch_id=%s error=%s", launch_id, exc, exc_info=True)
        session.rollback()
        launch = session.query(AgentTeamsLaunch).filter(
            AgentTeamsLaunch.id == launch_id,
            AgentTeamsLaunch.lease_owner == lease_owner,
        ).first()
        if launch:
            launch.status = 'failed'
            launch.error_code = 'agentteams_launch_failed'
            launch.lease_owner = None
            launch.lease_expires_at = None
            if launch.agentteams_leader_session_id:
                # 原始异常已在上方日志留痕；会话记录只存通用文案，
                # 避免内部细节经 embed 快照外泄给外部系统
                mark_session_failed(session, launch.agentteams_leader_session_id, '工作流执行失败')
            session.commit()
    finally:
        pending_tasks = [
            task for task in (workflow_task, heartbeat_task)
            if task is not None and not task.done()
        ]
        for task in pending_tasks:
            task.cancel()
        if pending_tasks:
            await asyncio.gather(*pending_tasks, return_exceptions=True)
        session.close()


async def persist_agentteams_workflow_progress_events(
    launch_id: int,
    events: AsyncGenerator[dict, None],
    session_factory: Callable[[], Session] = SessionLocal,
) -> AsyncGenerator[dict, None]:
    """在保留原始工作流事件流的同时，持久化展示进度。"""
    async for event in events:
        if isinstance(event, dict) and event.get('type') in AGENTTEAMS_EMBED_PROGRESS_EVENT_TYPES:
            await asyncio.to_thread(
                _persist_agentteams_workflow_progress,
                launch_id,
                event,
                session_factory,
            )
        yield event


def _resolve_agentteams_embed_token(db_session: Session, embed_token: str) -> AgentTeamsEmbedToken:
    token_hash = _hash_token(embed_token)
    token_record = db_session.query(AgentTeamsEmbedToken).filter_by(token_hash=token_hash).first()
    now = utcnow_naive()
    if not token_record or token_record.revoked_at or token_record.expires_at <= now:
        raise AgentTeamsLaunchError(401, 'invalid_embed_token', 'Invalid embed token')
    if not IntegrationClientService.is_enabled_for_embed_access(
        db_session,
        token_record.integration_client_key,
    ):
        raise AgentTeamsLaunchError(403, 'integration_disabled', 'Integration is disabled')

    if (
        token_record.last_used_at is None
        or token_record.last_used_at <= now - timedelta(seconds=EMBED_LAST_USED_WRITE_INTERVAL_SECONDS)
    ):
        token_record.last_used_at = now
        db_session.commit()
    return token_record


def _build_agentteams_embed_status(
    db_session: Session,
    token_record: AgentTeamsEmbedToken,
) -> dict:
    conversation = db_session.get(Conversation, token_record.conversation_id)
    if not conversation:
        raise AgentTeamsLaunchError(404, 'embed_session_not_found', 'Embed session not found')

    leader_session = None
    if token_record.leader_session_id:
        leader_session = db_session.get(LeaderSession, token_record.leader_session_id)
    if leader_session is None:
        leader_session = db_session.query(LeaderSession).filter_by(
            conversation_id=conversation.id,
        ).order_by(LeaderSession.started_at.desc()).first()

    if leader_session is None:
        status = conversation.status or 'created'
        version = f'conversation:{conversation.id}:{status}:0:0:0'
        decision_run = None
    else:
        launch = db_session.query(AgentTeamsLaunch).filter_by(
            agentteams_leader_session_id=leader_session.id,
        ).order_by(AgentTeamsLaunch.id.desc()).first()
        embed_progress = _get_agentteams_embed_progress(launch)
        max_sequence = db_session.query(func.max(Message.sequence_number)).filter(
            Message.leader_session_id == leader_session.id,
            Message.sequence_number.isnot(None),
        ).scalar() or 0
        result_count = db_session.query(func.count(LeaderAgentResult.id)).filter(
            LeaderAgentResult.leader_session_id == leader_session.id,
        ).scalar() or 0
        report_count = db_session.query(func.count(LeaderFinalReport.id)).filter(
            LeaderFinalReport.leader_session_id == leader_session.id,
        ).scalar() or 0
        tool_log_count = db_session.query(func.count(ToolCallLog.id)).filter(
            ToolCallLog.leader_session_id == leader_session.id,
        ).scalar() or 0
        max_tool_log_id = db_session.query(func.max(ToolCallLog.id)).filter(
            ToolCallLog.leader_session_id == leader_session.id,
        ).scalar() or 0
        from services.decision_run_service import DecisionRunService
        decision_run = DecisionRunService(db_session).projection_for_session(leader_session)
        leader_state = leader_session.state or conversation.status or 'created'
        if leader_state in AGENTTEAMS_TERMINAL_STATES or leader_state == 'questioning':
            status = leader_state
        elif decision_run.get('state') in AGENTTEAMS_TERMINAL_STATES:
            status = decision_run['state']
        else:
            status = _DECISION_STAGE_TO_EMBED_STATE.get(
                decision_run.get('current_stage'),
                leader_state,
            )
        decision_version = ':'.join([
            str(decision_run.get('state') or ''),
            str(decision_run.get('current_stage') or ''),
            str(decision_run.get('updated_at') or ''),
        ])
        version = (
            f'{leader_session.id}:{status}:{max_sequence}:'
            f'{result_count}:{report_count}:{tool_log_count}:{max_tool_log_id}:'
            f'{embed_progress["revision"]}:{decision_version}'
        )

    return {
        'conversation_id': conversation.id,
        'status': status,
        'terminal': status in AGENTTEAMS_TERMINAL_STATES,
        'version': version,
        'decision_run': decision_run,
        'run_id': decision_run.get('run_id') if decision_run else None,
    }


def get_agentteams_embed_status(db_session: Session, embed_token: str) -> dict:
    """仅返回嵌入轮询客户端所需的字段。"""
    token_record = _resolve_agentteams_embed_token(db_session, embed_token)
    return _build_agentteams_embed_status(db_session, token_record)


def _read_agentteams_embed_status(
    embed_token: str,
    session_factory: Callable[[], Session],
) -> dict:
    session = session_factory()
    try:
        return get_agentteams_embed_status(session, embed_token)
    finally:
        session.close()


async def stream_agentteams_embed_events(
    embed_token: str,
    session_factory: Callable[[], Session] = SessionLocal,
    poll_interval_seconds: float = AGENTTEAMS_EMBED_EVENT_POLL_SECONDS,
) -> AsyncGenerator[dict, None]:
    """跨工作器流式推送持久的嵌入快照失效事件。"""
    last_version = None
    while True:
        status = await asyncio.to_thread(
            _read_agentteams_embed_status,
            embed_token,
            session_factory,
        )
        if status['version'] != last_version:
            last_version = status['version']
            yield {'type': 'embed_snapshot', **status}

        if status['terminal']:
            yield {
                'type': 'done',
                'conversation_id': status['conversation_id'],
                'version': status['version'],
            }
            return

        await asyncio.sleep(max(0.05, poll_interval_seconds))


def resolve_agentteams_embed_answer_session(
    db_session: Session,
    embed_token: str,
    requested_session_id: int,
) -> tuple[LeaderSession, int]:
    """解析某个嵌入令牌可回答的唯一 Leader 会话。"""
    token_record = _resolve_agentteams_embed_token(db_session, embed_token)
    if (
        token_record.leader_session_id is None
        or token_record.leader_session_id != requested_session_id
    ):
        raise AgentTeamsLaunchError(
            403,
            'embed_session_mismatch',
            'Embed token does not grant access to this session',
        )

    leader_session = db_session.get(LeaderSession, token_record.leader_session_id)
    if (
        leader_session is None
        or leader_session.conversation_id != token_record.conversation_id
    ):
        raise AgentTeamsLaunchError(404, 'embed_session_not_found', 'Embed session not found')
    if leader_session.state != 'questioning':
        raise AgentTeamsLaunchError(
            409,
            'embed_session_not_questioning',
            'Embed session is not waiting for answers',
        )

    conversation = db_session.get(Conversation, token_record.conversation_id)
    if conversation is None:
        raise AgentTeamsLaunchError(404, 'embed_session_not_found', 'Embed session not found')
    return leader_session, conversation.user_id


def get_agentteams_embed_session(db_session: Session, embed_token: str) -> dict:
    """返回一个只读的嵌入会话快照。"""
    token_record = _resolve_agentteams_embed_token(db_session, embed_token)

    conversation = db_session.get(Conversation, token_record.conversation_id)
    if not conversation:
        raise AgentTeamsLaunchError(404, 'embed_session_not_found', 'Embed session not found')

    leader_sessions_query = db_session.query(LeaderSession).filter_by(
        conversation_id=conversation.id
    )
    if token_record.leader_session_id is not None:
        leader_sessions_query = leader_sessions_query.filter(
            LeaderSession.id == token_record.leader_session_id,
        )
    leader_sessions = leader_sessions_query.order_by(
        LeaderSession.started_at.asc(),
        LeaderSession.id.asc(),
    ).all()
    session_ids = [s.id for s in leader_sessions]
    agent_results = []
    final_reports = []
    tool_call_logs = []
    messages = []
    embed_progress = {'revision': 0, 'agents': {}}
    if session_ids:
        agent_results = db_session.query(LeaderAgentResult).filter(
            LeaderAgentResult.leader_session_id.in_(session_ids)
        ).order_by(LeaderAgentResult.leader_session_id, LeaderAgentResult.sequence_number).all()
        final_reports = db_session.query(LeaderFinalReport).filter(
            LeaderFinalReport.leader_session_id.in_(session_ids)
        ).all()
        tool_call_logs = db_session.query(ToolCallLog).filter(
            ToolCallLog.leader_session_id.in_(session_ids)
        ).order_by(ToolCallLog.id.asc()).all()
        # 只包含绑定到该工作流的消息。令牌绝不能因后续消息恰好与该会话
        # 共享同一对话，就获得对这些后续消息的访问权。
        messages = db_session.query(Message).filter(
            Message.conversation_id == conversation.id,
            Message.leader_session_id.in_(session_ids),
        ).order_by(Message.created_at, Message.id).all()
        if not any(
            message.message_type == 'normal' and message.role == 'user'
            for message in messages
        ):
            # 兼容在初始问题被显式绑定到 LeaderSession 之前创建的启动请求。
            # Agent Teams 每次启动都会新建对话，因此只有最早的未绑定用户消息，
            # 才是那条遗留的启动问题。
            legacy_question = db_session.query(Message).filter(
                Message.conversation_id == conversation.id,
                Message.leader_session_id.is_(None),
                Message.message_type == 'normal',
                Message.role == 'user',
            ).order_by(Message.created_at.asc(), Message.id.asc()).first()
            if legacy_question is not None:
                messages.append(legacy_question)
                messages.sort(key=lambda item: (item.created_at, item.id))
        launch = db_session.query(AgentTeamsLaunch).filter_by(
            agentteams_leader_session_id=leader_sessions[-1].id,
        ).order_by(AgentTeamsLaunch.id.desc()).first()
        embed_progress = _get_agentteams_embed_progress(launch)

    reports_by_session = {report.leader_session_id: report.to_dict() for report in final_reports}
    results_by_session: dict[int, list] = {}
    for result in agent_results:
        results_by_session.setdefault(result.leader_session_id, []).append(result.to_dict())

    from services.decision_run_service import DecisionRunService
    run_service = DecisionRunService(db_session)
    snapshot = {
        'locale': (
            leader_sessions[-1].locale
            if leader_sessions
            else conversation.default_locale
        ),
        'conversation': conversation.to_dict(include_share_token=False),
        'sessions': [
            {
                **leader_session.to_dict(),
                'decision_run': run_service.projection_for_session(leader_session),
                'agent_results': results_by_session.get(leader_session.id, []),
                'final_report': reports_by_session.get(leader_session.id, ''),
            }
            for leader_session in leader_sessions
        ],
        'messages': [
            {
                'id': message.id,
                'type': (
                    message.role
                    if message.message_type == 'normal' and message.role
                    else message.message_type
                ),
                'content': message.content,
                'content_locale': message.content_locale,
                'sequence_number': message.sequence_number,
                'created_at': message.created_at.isoformat() + 'Z' if message.created_at else None,
                'leader_session_id': message.leader_session_id,
            }
            for message in messages
        ],
        'tool_calls': [
            {
                **tool_call.to_dict(),
                'leader_session_id': tool_call.leader_session_id,
            }
            for tool_call in tool_call_logs
        ],
        'agent_progress': list(embed_progress['agents'].values()),
    }
    snapshot['version'] = _build_agentteams_embed_status(db_session, token_record)['version']
    return snapshot
