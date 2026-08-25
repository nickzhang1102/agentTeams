"""Agent Teams 启动契约测试。"""
import asyncio
import hashlib
import os
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from models import (
    Conversation,
    DecisionRun,
    IntegrationClient,
    LeaderSession,
    LLMModel,
    Message,
    AgentTeamsEmbedToken,
    AgentTeamsLaunch,
    SystemConfig,
    ToolCallLog,
)
from services.agentteams_integration_account import (
    AGENTTEAMS_INTEGRATION_ENABLED,
    ensure_agentteams_service_account,
    resolve_agentteams_service_account,
)
from services.agentteams_integration_launch import (
    AGENTTEAMS_INTEGRATION_KEY,
    AgentTeamsLaunchError,
    _apply_progress_event,
    find_recoverable_agentteams_launch_ids,
    get_agentteams_embed_session,
    launch_agentteams_consultation,
    renew_agentteams_launch_lease,
    run_claimed_agentteams_workflow_events,
    stream_agentteams_embed_events,
)
from services.integration_gateway import IntegrationAdapterRegistry
from api.agentteams_integration_api import AgentTeamsLaunchRequest, router as agentteams_router
from database import get_db
from tests.conftest import TestSessionLocal
from utils.time_utils import utcnow_naive


def _add_config(db_session, key, value):
    existing = db_session.query(SystemConfig).filter_by(key=key).first()
    if existing:
        existing.value = str(value)
    else:
        db_session.add(SystemConfig(key=key, value=str(value), description=key))
    db_session.flush()


def _payload():
    return {
        'source': 'agentteams',
        'source_user_id': 'agentteams:123',
        'source_patient_id': '456',
        'source_conversation_id': 789,
        'title': '虚拟会诊',
        'message': '请基于病历生成多学科会诊意见。',
        'locale': 'zh-CN',
        'metadata': {'created_from': 'agentteams'},
    }


def _prepare_service_account(db_session):
    _add_config(db_session, AGENTTEAMS_INTEGRATION_KEY, 'test-integration-key')
    user = ensure_agentteams_service_account(db_session)
    if not db_session.query(LLMModel).first():
        db_session.add(LLMModel(
            model_id='test-model',
            display_name='Test Model',
            base_url='http://llm.test/v1',
            api_key='test-llm-key',
            is_enabled=True,
            is_default=True,
        ))
    db_session.commit()
    return user


def test_launch_request_defaults_to_chinese_locale():
    payload = _payload()
    payload.pop('locale')

    assert AgentTeamsLaunchRequest(**payload).locale == 'zh-CN'


def test_docker_backend_migration_path_fails_closed():
    """镜像实际的 CMD 必须在迁移失败时停止。"""
    backend_root = Path(__file__).resolve().parents[1]
    dockerfile = (backend_root / 'Dockerfile').read_text(encoding='utf-8')
    start_script = (backend_root / 'start.sh').read_text(encoding='utf-8')

    # 启动脚本必须是 COPY 进镜像的真实文件
    # （勿用 RUN echo 内联生成：\n 转义在 dash/bash 内建 echo 中不生效，会产出单行损坏脚本）
    assert 'COPY backend/start.sh /app/start.sh' in dockerfile
    assert 'CMD ["/app/start.sh"]' in dockerfile

    # set -e 保证 alembic 失败即中止启动（禁止 "||" 容错写法）
    assert 'set -e' in start_script
    assert 'alembic upgrade head\n' in start_script
    assert 'alembic upgrade head ||' not in start_script


def test_generic_gateway_uses_provider_neutral_refs_and_agentteams_adapter(client, monkeypatch):
    """新契约不得要求 patient_id/source_* 字段名。"""
    scheduled = []

    def fake_schedule(launch_id):
        # 通用路由是异步的，因为持久化调度器需要应用运行中的事件循环。
        # 将此断言保留在路由契约测试中，以便未来的同步重构无法在启动
        # 已计费后重新引入提交后的 500 错误。
        scheduled.append((launch_id, asyncio.get_running_loop().is_running()))

    monkeypatch.setattr(
        'api.agentteams_integration_api.schedule_agentteams_launch',
        fake_schedule,
    )
    session = TestSessionLocal()
    try:
        _prepare_service_account(session)
    finally:
        session.close()

    response = client.post(
        '/api/integrations/v1/agentteams/consultation-launches',
        json={
            'user_ref': 'external-user-1',
            'subject_ref': 'subject-42',
            'conversation_ref': 'conversation-9',
            'title': '外部系统会诊',
            'message': '请生成会诊意见。',
            'locale': 'zh-CN',
            'metadata': {'tenant': 'demo'},
        },
        headers={
            'X-Integration-Key': 'test-integration-key',
            'X-Request-Id': 'generic-request-1',
        },
    )

    assert response.status_code == 200
    assert scheduled and scheduled[0][1] is True
    data = response.json()
    assert data['status'] == 'created'
    session = TestSessionLocal()
    try:
        launch = session.query(AgentTeamsLaunch).filter_by(
            request_id='generic-request-1'
        ).one()
        assert launch.integration_client_key == 'agentteams'
        token = session.query(AgentTeamsEmbedToken).filter_by(
            conversation_id=launch.agentteams_conversation_id
        ).one()
        assert token.integration_client_key == 'agentteams'
        assert launch.source_user_id == 'external-user-1'
        assert launch.source_patient_id == 'subject-42'
        assert launch.source_conversation_id == 'conversation-9'
    finally:
        session.close()


def test_generic_launch_returns_committed_result_when_scheduler_fails(
    client,
    monkeypatch,
):
    """提交后调度器故障不得导致可重试的 500 错误。"""
    session = TestSessionLocal()
    try:
        _prepare_service_account(session)
    finally:
        session.close()

    schedule_calls = []

    def fail_schedule(launch_id):
        schedule_calls.append(launch_id)
        raise RuntimeError("scheduler unavailable")

    monkeypatch.setattr(
        'api.agentteams_integration_api.schedule_agentteams_launch',
        fail_schedule,
    )
    headers = {
        'X-Integration-Key': 'test-integration-key',
        'X-Request-Id': 'scheduler-failure-request',
    }
    payload = {
        'conversation_ref': 'scheduler-failure-conversation',
        'message': 'persist before scheduling',
    }

    first = client.post(
        '/api/integrations/v1/agentteams/consultation-launches',
        json=payload,
        headers=headers,
    )
    assert first.status_code == 200
    first_body = first.json()
    assert first_body['status'] == 'created'
    assert len(schedule_calls) == 1

    session = TestSessionLocal()
    try:
        counts = {
            'launches': session.query(AgentTeamsLaunch).count(),
            'conversations': session.query(Conversation).count(),
        }
    finally:
        session.close()

    replay = client.post(
        '/api/integrations/v1/agentteams/consultation-launches',
        json=payload,
        headers=headers,
    )
    assert replay.status_code == 200
    assert replay.json()['agentteams_conversation_id'] == first_body['agentteams_conversation_id']
    assert len(schedule_calls) == 2

    session = TestSessionLocal()
    try:
        assert session.query(AgentTeamsLaunch).count() == counts['launches']
        assert session.query(Conversation).count() == counts['conversations']
    finally:
        session.close()


def test_generic_gateway_does_not_claim_unregistered_adapter(client):
    session = TestSessionLocal()
    try:
        service_account = _prepare_service_account(session)
        client_row = IntegrationClient(
            client_key='future-system',
            # 未注册的适配器键：网关必须在分发前 fail-closed。
            adapter_key='future-protocol',
            display_name='Future System',
            credential_hash='sha256:' + hashlib.sha256(b'future-key').hexdigest(),
            service_account_id=service_account.id,
            enabled=True,
            capabilities_json={'launch': True},
        )
        session.add(client_row)
        session.commit()
    finally:
        session.close()

    response = client.post(
        '/api/integrations/v1/future-system/consultation-launches',
        json={'message': 'future payload'},
        headers={
            'X-Integration-Key': 'future-key',
            'X-Request-Id': 'future-request-1',
        },
    )

    assert response.status_code == 501
    assert response.json()['detail']['error'] == 'integration_adapter_unavailable'


