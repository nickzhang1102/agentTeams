"""管理员生命周期与凭据轮转契约测试。"""

import os
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import (
    Conversation,
    IntegrationAccessOperation,
    IntegrationClient,
    AgentTeamsEmbedToken,
    AgentTeamsLaunch,
    SecurityLog,
    User,
)
from tests.conftest import TestSessionLocal
from utils.time_utils import utcnow_naive


def _service_account():
    session = TestSessionLocal()
    try:
        user = User(
            username='integration-admin-test-service',
            password_hash='unused',
            account_type='service',
            login_disabled=True,
            is_admin=False,
            role='editor',
        )
        session.add(user)
        session.commit()
        return user.id
    finally:
        session.close()

def _create_payload(service_account_id, *, adapter_key='contract-fixture'):
    return {
        'client_key': 'fixture-client',
        'adapter_key': adapter_key,
        'display_name': 'Fixture Client',
        'service_account_id': service_account_id,
        'capabilities': {'launch': True, 'status_query': True},
        'reason': 'contract test',
    }


def test_admin_can_create_list_disable_and_rotate_integration_client(client, admin_auth_header):
    service_account_id = _service_account()
    created = client.post(
        '/api/admin/integration-clients',
        json=_create_payload(service_account_id, adapter_key='agentteams'),
        headers=admin_auth_header,
    )
    assert created.status_code == 201
    body = created.json()
    plaintext = body['generated_integration_key']
    assert plaintext.startswith('ik_')
    assert 'credential_hash' not in body['client']
    assert plaintext not in str(body['client'])

    listed = client.get('/api/admin/integration-clients', headers=admin_auth_header)
    assert listed.status_code == 200
    assert listed.json()['items'][0]['client_key'] == 'fixture-client'
    assert 'credential_hash' not in listed.text

    disabled = client.put(
        '/api/admin/integration-clients/fixture-client/enabled',
        json={'enabled': False, 'reason': 'maintenance'},
        headers=admin_auth_header,
    )
    assert disabled.status_code == 200
    assert disabled.json()['enabled'] is False

    rotated = client.post(
        '/api/admin/integration-clients/fixture-client/rotate-key',
        json={'rotation_window_seconds': 120, 'reason': 'scheduled rotation'},
        headers=admin_auth_header,
    )
    assert rotated.status_code == 200
    assert rotated.json()['generated_integration_key'] != plaintext
    assert rotated.json()['client']['has_previous_credential'] is True

    session = TestSessionLocal()
    try:
        row = session.query(IntegrationClient).filter_by(client_key='fixture-client').one()
        assert row.credential_hash.startswith('sha256:')
        assert row.previous_credential_hash.startswith('sha256:')
        assert plaintext not in row.credential_hash
        logs = session.query(SecurityLog).filter_by(resource_id=row.id).all()
        assert {log.action for log in logs} == {
            'integration_client_create',
            'integration_client_disable',
            'integration_client_rotate_key',
        }
        assert all(plaintext not in str(log.details) for log in logs)
    finally:
        session.close()

    audit = client.get(
        '/api/admin/integration-clients/fixture-client/audit?limit=2',
        headers=admin_auth_header,
    )
    assert audit.status_code == 200
    assert len(audit.json()['items']) == 2
    assert audit.json()['items'][0]['resource_type'] == 'integration_client'
    assert plaintext not in audit.text


def test_rotation_window_authenticates_previous_key_then_expires(client, admin_auth_header):
    service_account_id = _service_account()
    created = client.post(
        '/api/admin/integration-clients',
        json=_create_payload(service_account_id),
        headers=admin_auth_header,
    )
    old_key = created.json()['generated_integration_key']
    rotated = client.post(
        '/api/admin/integration-clients/fixture-client/rotate-key',
        json={'rotation_window_seconds': 60},
        headers=admin_auth_header,
    )
    new_key = rotated.json()['generated_integration_key']

    from services.integration_client_service import IntegrationClientService, IntegrationClientError
    session = TestSessionLocal()
    try:
        row = session.query(IntegrationClient).filter_by(client_key='fixture-client').one()
        assert row.previous_credential_expires_at > utcnow_naive()
        assert IntegrationClientService.authenticate(session, 'fixture-client', old_key).client_key == 'fixture-client'
        assert IntegrationClientService.authenticate(session, 'fixture-client', new_key).client_key == 'fixture-client'
        row.previous_credential_expires_at = utcnow_naive() - timedelta(seconds=1)
        session.commit()
    finally:
        session.close()

    # 一旦重叠窗口过去，旧密钥就会被拒绝。在同一边界上，新
    # 密钥仍能通过身份验证。
    session = TestSessionLocal()
    try:
        try:
            IntegrationClientService.authenticate(session, 'fixture-client', old_key)
        except IntegrationClientError as error:
            assert error.status_code == 401
        else:
            raise AssertionError('expired prior key must be rejected')
        context = IntegrationClientService.authenticate(session, 'fixture-client', new_key)
        assert context.client_key == 'fixture-client'
    finally:
        session.close()


