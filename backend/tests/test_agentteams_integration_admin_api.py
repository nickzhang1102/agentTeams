"""Agent Teams 集成管理 API 测试。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import SystemConfig
from services.agentteams_integration_launch import AGENTTEAMS_INTEGRATION_KEY
from tests.conftest import TestSessionLocal


def _payload():
    return {
        'source': 'agentteams',
        'source_user_id': 'agentteams:123',
        'source_patient_id': '456',
        'source_conversation_id': 789,
        'title': '虚拟会诊',
        'message': '请基于病历生成多学科会诊意见。',
        'metadata': {'created_from': 'agentteams'},
    }


def test_admin_generates_integration_key_and_launch_accepts_plaintext(client, admin_auth_header, monkeypatch):
    monkeypatch.setattr('api.agentteams_integration_api.schedule_agentteams_launch', lambda launch_id: None)

    generate_response = client.post(
        '/api/admin/agentteams-integration/generate-key',
        headers=admin_auth_header,
    )

    assert generate_response.status_code == 200
    generated_key = generate_response.json()['generated_integration_key']
    assert generated_key.startswith('op_')
    assert generate_response.json()['has_integration_key'] is True
    assert generated_key not in generate_response.json()['integration_key_masked']

    session = TestSessionLocal()
    try:
        stored = session.query(SystemConfig).filter_by(key=AGENTTEAMS_INTEGRATION_KEY).one()
        assert stored.value.startswith('sha256:')
        assert generated_key not in stored.value
    finally:
        session.close()

    launch_response = client.post(
        '/api/integrations/agentteams/consultation-launches',
        json=_payload(),
        headers={
            'X-Integration-Key': generated_key,
            'X-Request-Id': 'req-generated-admin-key',
        },
    )

    assert launch_response.status_code == 200
    assert launch_response.json()['embed_path'].startswith('/embed/conversation/')


def test_admin_update_keeps_existing_key_when_blank(client, admin_auth_header):
    first = client.post('/api/admin/agentteams-integration/generate-key', headers=admin_auth_header)
    assert first.status_code == 200

    session = TestSessionLocal()
    try:
        original_value = session.query(SystemConfig).filter_by(key=AGENTTEAMS_INTEGRATION_KEY).one().value
    finally:
        session.close()

    update_response = client.put(
        '/api/admin/agentteams-integration',
        headers=admin_auth_header,
        json={
            'enabled': True,
            'integration_key': '',
            'embed_token_ttl_seconds': 900,
            'service_account_username': 'agentteams-service',
        },
    )

    assert update_response.status_code == 200

    session = TestSessionLocal()
    try:
        updated_value = session.query(SystemConfig).filter_by(key=AGENTTEAMS_INTEGRATION_KEY).one().value
        assert updated_value == original_value
    finally:
        session.close()


def test_basic_connection_update_does_not_reset_advanced_defaults(client, admin_auth_header):
    generated = client.post('/api/admin/agentteams-integration/generate-key', headers=admin_auth_header)
    assert generated.status_code == 200

    configured = client.put(
        '/api/admin/agentteams-integration',
        headers=admin_auth_header,
        json={
            'enabled': True,
            'embed_token_ttl_seconds': 1800,
            'service_account_username': 'custom-agentteams-service',
        },
    )
    assert configured.status_code == 200

    basic_save = client.put(
        '/api/admin/agentteams-integration',
        headers=admin_auth_header,
        json={'enabled': False, 'integration_key': ''},
    )
    assert basic_save.status_code == 200
    data = basic_save.json()
    assert data['enabled'] is False
    assert data['embed_token_ttl_seconds'] == 1800
    assert data['service_account_username'] == 'custom-agentteams-service'