def test_generic_status_reconcile_and_renew_are_read_only(client, monkeypatch):
    monkeypatch.setattr('api.agentteams_integration_api.schedule_agentteams_launch', lambda launch_id: None)
    session = TestSessionLocal()
    try:
        _prepare_service_account(session)
    finally:
        session.close()

    headers = {
        'X-Integration-Key': 'test-integration-key',
        'X-Request-Id': 'generic-read-only-1',
    }
    launched = client.post(
        '/api/integrations/v1/agentteams/consultation-launches',
        json={'conversation_ref': 'generic-read-only-conversation', 'message': 'read only'},
        headers=headers,
    )
    assert launched.status_code == 200
    before = TestSessionLocal()
    try:
        conversation_count = before.query(Conversation).count()
    finally:
        before.close()

    status = client.get(
        '/api/integrations/v1/agentteams/consultation-launches/generic-read-only-1',
        headers={'X-Integration-Key': 'test-integration-key'},
    )
    reconcile = client.post(
        '/api/integrations/v1/agentteams/consultation-launches/generic-read-only-1/reconcile',
        headers={'X-Integration-Key': 'test-integration-key'},
    )
    renew = client.post(
        '/api/integrations/v1/agentteams/embed-sessions/renew',
        json={
            'conversation_ref': 'generic-read-only-conversation',
            'request_id': 'generic-read-only-1',
        },
        headers={'X-Integration-Key': 'test-integration-key'},
    )

    assert status.status_code == 200
    assert reconcile.status_code == 200
    assert status.json()['request_id'] == reconcile.json()['request_id'] == 'generic-read-only-1'
    assert renew.status_code == 200
    after = TestSessionLocal()
    try:
        assert after.query(Conversation).count() == conversation_count
    finally:
        after.close()


def test_multiple_clients_share_adapter_key_and_keep_request_namespaces_isolated(client):
    calls = []

    class FixtureAdapter:
        adapter_key = 'contract-fixture'

        def launch(self, db_session, *, payload, request_id, client):
            calls.append(('launch', client.client_key, request_id))
            return {'request_id': request_id, 'status': 'created', 'adapter': self.adapter_key}

        def get_status(self, db_session, *, request_id, client):
            calls.append(('status', client.client_key, request_id))
            return {'found': True, 'request_id': request_id, 'status': 'created'}

        def reconcile(self, db_session, *, request_id, client):
            return self.get_status(db_session, request_id=request_id, client=client)

        def renew_access(self, db_session, *, refs, client):
            return {'request_id': refs.get('request_id'), 'status': 'created'}

        def schedule_launch(self, db_session, *, result, request_id, client):
            result.pop('_start_background', None)

    adapter = FixtureAdapter()
    IntegrationAdapterRegistry.register(adapter)
    session = TestSessionLocal()
    try:
        service_account = _prepare_service_account(session)
        for client_key, supplied_key in (('fixture-a', 'fixture-a-key'), ('fixture-b', 'fixture-b-key')):
            session.add(IntegrationClient(
                client_key=client_key,
                adapter_key='contract-fixture',
                display_name=client_key,
                credential_hash='sha256:' + hashlib.sha256(supplied_key.encode()).hexdigest(),
                service_account_id=service_account.id,
                enabled=True,
                capabilities_json={'launch': True, 'status_query': True, 'reconcile': True},
            ))
        session.commit()
    finally:
        session.close()

    try:
        first = client.post(
            '/api/integrations/v1/fixture-a/consultation-launches',
            json={'message': 'fixture'},
            headers={'X-Integration-Key': 'fixture-a-key', 'X-Request-Id': 'same-request-id'},
        )
        second = client.post(
            '/api/integrations/v1/fixture-b/consultation-launches',
            json={'message': 'fixture'},
            headers={'X-Integration-Key': 'fixture-b-key', 'X-Request-Id': 'same-request-id'},
        )
        status = client.get(
            '/api/integrations/v1/fixture-b/consultation-launches/same-request-id',
            headers={'X-Integration-Key': 'fixture-b-key'},
        )
        assert first.status_code == second.status_code == 200
        assert status.status_code == 200
        assert calls == [
            ('launch', 'fixture-a', 'same-request-id'),
            ('launch', 'fixture-b', 'same-request-id'),
            ('status', 'fixture-b', 'same-request-id'),
        ]
    finally:
        IntegrationAdapterRegistry._adapters.pop('contract-fixture', None)


class _RecordingFixtureAdapter:
    """用于证明网关规则对适配器保持中立的第二个最小适配器。"""

    adapter_key = 'contract-fixture'

    def __init__(self):
        self.calls = []

    def launch(self, db_session, *, payload, request_id, client):
        self.calls.append(('launch', client.client_key, request_id))
        return {'request_id': request_id, 'status': 'created', 'adapter': self.adapter_key}

    def get_status(self, db_session, *, request_id, client):
        self.calls.append(('status', client.client_key, request_id))
        return {'found': True, 'request_id': request_id, 'status': 'created'}

    def reconcile(self, db_session, *, request_id, client):
        self.calls.append(('reconcile', client.client_key, request_id))
        return self.get_status(db_session, request_id=request_id, client=client)

    def renew_access(self, db_session, *, refs, client):
        self.calls.append(('renew', client.client_key, dict(refs)))
        return {'status': 'created', 'access_ref': 'fixture-access-1'}

    def schedule_launch(self, db_session, *, result, request_id, client):
        result.pop('_start_background', None)


def _seed_fixture_client(db_session, client_key, supplied_key, *, capabilities):
    service_account = _prepare_service_account(db_session)
    db_session.add(IntegrationClient(
        client_key=client_key,
        adapter_key='contract-fixture',
        display_name=client_key,
        credential_hash='sha256:' + hashlib.sha256(supplied_key.encode()).hexdigest(),
        service_account_id=service_account.id,
        enabled=True,
        capabilities_json=capabilities,
    ))
    db_session.commit()


def test_second_adapter_supports_full_spi_including_renew(client):
    adapter = _RecordingFixtureAdapter()
    IntegrationAdapterRegistry.register(adapter)
    session = TestSessionLocal()
    try:
        _seed_fixture_client(
            session,
            'fixture-full-spi',
            'fixture-full-spi-key',
            capabilities={'launch': True, 'status_query': True, 'reconcile': True, 'renew_access': True},
        )
    finally:
        session.close()

    try:
        renewed = client.post(
            '/api/integrations/v1/fixture-full-spi/embed-sessions/renew',
            json={'conversation_ref': 'fixture-conversation', 'request_id': 'fixture-request-1'},
            headers={'X-Integration-Key': 'fixture-full-spi-key'},
        )
        assert renewed.status_code == 200
        assert renewed.json()['access_ref'] == 'fixture-access-1'
        assert adapter.calls == [
            ('renew', 'fixture-full-spi', {'conversation_ref': 'fixture-conversation', 'request_id': 'fixture-request-1'}),
        ]
    finally:
        IntegrationAdapterRegistry._adapters.pop('contract-fixture', None)


@pytest.mark.parametrize(
    'capabilities,method,path,body',
    (
        ({'launch': True, 'renew_access': True}, 'get', '/api/integrations/v1/fixture-limited/consultation-launches/req-1', None),
        ({'launch': True, 'status_query': True}, 'post', '/api/integrations/v1/fixture-limited/embed-sessions/renew', {'conversation_ref': 'c'}),
        ({'status_query': True}, 'post', '/api/integrations/v1/fixture-limited/consultation-launches', {'message': 'x'}),
    ),
    ids=['status_disabled', 'renew_disabled', 'launch_disabled'],
)
def test_gateway_capability_denial_is_adapter_neutral(client, capabilities, method, path, body):
    adapter = _RecordingFixtureAdapter()
    IntegrationAdapterRegistry.register(adapter)
    session = TestSessionLocal()
    try:
        _seed_fixture_client(session, 'fixture-limited', 'fixture-limited-key', capabilities=capabilities)
    finally:
        session.close()

    try:
        headers = {'X-Integration-Key': 'fixture-limited-key', 'X-Request-Id': 'req-1'}
        response = (
            client.get(path, headers=headers)
            if method == 'get'
            else client.post(path, json=body, headers=headers)
        )
        assert response.status_code == 403
        assert response.json()['detail']['error'] == 'integration_capability_disabled'
        assert adapter.calls == []
    finally:
        IntegrationAdapterRegistry._adapters.pop('contract-fixture', None)


def test_second_adapter_launch_does_not_create_local_workflow_records(client):
    """工作流调度由适配器所有，而非由网关强制实施。

    测试适配器不创建任何本地记录；网关不得代表第二个适配器
    创建 AgentTeamsLaunch/Conversation 记录。
    """
    adapter = _RecordingFixtureAdapter()
    IntegrationAdapterRegistry.register(adapter)
    session = TestSessionLocal()
    try:
        _seed_fixture_client(
            session,
            'fixture-neutral',
            'fixture-neutral-key',
            capabilities={'launch': True},
        )
    finally:
        session.close()

    try:
        response = client.post(
            '/api/integrations/v1/fixture-neutral/consultation-launches',
            json={'message': 'fixture launch'},
            headers={'X-Integration-Key': 'fixture-neutral-key', 'X-Request-Id': 'fixture-neutral-1'},
        )
        assert response.status_code == 200
        assert adapter.calls == [('launch', 'fixture-neutral', 'fixture-neutral-1')]
        session = TestSessionLocal()
        try:
            assert session.query(Conversation).count() == 0
            assert session.query(AgentTeamsLaunch).count() == 0
        finally:
            session.close()
    finally:
        IntegrationAdapterRegistry._adapters.pop('contract-fixture', None)