def test_disabled_client_rejects_even_a_valid_current_key(client, admin_auth_header):
    service_account_id = _service_account()
    created = client.post(
        '/api/admin/integration-clients',
        json=_create_payload(service_account_id),
        headers=admin_auth_header,
    )
    key = created.json()['generated_integration_key']
    disabled = client.put(
        '/api/admin/integration-clients/fixture-client/enabled',
        json={'enabled': False},
        headers=admin_auth_header,
    )
    assert disabled.status_code == 200

    from services.integration_client_service import IntegrationClientError, IntegrationClientService
    session = TestSessionLocal()
    try:
        try:
            IntegrationClientService.authenticate(session, 'fixture-client', key)
        except IntegrationClientError as error:
            assert error.status_code == 403
            assert error.error_code == 'integration_disabled'
        else:
            raise AssertionError('disabled client must be rejected')
    finally:
        session.close()


def test_disabling_client_blocks_existing_embed_access_until_reenabled(client, admin_auth_header):
    service_account_id = _service_account()
    created = client.post(
        '/api/admin/integration-clients',
        json=_create_payload(service_account_id, adapter_key='agentteams'),
        headers=admin_auth_header,
    )
    assert created.status_code == 201
    raw_token, conversation_id, _ = _seed_client_owned_embed_launch(
        'fixture-client', 'fixture-client:disabled-embed-request', service_account_id
    )

    before = client.get(
        f'/api/integrations/agentteams/embed-sessions/{raw_token}',
    )
    assert before.status_code == 200
    assert before.json()['conversation']['id'] == conversation_id

    disabled = client.put(
        '/api/admin/integration-clients/fixture-client/enabled',
        json={'enabled': False, 'reason': 'suspend existing embed access'},
        headers=admin_auth_header,
    )
    assert disabled.status_code == 200

    for path in (
        f'/api/integrations/agentteams/embed-sessions/{raw_token}',
        f'/api/integrations/agentteams/embed-sessions/{raw_token}/status',
    ):
        blocked = client.get(path)
        assert blocked.status_code == 403
        assert blocked.json()['detail']['error'] == 'integration_disabled'

    enabled = client.put(
        '/api/admin/integration-clients/fixture-client/enabled',
        json={'enabled': True, 'reason': 'restore embed access'},
        headers=admin_auth_header,
    )
    assert enabled.status_code == 200

    after = client.get(
        f'/api/integrations/agentteams/embed-sessions/{raw_token}',
    )
    assert after.status_code == 200
    assert after.json()['conversation']['id'] == conversation_id


def test_reenabling_client_requires_a_safe_service_account(client, admin_auth_header):
    service_account_id = _service_account()
    created = client.post(
        '/api/admin/integration-clients',
        json=_create_payload(service_account_id),
        headers=admin_auth_header,
    )
    assert created.status_code == 201
    session = TestSessionLocal()
    try:
        service_account = session.get(User, service_account_id)
        service_account.login_disabled = False
        session.commit()
    finally:
        session.close()

    response = client.put(
        '/api/admin/integration-clients/fixture-client/enabled',
        json={'enabled': False},
        headers=admin_auth_header,
    )
    assert response.status_code == 200
    response = client.put(
        '/api/admin/integration-clients/fixture-client/enabled',
        json={'enabled': True},
        headers=admin_auth_header,
    )
    assert response.status_code == 422
    assert response.json()['detail']['error'] == 'unsafe_service_account'


