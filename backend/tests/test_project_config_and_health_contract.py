"""Regression tests for browser-facing health and project config contracts."""

from types import SimpleNamespace

from fastapi.testclient import TestClient

from api.project_config_api import _project_model_to_dict
from app import app


def test_health_aliases_return_the_same_payload_shape():
    client = TestClient(app)

    backend_health = client.get('/health')
    browser_health = client.get('/api/health')

    assert backend_health.status_code == 200
    assert browser_health.status_code == 200
    assert backend_health.json()['status'] == browser_health.json()['status'] == 'ok'
    assert backend_health.json()['version'] == browser_health.json()['version']


def test_project_config_hides_gateway_and_diagnostic_fields_for_regular_users():
    model = SimpleNamespace(
        to_dict=lambda include_sensitive: {
            'model_id': 'example-model',
            'base_url': 'https://internal-gateway.example',
            'api_key': 'secret-key',
            'api_key_masked': 'sec****key',
            'last_test_error': 'upstream detail',
        },
    )

    regular_user = _project_model_to_dict(model, can_edit=False)
    admin_user = _project_model_to_dict(model, can_edit=True)

    assert regular_user == {'model_id': 'example-model'}
    assert admin_user['base_url'] == 'https://internal-gateway.example'
    assert admin_user['last_test_error'] == 'upstream detail'