def test_shared_agentteams_adapter_cannot_cross_client_status_or_renew_by_external_ref(client, monkeypatch):
    monkeypatch.setattr('api.agentteams_integration_api.schedule_agentteams_launch', lambda launch_id: None)
    session = TestSessionLocal()
    try:
        service_account = _prepare_service_account(session)
        for client_key, supplied_key in (('tenant-a', 'tenant-a-key'), ('tenant-b', 'tenant-b-key')):
            session.add(IntegrationClient(
                client_key=client_key,
                adapter_key='agentteams',
                display_name=client_key,
                credential_hash='sha256:' + hashlib.sha256(supplied_key.encode()).hexdigest(),
                service_account_id=service_account.id,
                enabled=True,
                capabilities_json={'launch': True, 'status_query': True, 'reconcile': True, 'renew_access': True},
            ))
        session.commit()
    finally:
        session.close()

    launched = client.post(
        '/api/integrations/v1/tenant-a/consultation-launches',
        json={'conversation_ref': 'same-external-conversation', 'message': 'tenant a'},
        headers={'X-Integration-Key': 'tenant-a-key', 'X-Request-Id': 'same-request'},
    )
    assert launched.status_code == 200
    session = TestSessionLocal()
    try:
        launch = session.query(AgentTeamsLaunch).filter_by(
            integration_client_key='tenant-a',
            request_id='tenant-a:same-request',
        ).one()
        token = session.query(AgentTeamsEmbedToken).filter_by(
            conversation_id=launch.agentteams_conversation_id,
        ).one()
        assert token.integration_client_key == 'tenant-a'
    finally:
        session.close()

    cross_status = client.get(
        '/api/integrations/v1/tenant-b/consultation-launches/same-request',
        headers={'X-Integration-Key': 'tenant-b-key'},
    )
    assert cross_status.status_code == 200
    assert cross_status.json()['status'] == 'not_found'

    cross_renew = client.post(
        '/api/integrations/v1/tenant-b/embed-sessions/renew',
        json={'conversation_ref': 'same-external-conversation'},
        headers={'X-Integration-Key': 'tenant-b-key'},
    )
    assert cross_renew.status_code == 404
    assert cross_renew.json()['detail']['error'] == 'agentteams_launch_not_found'


def test_generic_launch_accepts_long_request_id_for_shared_adapter_client(client, monkeypatch):
    """外部契约内的长 request-id 不得因 client 命名空间前缀被误拒。"""
    monkeypatch.setattr('api.agentteams_integration_api.schedule_agentteams_launch', lambda launch_id: None)
    session = TestSessionLocal()
    try:
        service_account = _prepare_service_account(session)
        session.add(IntegrationClient(
            client_key='tenant-a',
            adapter_key='agentteams',
            display_name='tenant-a',
            credential_hash='sha256:' + hashlib.sha256(b'tenant-a-key').hexdigest(),
            service_account_id=service_account.id,
            enabled=True,
            capabilities_json={'launch': True, 'status_query': True},
        ))
        session.commit()
    finally:
        session.close()

    # 95 字符外部 ID 加 'tenant-a:' 前缀后为 104 字符，
    # 超出旧存储宽度 100，但必须落在新存储宽度内。
    long_request_id = 'r' * 95
    launched = client.post(
        '/api/integrations/v1/tenant-a/consultation-launches',
        json={'conversation_ref': 'long-request-id', 'message': 'long id'},
        headers={'X-Integration-Key': 'tenant-a-key', 'X-Request-Id': long_request_id},
    )
    assert launched.status_code == 200

    session = TestSessionLocal()
    try:
        launch = session.query(AgentTeamsLaunch).filter_by(
            integration_client_key='tenant-a',
            request_id=f'tenant-a:{long_request_id}',
        ).one()
        assert launch.agentteams_conversation_id is not None
    finally:
        session.close()


def test_launch_idempotency_is_scoped_per_client_for_same_external_request_id(client, monkeypatch):
    """相同外部 request-id 在不同 client（含遗留密钥）下必须各自独立。"""
    monkeypatch.setattr('api.agentteams_integration_api.schedule_agentteams_launch', lambda launch_id: None)
    session = TestSessionLocal()
    try:
        service_account = _prepare_service_account(session)
        session.add(IntegrationClient(
            client_key='agentteams',
            adapter_key='agentteams',
            display_name='Agent Teams',
            credential_hash='sha256:' + hashlib.sha256(b'test-integration-key').hexdigest(),
            service_account_id=service_account.id,
            enabled=True,
            capabilities_json={'launch': True, 'status_query': True},
        ))
        session.add(IntegrationClient(
            client_key='tenant-a',
            adapter_key='agentteams',
            display_name='tenant-a',
            credential_hash='sha256:' + hashlib.sha256(b'tenant-a-key').hexdigest(),
            service_account_id=service_account.id,
            enabled=True,
            capabilities_json={'launch': True, 'status_query': True},
        ))
        session.commit()
    finally:
        session.close()

    tenant_launched = client.post(
        '/api/integrations/v1/tenant-a/consultation-launches',
        json={'conversation_ref': 'same-ref', 'message': 'tenant a body'},
        headers={'X-Integration-Key': 'tenant-a-key', 'X-Request-Id': 'shared-request'},
    )
    assert tenant_launched.status_code == 200

    # 遗留密钥持有者用相同外部 request-id 启动：不得命中 tenant-a 的记录，
    # 也不得因唯一约束冲突产生 500，而是拥有自己独立的启动。
    legacy_launched = client.post(
        '/api/integrations/v1/agentteams/consultation-launches',
        json={'conversation_ref': 'legacy-ref', 'message': 'legacy body'},
        headers={
            'X-Integration-Key': 'test-integration-key',
            'X-Request-Id': 'tenant-a:shared-request',
        },
    )
    assert legacy_launched.status_code == 200

    session = TestSessionLocal()
    try:
        rows = session.query(AgentTeamsLaunch).filter_by(source='agentteams').all()
        assert len(rows) == 2
        by_owner = {row.integration_client_key: row for row in rows}
        assert set(by_owner) == {'tenant-a', 'agentteams'}
        assert (
            by_owner['tenant-a'].agentteams_conversation_id
            != by_owner['agentteams'].agentteams_conversation_id
        )
    finally:
        session.close()


def test_generic_gateway_enforces_launch_capability(client):
    session = TestSessionLocal()
    try:
        service_account = _prepare_service_account(session)
        session.add(IntegrationClient(
            client_key='agentteams',
            adapter_key='agentteams',
            display_name='Agent Teams',
            credential_hash='sha256:' + hashlib.sha256(b'test-integration-key').hexdigest(),
            service_account_id=service_account.id,
            enabled=True,
            capabilities_json={'launch': False},
        ))
        session.commit()
    finally:
        session.close()

    response = client.post(
        '/api/integrations/v1/agentteams/consultation-launches',
        json={
            'conversation_ref': 'capability-disabled',
            'message': 'must not launch',
        },
        headers={
            'X-Integration-Key': 'test-integration-key',
            'X-Request-Id': 'capability-disabled',
        },
    )

    assert response.status_code == 403
    assert response.json()['detail']['error'] == 'integration_capability_disabled'


def test_legacy_service_account_resolution_is_fail_closed_for_unsafe_account(client):
    session = TestSessionLocal()
    try:
        service_account = _prepare_service_account(session)
        service_account.is_admin = True
        session.commit()
        assert resolve_agentteams_service_account(session) is None
    finally:
        session.close()


@pytest.mark.parametrize(
    ('account_type', 'login_disabled', 'is_admin'),
    [
        ('human', True, False),
        ('service', False, False),
        ('service', True, True),
    ],
)
def test_generic_gateway_rejects_unsafe_service_account_policy(
    client,
    account_type,
    login_disabled,
    is_admin,
):
    session = TestSessionLocal()
    try:
        service_account = _prepare_service_account(session)
        service_account.account_type = account_type
        service_account.login_disabled = login_disabled
        service_account.is_admin = is_admin
        session.add(IntegrationClient(
            client_key='future-system',
            adapter_key='future-protocol',
            display_name='Future System',
            credential_hash='sha256:' + hashlib.sha256(b'future-key').hexdigest(),
            service_account_id=service_account.id,
            enabled=True,
            capabilities_json={'launch': True},
        ))
        session.commit()
    finally:
        session.close()

    response = client.post(
        '/api/integrations/v1/future-system/consultation-launches',
        json={'conversation_ref': 'unsafe-account', 'message': 'must not launch'},
        headers={
            'X-Integration-Key': 'future-key',
            'X-Request-Id': 'unsafe-account',
        },
    )

    assert response.status_code == 403
    assert response.json()['detail']['error'] == 'service_account_not_configured'