def test_data_inventory_is_client_scoped_and_does_not_return_phi(client, admin_auth_header):
    service_account_id = _service_account()
    created = client.post(
        '/api/admin/integration-clients',
        json=_create_payload(service_account_id),
        headers=admin_auth_header,
    )
    assert created.status_code == 201
    session = TestSessionLocal()
    try:
        session.add(IntegrationClient(
            client_key='other-client',
            adapter_key='agentteams',
            display_name='Other Client',
            credential_hash='sha256:' + ('a' * 64),
            service_account_id=service_account_id,
            enabled=True,
            capabilities_json={'launch': True},
        ))
        session.commit()
    finally:
        session.close()

    inventory = client.get(
        '/api/admin/integration-clients/fixture-client/data-inventory',
        headers=admin_auth_header,
    )
    assert inventory.status_code == 200
    body = inventory.json()
    assert body['client_key'] == 'fixture-client'
    assert body['categories']['launch_records']['count'] == 0
    assert body['categories']['embed_tokens']['count'] == 0
    assert body['destructive_actions']['remote_delete'] == 'not_implemented'
    assert body['destructive_actions']['retention_policy'] == 'not_implemented'
    assert body['ownership'] == {
        'type': 'integration_client',
        'client_key': 'fixture-client',
        'query_boundary': 'exact client_key match',
    }
    assert 'raw_content' not in inventory.text
    assert set(body['categories']) == {
        'launch_records', 'conversations', 'messages', 'leader_sessions',
        'embed_tokens', 'access_operations',
        'security_audit_records',
    }


def test_data_inventory_exposes_phi_safe_classification_and_governance_counts(
    client,
    admin_auth_header,
):
    service_account_id = _service_account()
    created = client.post(
        '/api/admin/integration-clients',
        json=_create_payload(service_account_id, adapter_key='agentteams'),
        headers=admin_auth_header,
    )
    assert created.status_code == 201
    _seed_client_owned_embed_launch(
        'fixture-client', 'fixture-client:inventory-request', service_account_id
    )

    inventory = client.get(
        '/api/admin/integration-clients/fixture-client/data-inventory',
        headers=admin_auth_header,
    )

    assert inventory.status_code == 200
    body = inventory.json()
    assert body['contains_phi_content'] is True
    assert body['categories']['launch_records']['count'] == 1
    assert body['categories']['launch_records']['source'] == 'agentteams'
    assert body['categories']['launch_records']['owner']['client_key'] == 'fixture-client'
    assert body['categories']['launch_records']['content_classification'] == 'external_reference'
    assert body['categories']['launch_records']['retention_basis'] == 'idempotency_and_reconciliation'
    assert body['categories']['conversations']['count'] == 1
    assert body['categories']['conversations']['contains_phi_content'] is True
    assert body['categories']['embed_tokens']['actions']['access_revoke'] == 'available'
    assert body['categories']['access_operations']['count'] == 0
    assert body['categories']['security_audit_records']['count'] >= 1
    assert all(
        category['actions']['local_delete'] == 'not_implemented'
        and category['actions']['remote_delete'] == 'not_implemented'
        for category in body['categories'].values()
    )
    assert 'revocation fixture' not in inventory.text
    assert 'external-revoke-conversation' not in inventory.text
    assert 'source_patient_id' not in inventory.text

def test_admin_rejects_unsafe_service_account(client, admin_auth_header):
    session = TestSessionLocal()
    try:
        unsafe = User(
            username='unsafe-integration-service',
            password_hash='unused',
            account_type='service',
            login_disabled=False,
            is_admin=False,
            role='editor',
        )
        session.add(unsafe)
        session.commit()
        unsafe_id = unsafe.id
    finally:
        session.close()

    response = client.post(
        '/api/admin/integration-clients',
        json=_create_payload(unsafe_id),
        headers=admin_auth_header,
    )
    assert response.status_code == 422
    assert response.json()['detail']['error'] == 'unsafe_service_account'