def test_launch_rejects_request_id_longer_than_storage_contract(client):
    session = TestSessionLocal()
    try:
        _prepare_service_account(session)
    finally:
        session.close()

    response = client.post(
        '/api/integrations/agentteams/consultation-launches',
        json=_payload(),
        headers={
            'X-Integration-Key': 'test-integration-key',
            'X-Request-Id': 'x' * 101,
        },
    )

    assert response.status_code == 400
    assert response.json()['detail']['error'] == 'invalid_payload'


@pytest.mark.parametrize('field', ['source_user_id', 'source_patient_id', 'source_conversation_id'])
def test_launch_rejects_source_reference_longer_than_storage_contract(client, field):
    session = TestSessionLocal()
    try:
        _prepare_service_account(session)
    finally:
        session.close()

    payload = _payload()
    payload[field] = 'x' * 101
    response = client.post(
        '/api/integrations/agentteams/consultation-launches',
        json=payload,
        headers={
            'X-Integration-Key': 'test-integration-key',
            'X-Request-Id': f'req-long-{field}',
        },
    )

    assert response.status_code == 400
    assert response.json()['detail']['error'] == 'invalid_payload'


def test_agent_report_progress_is_visible_only_after_the_report_event():
    progress = {'revision': 0, 'agents': {}}
    decomposition = {
        'subtasks': [
            {'id': 'subtask-1', 'goal': '整理病史', 'status': 'completed', 'tools': []},
        ],
    }

    _apply_progress_event(progress, {
        'type': 'task_decomposition',
        'agent_id': 'medical-oncologist',
        'agent_name': '肿瘤内科专家',
        'subtasks': decomposition['subtasks'],
    })
    _apply_progress_event(progress, {
        'type': 'subtask_completed',
        'agent_id': 'medical-oncologist',
        'subtask_id': 'subtask-1',
        'status': 'completed',
    })

    agent = progress['agents']['medical-oncologist']
    assert agent['status'] == 'running'
    assert not agent.get('content')

    _apply_progress_event(progress, {
        'type': 'agent_result',
        'agent_id': 'medical-oncologist',
        'agent_name': '肿瘤内科专家',
        'content': '第一位专家的完整报告',
        'summary': {'one_sentence': '核心结论'},
        'decomposition': decomposition,
        'status': 'success',
    })

    agent = progress['agents']['medical-oncologist']
    assert agent['status'] == 'completed'
    assert agent['content'] == '第一位专家的完整报告'
    assert agent['summary']['one_sentence'] == '核心结论'


def test_embed_event_db_dependency_closes_before_stream_body():
    route = next(
        route
        for route in agentteams_router.routes
        if route.name == 'stream_embed_session_events'
    )
    db_dependency = next(
        dependency
        for dependency in route.dependant.dependencies
        if dependency.call is get_db
    )

    assert db_dependency.scope == 'function'


def test_launch_preserves_long_message_in_conversation_and_leader_session(client, monkeypatch):
    monkeypatch.setattr('api.agentteams_integration_api.schedule_agentteams_launch', lambda launch_id: None)
    session = TestSessionLocal()
    try:
        _prepare_service_account(session)
    finally:
        session.close()

    long_message = '\nBEGIN-PATIENT-CONTEXT\n' + ('X' * 61000) + '\nEND-PATIENT-CONTEXT\n'
    payload = _payload()
    payload['message'] = long_message
    response = client.post(
        '/api/integrations/agentteams/consultation-launches',
        json=payload,
        headers={
            'X-Integration-Key': 'test-integration-key',
            'X-Request-Id': 'req-long-message',
        },
    )

    assert response.status_code == 200
    data = response.json()
    session = TestSessionLocal()
    try:
        user_message = session.query(Message).filter_by(
            conversation_id=data['agentteams_conversation_id'],
            message_type='normal',
        ).one()
        leader_session = session.get(LeaderSession, data['agentteams_session_id'])

        assert user_message.content['text'] == long_message
        assert user_message.leader_session_id == leader_session.id
        assert leader_session.user_message == long_message
    finally:
        session.close()


@pytest.mark.asyncio
async def test_embed_event_stream_emits_version_changes_and_done(monkeypatch):
    statuses = iter([
        {
            'conversation_id': 10,
            'status': 'monitoring',
            'terminal': False,
            'version': '20:monitoring:1:0:0',
        },
        {
            'conversation_id': 10,
            'status': 'completed',
            'terminal': True,
            'version': '20:completed:2:1:1',
        },
    ])

    monkeypatch.setattr(
        'services.agentteams_integration_launch._read_agentteams_embed_status',
        lambda *args: next(statuses),
    )

    events = [
        event
        async for event in stream_agentteams_embed_events(
            'embed-token', poll_interval_seconds=0
        )
    ]

    assert [event['type'] for event in events] == [
        'embed_snapshot', 'embed_snapshot', 'done'
    ]
    assert events[0]['version'] == '20:monitoring:1:0:0'
    assert events[1]['terminal'] is True


def test_launch_rejects_invalid_integration_key(client):
    response = client.post(
        '/api/integrations/agentteams/consultation-launches',
        json=_payload(),
        headers={'X-Request-Id': 'req-invalid'},
    )

    assert response.status_code == 401
    assert response.json()['error'] == 'invalid_integration_key'


def test_launch_requires_service_account(client):
    session = TestSessionLocal()
    try:
        _add_config(session, AGENTTEAMS_INTEGRATION_KEY, 'test-integration-key')
        session.commit()
    finally:
        session.close()

    response = client.post(
        '/api/integrations/agentteams/consultation-launches',
        json=_payload(),
        headers={
            'X-Integration-Key': 'test-integration-key',
            'X-Request-Id': 'req-no-service',
        },
    )

    assert response.status_code == 403
    assert response.json()['detail']['error'] == 'service_account_not_configured'


def test_launch_rejects_when_integration_disabled(client):
    session = TestSessionLocal()
    try:
        _prepare_service_account(session)
        _add_config(session, AGENTTEAMS_INTEGRATION_ENABLED, 'false')
        session.commit()
    finally:
        session.close()

    response = client.post(
        '/api/integrations/agentteams/consultation-launches',
        json=_payload(),
        headers={
            'X-Integration-Key': 'test-integration-key',
            'X-Request-Id': 'req-disabled',
        },
    )

    assert response.status_code == 403
    assert response.json()['detail']['error'] == 'integration_disabled'


def test_launch_rejects_invalid_payload(client):
    session = TestSessionLocal()
    try:
        _add_config(session, AGENTTEAMS_INTEGRATION_KEY, 'test-integration-key')
        session.commit()
    finally:
        session.close()

    payload = _payload()
    payload.pop('message')

    response = client.post(
        '/api/integrations/agentteams/consultation-launches',
        json=payload,
        headers={
            'X-Integration-Key': 'test-integration-key',
            'X-Request-Id': 'req-invalid-payload',
        },
    )

    assert response.status_code == 400
    assert response.json()['detail']['error'] == 'invalid_payload'


def test_embed_token_answers_only_its_bound_questioning_session(client, monkeypatch):
    monkeypatch.setattr('api.agentteams_integration_api.schedule_agentteams_launch', lambda launch_id: None)
    session = TestSessionLocal()
    try:
        _prepare_service_account(session)
    finally:
        session.close()

    launch_response = client.post(
        '/api/integrations/agentteams/consultation-launches',
        json=_payload(),
        headers={
            'X-Integration-Key': 'test-integration-key',
            'X-Request-Id': 'req-embed-answer',
        },
    )
    assert launch_response.status_code == 200
    launch_data = launch_response.json()

    session = TestSessionLocal()
    try:
        leader_session = session.get(LeaderSession, launch_data['agentteams_session_id'])
        leader_session.state = 'questioning'
        session.add(Message.create_leader_message(
            conversation_id=leader_session.conversation_id,
            leader_session_id=leader_session.id,
            message_type='question',
            content={'questions': [{'question': '当前治疗目标？', 'options': ['治愈', '控制', '缓解']}]},
            sequence_number=1,
        ))
        session.commit()
    finally:
        session.close()

    async def completed_continuation(**kwargs):
        assert kwargs['session_id'] == launch_data['agentteams_session_id']
        assert kwargs['answers'] == ['控制']
        yield {
            'type': 'task_decomposition',
            'agent_id': 'medical-oncologist',
            'agent_name': '肿瘤内科专家',
            'subtasks': [{
                'id': 'subtask-after-answer',
                'goal': '结合补充答案核对治疗目标',
                'status': 'pending',
                'tools': [],
            }],
        }
        yield {
            'type': 'subtask_started',
            'agent_id': 'medical-oncologist',
            'agent_name': '肿瘤内科专家',
            'subtask_id': 'subtask-after-answer',
            'goal': '结合补充答案核对治疗目标',
            'tools': [],
        }
        yield {'type': 'done', 'session_id': kwargs['session_id']}

    monkeypatch.setattr(
        'leader.question_answers.async_continue_leader_workflow',
        completed_continuation,
    )

    response = client.post(
        f"/api/integrations/agentteams/embed-sessions/{launch_data['embed_token']}/answers",
        json={
            'session_id': launch_data['agentteams_session_id'],
            'answers': ['控制'],
        },
    )

    assert response.status_code == 200
    assert '"type": "done"' in response.text
    session = TestSessionLocal()
    try:
        answer = session.query(Message).filter_by(
            leader_session_id=launch_data['agentteams_session_id'],
            message_type='answer',
        ).one()
        assert answer.content['answers'] == [{'question': '当前治疗目标？', 'answer': '控制'}]
        progress = get_agentteams_embed_session(
            session,
            launch_data['embed_token'],
        )['agent_progress']
        assert progress[0]['currentSubtaskId'] == 'subtask-after-answer'
        assert progress[0]['decomposition']['subtasks'][0]['status'] == 'running'
        launch = session.query(AgentTeamsLaunch).filter_by(
            agentteams_leader_session_id=launch_data['agentteams_session_id'],
        ).one()
        assert launch.status == 'questioning'
        assert launch.lease_owner is None
        assert launch.lease_expires_at is None
        launch.status = 'running'
        launch.lease_owner = 'answer-worker'
        launch.lease_expires_at = utcnow_naive() + timedelta(minutes=5)
        session.commit()
    finally:
        session.close()

    busy = client.post(
        f"/api/integrations/agentteams/embed-sessions/{launch_data['embed_token']}/answers",
        json={'session_id': launch_data['agentteams_session_id'], 'answers': ['缓解']},
    )
    assert busy.status_code == 409
    assert busy.json()['detail']['error'] == 'embed_session_already_running'
    session = TestSessionLocal()
    try:
        assert session.query(Message).filter_by(
            leader_session_id=launch_data['agentteams_session_id'],
            message_type='answer',
        ).count() == 1
        launch = session.query(AgentTeamsLaunch).filter_by(
            agentteams_leader_session_id=launch_data['agentteams_session_id'],
        ).one()
        launch.status = 'questioning'
        launch.lease_owner = None
        launch.lease_expires_at = None
        session.commit()
    finally:
        session.close()

    mismatch = client.post(
        f"/api/integrations/agentteams/embed-sessions/{launch_data['embed_token']}/answers",
        json={'session_id': launch_data['agentteams_session_id'] + 1, 'answers': ['控制']},
    )
    assert mismatch.status_code == 403
    assert mismatch.json()['detail']['error'] == 'embed_session_mismatch'

    session = TestSessionLocal()
    try:
        leader_session = session.get(LeaderSession, launch_data['agentteams_session_id'])
        leader_session.state = 'completed'
        session.commit()
    finally:
        session.close()

    not_questioning = client.post(
        f"/api/integrations/agentteams/embed-sessions/{launch_data['embed_token']}/answers",
        json={'session_id': launch_data['agentteams_session_id'], 'answers': ['控制']},
    )
    assert not_questioning.status_code == 409
    assert not_questioning.json()['detail']['error'] == 'embed_session_not_questioning'


def test_launch_creates_conversation_embed_token_and_is_idempotent(client, monkeypatch):
    calls = []

    def fake_background(launch_id):
        calls.append(launch_id)
        session = TestSessionLocal()
        try:
            launch = session.get(AgentTeamsLaunch, launch_id)
            launch.status = 'running'
            launch.lease_owner = 'test-worker'
            launch.lease_expires_at = utcnow_naive() + timedelta(minutes=5)
            session.commit()
        finally:
            session.close()

    monkeypatch.setattr(
        'api.agentteams_integration_api.schedule_agentteams_launch',
        fake_background,
    )

    session = TestSessionLocal()
    try:
        service_user = _prepare_service_account(session)
        service_user_id = service_user.id
    finally:
        session.close()

    headers = {
        'X-Integration-Key': 'test-integration-key',
        'X-Request-Id': 'req-success',
    }
    first = client.post(
        '/api/integrations/agentteams/consultation-launches',
        json=_payload(),
        headers=headers,
    )
    second = client.post(
        '/api/integrations/agentteams/consultation-launches',
        json=_payload(),
        headers=headers,
    )

    assert first.status_code == 200
    assert second.status_code == 200
    first_data = first.json()
    second_data = second.json()
    assert first_data['agentteams_conversation_id'] == second_data['agentteams_conversation_id']
    assert first_data['agentteams_session_id'] == second_data['agentteams_session_id']
    assert first_data['run_id'] == second_data['run_id']
    assert first_data['run_id']
    assert first_data['embed_token'] != second_data['embed_token']
    assert first_data['agentteams_share_token']
    assert first_data['embed_path'].endswith('?locale=zh-CN')
    assert calls == [1]

    first_token_response = client.get(
        f"/api/integrations/agentteams/embed-sessions/{first_data['embed_token']}"
    )
    assert first_token_response.status_code == 200

    session = TestSessionLocal()
    try:
        conversations = session.query(Conversation).all()
        launches = session.query(AgentTeamsLaunch).all()
        embed_tokens = session.query(AgentTeamsEmbedToken).all()

        assert len(conversations) == 1
        assert conversations[0].user_id == service_user.id
        assert conversations[0].is_review_mode is True
        assert conversations[0].category == 'medical'
        assert conversations[0].default_locale == 'zh-CN'
        assert conversations[0].share_token == first_data['agentteams_share_token']
        assert len(launches) == 1
        assert launches[0].request_id == 'req-success'
        assert launches[0].agentteams_conversation_id == conversations[0].id
        assert len(embed_tokens) == 2
        assert sum(token.revoked_at is None for token in embed_tokens) == 2
        assert all(token.token_hash not in {first_data['embed_token'], second_data['embed_token']} for token in embed_tokens)
        leader_session = session.get(LeaderSession, first_data['agentteams_session_id'])
        assert leader_session.locale == 'zh-CN'
        user_message = session.query(Message).filter_by(
            conversation_id=conversations[0].id,
            message_type='normal',
        ).one()
        assert user_message.content_locale == 'zh-CN'
    finally:
        session.close()


def test_launch_reconciliation_is_read_only(client, monkeypatch):
    scheduled = []
    monkeypatch.setattr(
        'api.agentteams_integration_api.schedule_agentteams_launch',
        lambda launch_id: scheduled.append(launch_id),
    )
    session = TestSessionLocal()
    try:
        _prepare_service_account(session)
    finally:
        session.close()

    headers = {
        'X-Integration-Key': 'test-integration-key',
        'X-Request-Id': 'req-read-only-reconciliation',
    }
    created = client.post(
        '/api/integrations/agentteams/consultation-launches',
        json=_payload(),
        headers=headers,
    )
    assert created.status_code == 200
    scheduled.clear()

    found = client.get(
        '/api/integrations/agentteams/consultation-launches/req-read-only-reconciliation',
        headers={'X-Integration-Key': 'test-integration-key'},
    )
    assert found.status_code == 200
    assert found.json() == {
        'found': True,
        'request_id': 'req-read-only-reconciliation',
        'status': 'created',
        'agentteams_conversation_id': created.json()['agentteams_conversation_id'],
        'agentteams_session_id': created.json()['agentteams_session_id'],
        'source_conversation_id': '789',
        'error_code': None,
    }
    assert scheduled == []

    session = TestSessionLocal()
    try:
        assert session.query(Conversation).count() == 1
        assert session.query(AgentTeamsEmbedToken).count() == 1
    finally:
        session.close()

    missing = client.get(
        '/api/integrations/agentteams/consultation-launches/missing-request',
        headers={'X-Integration-Key': 'test-integration-key'},
    )
    assert missing.status_code == 200
    assert missing.json() == {
        'found': False,
        'request_id': 'missing-request',
        'status': 'not_found',
    }


def test_idempotent_launch_rejects_payload_for_another_patient(client, monkeypatch):
    monkeypatch.setattr('api.agentteams_integration_api.schedule_agentteams_launch', lambda launch_id: None)
    session = TestSessionLocal()
    try:
        _prepare_service_account(session)
    finally:
        session.close()

    headers = {
        'X-Integration-Key': 'test-integration-key',
        'X-Request-Id': 'req-payload-conflict',
    }
    first = client.post(
        '/api/integrations/agentteams/consultation-launches',
        json=_payload(),
        headers=headers,
    )
    conflicting_payload = _payload()
    conflicting_payload['source_patient_id'] = 'another-patient'
    conflicting_payload['message'] = '另一位患者的病历。'
    second = client.post(
        '/api/integrations/agentteams/consultation-launches',
        json=conflicting_payload,
        headers=headers,
    )

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()['detail']['error'] == 'idempotency_conflict'

    session = TestSessionLocal()
    try:
        assert session.query(AgentTeamsLaunch).count() == 1
        assert session.query(Conversation).count() == 1
        assert session.query(AgentTeamsEmbedToken).count() == 1
    finally:
        session.close()