def _seed_client_owned_embed_launch(client_key: str, request_id: str, service_account_id: int):
    """仅创建行使访问撤销所需的本地记录。"""
    session = TestSessionLocal()
    try:
        conversation = Conversation(
            title='revocation fixture',
            user_id=service_account_id,
            status='analyzing',
            is_review_mode=True,
            category='medical',
            default_locale='zh-CN',
            share_token=Conversation.generate_share_token(),
        )
        session.add(conversation)
        session.flush()
        launch = AgentTeamsLaunch(
            source='agentteams',
            integration_client_key=client_key,
            request_id=request_id,
            source_conversation_id='external-revoke-conversation',
            agentteams_conversation_id=conversation.id,
            status='running',
        )
        session.add(launch)
        session.flush()
        raw_token = 'revocation-fixture-token'
        import hashlib
        token = AgentTeamsEmbedToken(
            token_hash=hashlib.sha256(raw_token.encode('utf-8')).hexdigest(),
            conversation_id=conversation.id,
            source='agentteams',
            integration_client_key=client_key,
            expires_at=utcnow_naive() + timedelta(hours=1),
        )
        session.add(token)
        session.commit()
        return raw_token, conversation.id, launch.id
    finally:
        session.close()


def test_admin_revoke_embed_access_is_client_scoped_idempotent_and_audited(
    client,
    admin_auth_header,
):
    service_account_id = _service_account()
    created = client.post(
        '/api/admin/integration-clients',
        json=_create_payload(service_account_id, adapter_key='agentteams'),
        headers=admin_auth_header,
    )
    assert created.status_code == 201
    raw_token, conversation_id, launch_id = _seed_client_owned_embed_launch(
        'fixture-client', 'fixture-client:fixture-revoke-request', service_account_id
    )

    before = client.get(
        f'/api/integrations/agentteams/embed-sessions/{raw_token}',
    )
    assert before.status_code == 200

    revoked = client.post(
        '/api/admin/integration-clients/fixture-client/embed-tokens/revoke',
        json={
            'request_id': 'fixture-revoke-request',
            'operation_id': 'op-fixture-revoke-1',
            'reason': 'user requested access revocation',
        },
        headers=admin_auth_header,
    )
    assert revoked.status_code == 200
    revoked_body = revoked.json()
    assert revoked_body['operation_id'] == 'op-fixture-revoke-1'
    assert revoked_body['action'] == 'integration_client_revoke_embed_access'
    assert revoked_body['status'] == 'completed'
    assert revoked_body['client_key'] == 'fixture-client'
    assert revoked_body['request_id'] == 'fixture-revoke-request'
    assert revoked_body['revoked_count'] == 1
    assert revoked_body['remote_action'] == 'not_implemented'

    again = client.post(
        '/api/admin/integration-clients/fixture-client/embed-tokens/revoke',
        json={
            'request_id': 'fixture-revoke-request',
            'operation_id': 'op-fixture-revoke-1',
            'reason': 'repeat reconciliation',
        },
        headers=admin_auth_header,
    )
    assert again.status_code == 200
    assert again.json() == revoked_body

    operation = client.get(
        '/api/admin/integration-clients/fixture-client/embed-tokens/revoke/op-fixture-revoke-1',
        headers=admin_auth_header,
    )
    assert operation.status_code == 200
    assert operation.json() == revoked_body

    listed = client.get(
        '/api/admin/integration-clients/fixture-client/embed-tokens/revoke?status=completed',
        headers=admin_auth_header,
    )
    assert listed.status_code == 200
    assert listed.json()['items'] == [revoked_body]

    pending = client.get(
        '/api/admin/integration-clients/fixture-client/embed-tokens/revoke?status=requested',
        headers=admin_auth_header,
    )
    assert pending.status_code == 200
    assert pending.json()['items'] == []

    session = TestSessionLocal()
    try:
        session.add(IntegrationAccessOperation(
            operation_id='op-other-client',
            client_key='other-client',
            action='integration_client_revoke_embed_access',
            request_id='other-request',
            status='completed',
            revoked_count=3,
        ))
        session.commit()
    finally:
        session.close()

    isolated = client.get(
        '/api/admin/integration-clients/fixture-client/embed-tokens/revoke',
        headers=admin_auth_header,
    )
    assert isolated.status_code == 200
    assert isolated.json()['items'] == [revoked_body]

    after = client.get(
        f'/api/integrations/agentteams/embed-sessions/{raw_token}',
    )
    assert after.status_code == 401

    session = TestSessionLocal()
    try:
        assert session.get(Conversation, conversation_id) is not None
        assert session.get(AgentTeamsLaunch, launch_id) is not None
        token = session.query(AgentTeamsEmbedToken).filter_by(
            conversation_id=conversation_id,
            integration_client_key='fixture-client',
        ).one()
        assert token.revoked_at is not None
        logs = session.query(SecurityLog).filter_by(
            action='integration_client_revoke_embed_access',
        ).all()
        assert len(logs) == 2
        assert all(raw_token not in str(log.details) for log in logs)
        assert all(log.details['client_key'] == 'fixture-client' for log in logs)
    finally:
        session.close()


def test_admin_revoke_rejects_cross_client_request_id_and_missing_reason(
    client,
    admin_auth_header,
):
    service_account_id = _service_account()
    created = client.post(
        '/api/admin/integration-clients',
        json=_create_payload(service_account_id, adapter_key='agentteams'),
        headers=admin_auth_header,
    )
    assert created.status_code == 201
    _seed_client_owned_embed_launch(
        'fixture-client', 'fixture-client:fixture-revoke-request', service_account_id
    )
    session = TestSessionLocal()
    try:
        session.add(IntegrationClient(
            client_key='other-client',
            adapter_key='agentteams',
            display_name='Other Client',
            credential_hash='sha256:' + ('b' * 64),
            service_account_id=service_account_id,
            enabled=True,
            capabilities_json={'launch': True},
        ))
        session.commit()
    finally:
        session.close()

    cross_client = client.post(
        '/api/admin/integration-clients/other-client/embed-tokens/revoke',
        json={'request_id': 'fixture-revoke-request', 'reason': 'cross-client probe'},
        headers=admin_auth_header,
    )
    assert cross_client.status_code == 404
    assert cross_client.json()['detail']['error'] == 'agentteams_launch_not_found'

    missing_reason = client.post(
        '/api/admin/integration-clients/fixture-client/embed-tokens/revoke',
        json={'request_id': 'fixture-revoke-request'},
        headers=admin_auth_header,
    )
    assert missing_reason.status_code == 422

    blank_reason = client.post(
        '/api/admin/integration-clients/fixture-client/embed-tokens/revoke',
        json={'request_id': 'fixture-revoke-request', 'reason': '   '},
        headers=admin_auth_header,
    )
    assert blank_reason.status_code == 422

    conflict = client.post(
        '/api/admin/integration-clients/fixture-client/embed-tokens/revoke',
        json={
            'request_id': 'different-request',
            'operation_id': 'op-fixture-revoke-1',
            'reason': 'operation collision',
        },
        headers=admin_auth_header,
    )
    assert conflict.status_code == 404


def test_admin_revoke_fails_closed_for_non_agentteams_adapter(client, admin_auth_header):
    service_account_id = _service_account()
    created = client.post(
        '/api/admin/integration-clients',
        json=_create_payload(service_account_id),
        headers=admin_auth_header,
    )
    assert created.status_code == 201
    session = TestSessionLocal()
    try:
        session.add(IntegrationClient(
            client_key='fixture-other-adapter',
            adapter_key='contract-fixture',
            display_name='Other Adapter',
            credential_hash='sha256:' + ('c' * 64),
            service_account_id=service_account_id,
            enabled=True,
            capabilities_json={'launch': True},
        ))
        session.commit()
    finally:
        session.close()

    response = client.post(
        '/api/admin/integration-clients/fixture-other-adapter/embed-tokens/revoke',
        json={'request_id': 'request', 'reason': 'unsupported adapter'},
        headers=admin_auth_header,
    )
    assert response.status_code == 501
    assert response.json()['detail']['error'] == 'integration_access_revoke_unavailable'

    listed = client.get(
        '/api/admin/integration-clients/fixture-other-adapter/embed-tokens/revoke',
        headers=admin_auth_header,
    )
    assert listed.status_code == 501
    assert listed.json()['detail']['error'] == 'integration_access_revoke_unavailable'


def test_admin_revoke_requires_admin_permission(client, auth_header):
    response = client.post(
        '/api/admin/integration-clients/fixture-client/embed-tokens/revoke',
        json={'request_id': 'request', 'reason': 'not allowed'},
        headers=auth_header,
    )
    assert response.status_code == 403