def test_concurrent_idempotency_winner_revalidates_conflicting_payload(client, monkeypatch):
    monkeypatch.setattr('api.agentteams_integration_api.schedule_agentteams_launch', lambda launch_id: None)
    setup_session = TestSessionLocal()
    try:
        _prepare_service_account(setup_session)
    finally:
        setup_session.close()

    request_id = 'req-concurrent-payload-conflict'
    first = client.post(
        '/api/integrations/agentteams/consultation-launches',
        json=_payload(),
        headers={
            'X-Integration-Key': 'test-integration-key',
            'X-Request-Id': request_id,
        },
    )
    assert first.status_code == 200

    session = TestSessionLocal()
    original_query = session.query
    force_initial_miss = True

    class ForcedMissQuery:
        def __init__(self, query):
            self.query = query

        def filter_by(self, **kwargs):
            self.query = self.query.filter_by(**kwargs)
            return self

        def with_for_update(self, *args, **kwargs):
            self.query = self.query.with_for_update(*args, **kwargs)
            return self

        def first(self):
            return None

    def racing_query(*entities, **kwargs):
        nonlocal force_initial_miss
        query = original_query(*entities, **kwargs)
        if force_initial_miss and entities == (AgentTeamsLaunch,):
            force_initial_miss = False
            return ForcedMissQuery(query)
        return query

    monkeypatch.setattr(session, 'query', racing_query)
    conflicting_payload = _payload()
    conflicting_payload['source_patient_id'] = 'another-patient'
    conflicting_payload['message'] = '另一位患者的病历。'

    try:
        with pytest.raises(AgentTeamsLaunchError) as exc_info:
            launch_agentteams_consultation(
                session,
                conflicting_payload,
                request_id=request_id,
                integration_key='test-integration-key',
            )

        assert exc_info.value.status_code == 409
        assert exc_info.value.error_code == 'idempotency_conflict'
        assert session.query(AgentTeamsLaunch).count() == 1
        assert session.query(Conversation).count() == 1
        assert session.query(AgentTeamsEmbedToken).count() == 1
    finally:
        session.close()


def test_embed_session_reads_single_conversation_without_jwt(client, monkeypatch):
    monkeypatch.setattr('api.agentteams_integration_api.schedule_agentteams_launch', lambda launch_id: None)
    session = TestSessionLocal()
    try:
        _prepare_service_account(session)
    finally:
        session.close()

    response = client.post(
        '/api/integrations/agentteams/consultation-launches',
        json=_payload(),
        headers={
            'X-Integration-Key': 'test-integration-key',
            'X-Request-Id': 'req-embed',
        },
    )
    launch_data = response.json()
    token = launch_data['embed_token']

    session = TestSessionLocal()
    try:
        initial_question = session.query(Message).filter_by(
            conversation_id=launch_data['agentteams_conversation_id'],
            message_type='normal',
            role='user',
        ).one()
        # 模拟一次修复前的启动，其原始问题未显式绑定到 LeaderSession。
        initial_question.leader_session_id = None
        unrelated_session = LeaderSession(
            conversation_id=launch_data['agentteams_conversation_id'],
            user_message='另一轮不应暴露的需求',
            state='completed',
            locale='zh-CN',
        )
        session.add(unrelated_session)
        session.flush()
        session.add(Message.create_leader_message(
            conversation_id=launch_data['agentteams_conversation_id'],
            leader_session_id=launch_data['agentteams_session_id'],
            message_type='assessment',
            content={'text': 'Persisted English assessment'},
            content_locale='en-US',
            sequence_number=2,
        ))
        session.add(Message.create_leader_message(
            conversation_id=launch_data['agentteams_conversation_id'],
            leader_session_id=unrelated_session.id,
            message_type='assessment',
            content={'text': '另一轮私有消息'},
            content_locale='zh-CN',
            sequence_number=1,
        ))
        session.add(Message.create_normal_message(
            conversation_id=launch_data['agentteams_conversation_id'],
            role='user',
            content='另一轮未绑定但也不应暴露的问题',
            is_review_mode=True,
            content_locale='zh-CN',
        ))
        session.commit()
    finally:
        session.close()

    embed_response = client.get(f'/api/integrations/agentteams/embed-sessions/{token}')

    assert embed_response.status_code == 200
    data = embed_response.json()
    assert data['conversation']['title'] == '虚拟会诊'
    assert data['locale'] == 'zh-CN'
    assert 'share_token' not in data['conversation']
    assert len(data['sessions']) == 1
    assert data['sessions'][0]['id'] == response.json()['agentteams_session_id']
    assert all(message['content'] != {'text': '另一轮私有消息'} for message in data['messages'])
    assert all(
        message['content'] != {'text': '另一轮未绑定但也不应暴露的问题'}
        for message in data['messages']
    )
    initial_question = next(message for message in data['messages'] if message['type'] == 'user')
    assert initial_question['content']['text'] == _payload()['message']
    assessment = next(message for message in data['messages'] if message['type'] == 'assessment')
    assert assessment['content_locale'] == 'en-US'
    assert data['version']
    assert embed_response.headers['cache-control'] == 'no-store'
    assert embed_response.headers['referrer-policy'] == 'no-referrer'
    assert embed_response.headers['content-security-policy'].startswith('frame-ancestors ')

    status_response = client.get(
        f'/api/integrations/agentteams/embed-sessions/{token}/status'
    )
    assert status_response.status_code == 200
    status_data = status_response.json()
    assert status_data == {
        'conversation_id': data['conversation']['id'],
        'status': data['sessions'][0]['state'],
        'terminal': False,
        'version': data['version'],
        'decision_run': data['sessions'][0]['decision_run'],
        'run_id': data['sessions'][0]['decision_run']['run_id'],
    }
    assert 'sessions' not in status_data
    assert status_response.headers['cache-control'] == 'no-store'


def test_embed_status_version_tracks_decision_stage_changes(client, monkeypatch):
    monkeypatch.setattr('api.agentteams_integration_api.schedule_agentteams_launch', lambda launch_id: None)
    session = TestSessionLocal()
    try:
        _prepare_service_account(session)
    finally:
        session.close()

    response = client.post(
        '/api/integrations/agentteams/consultation-launches',
        json=_payload(),
        headers={'X-Integration-Key': 'test-integration-key', 'X-Request-Id': 'req-stage-version'},
    )
    token = response.json()['embed_token']
    session = TestSessionLocal()
    try:
        run = session.query(DecisionRun).one()
        run.current_stage = 'execution'
        run.updated_at = utcnow_naive()
        session.commit()
    finally:
        session.close()

    status = client.get(f'/api/integrations/agentteams/embed-sessions/{token}/status').json()
    assert status['status'] == 'monitoring'
    assert ':execution:' in status['version']

    session = TestSessionLocal()
    try:
        session.add(ToolCallLog(
            conversation_id=status['conversation_id'],
            leader_session_id=response.json()['agentteams_session_id'],
            agent_id='oncology',
            tool_name='web_search',
            status='success',
            execution_time=0.5,
        ))
        session.commit()
    finally:
        session.close()
    refreshed = client.get(f'/api/integrations/agentteams/embed-sessions/{token}/status').json()
    assert refreshed['version'] != status['version']


def test_embed_session_rejects_expired_token(client, monkeypatch):
    monkeypatch.setattr('api.agentteams_integration_api.schedule_agentteams_launch', lambda launch_id: None)
    session = TestSessionLocal()
    try:
        _prepare_service_account(session)
    finally:
        session.close()

    response = client.post(
        '/api/integrations/agentteams/consultation-launches',
        json=_payload(),
        headers={
            'X-Integration-Key': 'test-integration-key',
            'X-Request-Id': 'req-expired-token',
        },
    )
    token = response.json()['embed_token']

    session = TestSessionLocal()
    try:
        embed_record = session.query(AgentTeamsEmbedToken).one()
        embed_record.expires_at = utcnow_naive() - timedelta(seconds=1)
        session.commit()
    finally:
        session.close()

    embed_response = client.get(f'/api/integrations/agentteams/embed-sessions/{token}')

    assert embed_response.status_code == 401
    assert embed_response.json()['error'] == 'invalid_embed_token'


def test_renew_embed_session_issues_new_token_without_new_conversation_or_usage(client, monkeypatch):
    monkeypatch.setattr('api.agentteams_integration_api.schedule_agentteams_launch', lambda launch_id: None)
    session = TestSessionLocal()
    try:
        _prepare_service_account(session)
    finally:
        session.close()

    launch_response = client.post(
        '/api/integrations/agentteams/consultation-launches',
        json=_payload(),
        headers={
            'X-Integration-Key': 'test-integration-key',
            'X-Request-Id': 'req-renew-token',
        },
    )
    assert launch_response.status_code == 200
    launch_data = launch_response.json()

    renew_response = client.post(
        '/api/integrations/agentteams/embed-sessions/renew',
        json={
            'source_conversation_id': '789',
            'request_id': 'req-renew-token',
            'agentteams_conversation_id': launch_data['agentteams_conversation_id'],
            'agentteams_session_id': launch_data['agentteams_session_id'],
        },
        headers={'X-Integration-Key': 'test-integration-key'},
    )

    assert renew_response.status_code == 200
    renew_data = renew_response.json()
    assert renew_data['agentteams_conversation_id'] == launch_data['agentteams_conversation_id']
    assert renew_data['agentteams_session_id'] == launch_data['agentteams_session_id']
    assert renew_data['embed_token'] != launch_data['embed_token']
    assert renew_data['embed_path'].startswith('/embed/conversation/')

    old_token_response = client.get(
        f"/api/integrations/agentteams/embed-sessions/{launch_data['embed_token']}"
    )
    assert old_token_response.status_code == 200

    session = TestSessionLocal()
    try:
        assert session.query(Conversation).count() == 1
        assert session.query(DecisionRun).count() == 1
        assert session.query(AgentTeamsEmbedToken).count() == 2
        assert session.query(AgentTeamsEmbedToken).filter_by(revoked_at=None).count() == 2
    finally:
        session.close()


def test_renew_embed_session_uses_request_id_when_source_conversation_is_duplicated(client, monkeypatch):
    monkeypatch.setattr('api.agentteams_integration_api.schedule_agentteams_launch', lambda launch_id: None)
    session = TestSessionLocal()
    try:
        _prepare_service_account(session)
    finally:
        session.close()

    first = client.post(
        '/api/integrations/agentteams/consultation-launches',
        json=_payload(),
        headers={
            'X-Integration-Key': 'test-integration-key',
            'X-Request-Id': 'req-duplicate-source-first',
        },
    )
    second = client.post(
        '/api/integrations/agentteams/consultation-launches',
        json=_payload(),
        headers={
            'X-Integration-Key': 'test-integration-key',
            'X-Request-Id': 'req-duplicate-source-second',
        },
    )
    assert first.status_code == 200
    assert second.status_code == 200

    second_data = second.json()
    renewed = client.post(
        '/api/integrations/agentteams/embed-sessions/renew',
        json={
            'source_conversation_id': 'a-new-local-conversation-id',
            'request_id': 'req-duplicate-source-second',
            'agentteams_conversation_id': second_data['agentteams_conversation_id'],
            'agentteams_session_id': second_data['agentteams_session_id'],
        },
        headers={'X-Integration-Key': 'test-integration-key'},
    )

    assert renewed.status_code == 200
    assert renewed.json()['agentteams_conversation_id'] == second_data['agentteams_conversation_id']
    assert renewed.json()['agentteams_session_id'] == second_data['agentteams_session_id']

    ambiguous = client.post(
        '/api/integrations/agentteams/embed-sessions/renew',
        json={'source_conversation_id': '789'},
        headers={'X-Integration-Key': 'test-integration-key'},
    )
    assert ambiguous.status_code == 409
    assert ambiguous.json()['detail']['error'] == 'agentteams_launch_ambiguous'


def test_launch_preparation_failure_rolls_back_all_side_effects(client, monkeypatch):
    session = TestSessionLocal()
    try:
        service_user = _prepare_service_account(session)
        service_user_id = service_user.id
    finally:
        session.close()

    def fail_session_creation(*args, **kwargs):
        raise RuntimeError('injected leader session failure')

    monkeypatch.setattr(
        'services.agentteams_integration_launch.create_leader_session',
        fail_session_creation,
    )

    with pytest.raises(RuntimeError, match='injected leader session failure'):
        client.post(
            '/api/integrations/agentteams/consultation-launches',
            json=_payload(),
            headers={
                'X-Integration-Key': 'test-integration-key',
                'X-Request-Id': 'req-atomic-failure',
            },
        )

    session = TestSessionLocal()
    try:
        assert session.query(AgentTeamsLaunch).count() == 0
        assert session.query(Conversation).count() == 0
        assert session.query(LeaderSession).count() == 0
        assert session.query(DecisionRun).count() == 0
        assert session.query(AgentTeamsEmbedToken).count() == 0
    finally:
        session.close()


def test_launch_rebuilds_an_empty_legacy_idempotency_record(client, monkeypatch):
    monkeypatch.setattr(
        'api.agentteams_integration_api.schedule_agentteams_launch',
        lambda launch_id: None,
    )
    session = TestSessionLocal()
    try:
        _prepare_service_account(session)
        session.add(AgentTeamsLaunch(
            source='agentteams',
            request_id='req-legacy-empty',
            source_conversation_id='789',
            status='created',
        ))
        session.commit()
    finally:
        session.close()

    response = client.post(
        '/api/integrations/agentteams/consultation-launches',
        json=_payload(),
        headers={
            'X-Integration-Key': 'test-integration-key',
            'X-Request-Id': 'req-legacy-empty',
        },
    )

    assert response.status_code == 200
    session = TestSessionLocal()
    try:
        launches = session.query(AgentTeamsLaunch).filter_by(request_id='req-legacy-empty').all()
        assert len(launches) == 1
        assert launches[0].agentteams_conversation_id is not None
        assert launches[0].agentteams_leader_session_id is not None
    finally:
        session.close()


def test_background_worker_claim_prevents_duplicate_execution(db_session, monkeypatch):
    _prepare_service_account(db_session)
    from services.agentteams_integration_launch import launch_agentteams_consultation, run_agentteams_leader_workflow

    launch_agentteams_consultation(
        db_session,
        _payload(),
        request_id='req-worker-claim',
        integration_key='test-integration-key',
    )
    launch = db_session.query(AgentTeamsLaunch).filter_by(request_id='req-worker-claim').one()
    executions = []

    async def successful_workflow(*args, **kwargs):
        executions.append(kwargs['existing_session_id'])
        yield {'type': 'complete'}

    monkeypatch.setattr(
        'services.agentteams_integration_launch.async_run_leader_workflow',
        successful_workflow,
    )

    run_agentteams_leader_workflow(launch.id, session_factory=TestSessionLocal)
    run_agentteams_leader_workflow(launch.id, session_factory=TestSessionLocal)

    assert executions == [launch.agentteams_leader_session_id]
    db_session.expire_all()
    persisted = db_session.get(AgentTeamsLaunch, launch.id)
    assert persisted.attempt_count == 1
    assert persisted.lease_owner is None
    assert persisted.lease_expires_at is None


def test_background_worker_persists_realtime_agent_subtasks(db_session, monkeypatch):
    _prepare_service_account(db_session)
    from services.agentteams_integration_launch import launch_agentteams_consultation, run_agentteams_leader_workflow

    result = launch_agentteams_consultation(
        db_session,
        _payload(),
        request_id='req-worker-progress',
        integration_key='test-integration-key',
    )
    launch = db_session.query(AgentTeamsLaunch).filter_by(request_id='req-worker-progress').one()

    async def workflow_with_progress(*args, **kwargs):
        yield {
            'type': 'task_decomposition',
            'agent_id': 'medical-oncologist',
            'agent_name': '肿瘤内科专家',
            'subtasks': [
                {'id': 'subtask-1', 'goal': '整理病史', 'status': 'pending', 'tools': []},
                {'id': 'subtask-2', 'goal': '核对指南', 'status': 'pending', 'tools': ['web_search']},
            ],
        }
        yield {
            'type': 'subtask_started',
            'agent_id': 'medical-oncologist',
            'agent_name': '肿瘤内科专家',
            'subtask_id': 'subtask-1',
            'goal': '整理病史',
            'tools': [],
        }
        yield {
            'type': 'subtask_completed',
            'agent_id': 'medical-oncologist',
            'agent_name': '肿瘤内科专家',
            'subtask_id': 'subtask-1',
            'goal': '整理病史',
            'status': 'completed',
        }
        yield {
            'type': 'subtask_started',
            'agent_id': 'medical-oncologist',
            'agent_name': '肿瘤内科专家',
            'subtask_id': 'subtask-2',
            'goal': '核对指南',
            'tools': ['web_search'],
        }

    monkeypatch.setattr(
        'services.agentteams_integration_launch.async_run_leader_workflow',
        workflow_with_progress,
    )

    run_agentteams_leader_workflow(launch.id, session_factory=TestSessionLocal)

    db_session.expire_all()
    snapshot = get_agentteams_embed_session(db_session, result['embed_token'])
    assert len(snapshot['agent_progress']) == 1
    progress = snapshot['agent_progress'][0]
    assert progress['agent_id'] == 'medical-oncologist'
    assert progress['status'] == 'running'
    assert progress['currentSubtaskId'] == 'subtask-2'
    assert progress['decomposition']['completedCount'] == 1
    assert progress['decomposition']['totalCount'] == 2
    assert [task['status'] for task in progress['decomposition']['subtasks']] == [
        'completed', 'running',
    ]
    assert ':4:' in snapshot['version']


def test_expired_running_launch_is_recovered_and_reclaimed(db_session, monkeypatch):
    _prepare_service_account(db_session)
    from services.agentteams_integration_launch import launch_agentteams_consultation, run_agentteams_leader_workflow

    launch_agentteams_consultation(
        db_session,
        _payload(),
        request_id='req-worker-recovery',
        integration_key='test-integration-key',
    )
    launch = db_session.query(AgentTeamsLaunch).filter_by(request_id='req-worker-recovery').one()
    session_id = launch.agentteams_leader_session_id
    launch.status = 'running'
    launch.lease_owner = 'dead-worker'
    launch.lease_expires_at = utcnow_naive() - timedelta(seconds=1)
    launch.attempt_count = 1
    db_session.commit()
    executions = []

    async def successful_workflow(*args, **kwargs):
        executions.append(kwargs['existing_session_id'])
        yield {'type': 'complete'}

    monkeypatch.setattr(
        'services.agentteams_integration_launch.async_run_leader_workflow',
        successful_workflow,
    )

    assert find_recoverable_agentteams_launch_ids(TestSessionLocal) == [launch.id]
    run_agentteams_leader_workflow(launch.id, session_factory=TestSessionLocal)

    db_session.expire_all()
    recovered = db_session.get(AgentTeamsLaunch, launch.id)
    assert executions == [session_id]
    assert recovered.attempt_count == 2
    assert recovered.lease_owner is None
    assert recovered.lease_expires_at is None


def test_active_lease_is_not_recoverable_and_heartbeat_requires_owner(db_session):
    _prepare_service_account(db_session)
    from services.agentteams_integration_launch import launch_agentteams_consultation

    launch_agentteams_consultation(
        db_session,
        _payload(),
        request_id='req-active-lease',
        integration_key='test-integration-key',
    )
    launch = db_session.query(AgentTeamsLaunch).filter_by(request_id='req-active-lease').one()
    launch.status = 'running'
    launch.lease_owner = 'live-worker'
    launch.lease_expires_at = utcnow_naive() + timedelta(minutes=5)
    db_session.commit()

    assert launch.id not in find_recoverable_agentteams_launch_ids(TestSessionLocal)
    assert renew_agentteams_launch_lease(launch.id, 'wrong-worker', TestSessionLocal) is False
    assert renew_agentteams_launch_lease(launch.id, 'live-worker', TestSessionLocal) is True


@pytest.mark.asyncio
async def test_answer_continuation_stops_immediately_after_lease_loss(monkeypatch):
    source_closed = asyncio.Event()

    async def blocked_events():
        try:
            await asyncio.Event().wait()
            yield {'type': 'done'}
        finally:
            source_closed.set()

    async def lost_lease(*args, **kwargs):
        return False

    monkeypatch.setattr(
        'services.agentteams_integration_launch._maintain_agentteams_launch_lease',
        lost_lease,
    )
    wrapped = run_claimed_agentteams_workflow_events(
        999999,
        'lost-owner',
        blocked_events(),
        TestSessionLocal,
    )

    with pytest.raises(RuntimeError, match='lost its launch lease'):
        await asyncio.wait_for(anext(wrapped), timeout=1)

    assert source_closed.is_set()


@pytest.mark.asyncio
async def test_answer_continuation_keeps_nonterminal_session_recoverable(db_session):
    from services.agentteams_integration_launch import launch_agentteams_consultation

    _prepare_service_account(db_session)
    launch_agentteams_consultation(
        db_session,
        _payload(),
        request_id='req-answer-setup-failure',
        integration_key='test-integration-key',
    )
    launch = db_session.query(AgentTeamsLaunch).filter_by(
        request_id='req-answer-setup-failure',
    ).one()
    leader_session = db_session.get(LeaderSession, launch.agentteams_leader_session_id)
    leader_session.state = 'assessing'
    launch.status = 'running'
    launch.lease_owner = 'answer-owner'
    launch.lease_expires_at = utcnow_naive() + timedelta(minutes=5)
    db_session.commit()

    async def setup_failure_stream():
        yield {'type': 'error', 'message': 'service initialization failed'}

    events = [
        event
        async for event in run_claimed_agentteams_workflow_events(
            launch.id,
            'answer-owner',
            setup_failure_stream(),
            TestSessionLocal,
        )
    ]

    assert events == [{'type': 'error', 'message': 'service initialization failed'}]
    db_session.expire_all()
    launch = db_session.get(AgentTeamsLaunch, launch.id)
    assert launch.status == 'running'
    assert launch.lease_owner is None
    assert launch.lease_expires_at <= utcnow_naive()
    assert launch.id in find_recoverable_agentteams_launch_ids(TestSessionLocal)


def test_renew_embed_session_rejects_mismatched_conversation(client, monkeypatch):
    monkeypatch.setattr('api.agentteams_integration_api.schedule_agentteams_launch', lambda launch_id: None)
    session = TestSessionLocal()
    try:
        _prepare_service_account(session)
    finally:
        session.close()

    launch_response = client.post(
        '/api/integrations/agentteams/consultation-launches',
        json=_payload(),
        headers={
            'X-Integration-Key': 'test-integration-key',
            'X-Request-Id': 'req-renew-mismatch',
        },
    )
    assert launch_response.status_code == 200

    renew_response = client.post(
        '/api/integrations/agentteams/embed-sessions/renew',
        json={
            'source_conversation_id': '789',
            'agentteams_conversation_id': 999999,
        },
        headers={'X-Integration-Key': 'test-integration-key'},
    )

    assert renew_response.status_code == 404
    assert renew_response.json()['detail']['error'] == 'agentteams_launch_not_found'


def test_background_workflow_success_converges_launch_state(db_session, monkeypatch):
    _prepare_service_account(db_session)
    from services.agentteams_integration_launch import launch_agentteams_consultation, run_agentteams_leader_workflow

    result = launch_agentteams_consultation(
        db_session,
        _payload(),
        request_id='req-background-success',
        integration_key='test-integration-key',
    )
    launch = db_session.query(AgentTeamsLaunch).filter_by(request_id='req-background-success').first()

    async def successful_workflow(*args, **kwargs):
        assert kwargs['existing_session_id'] == result['agentteams_session_id']
        session = TestSessionLocal()
        try:
            leader_session = session.get(LeaderSession, kwargs['existing_session_id'])
            leader_session.state = 'completed'
            session.commit()
        finally:
            session.close()
        yield {'type': 'complete'}

    monkeypatch.setattr(
        'services.agentteams_integration_launch.async_run_leader_workflow',
        successful_workflow,
    )

    run_agentteams_leader_workflow(launch.id, session_factory=TestSessionLocal)
    db_session.expire_all()

    leader_session = db_session.query(LeaderSession).filter_by(id=result['agentteams_session_id']).first()
    launch = db_session.query(AgentTeamsLaunch).filter_by(id=launch.id).first()

    assert leader_session.state == 'completed'
    assert launch.status == 'completed'


def test_background_workflow_failure_marks_launch_failed(db_session, monkeypatch):
    _prepare_service_account(db_session)
    from services.agentteams_integration_launch import launch_agentteams_consultation, run_agentteams_leader_workflow

    result = launch_agentteams_consultation(
        db_session,
        _payload(),
        request_id='req-background-failure',
        integration_key='test-integration-key',
    )
    launch = db_session.query(AgentTeamsLaunch).filter_by(request_id='req-background-failure').first()

    async def failing_workflow(*args, **kwargs):
        raise RuntimeError('workflow failed')
        yield  # pragma: no cover

    monkeypatch.setattr(
        'services.agentteams_integration_launch.async_run_leader_workflow',
        failing_workflow,
    )

    run_agentteams_leader_workflow(launch.id, session_factory=TestSessionLocal)
    db_session.expire_all()

    leader_session = db_session.query(LeaderSession).filter_by(id=result['agentteams_session_id']).first()
    launch = db_session.query(AgentTeamsLaunch).filter_by(id=launch.id).first()

    assert leader_session.state == 'failed'
    assert launch.status == 'failed'
    assert launch.error_code == 'agentteams_launch_failed'
