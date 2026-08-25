"""Agent Teams 服务账户测试。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import SystemConfig, User
from services.agentteams_integration_account import (
    AGENTTEAMS_INTEGRATION_ENABLED,
    AGENTTEAMS_SERVICE_ACCOUNT_USERNAME,
    ensure_agentteams_service_account,
    get_agentteams_capacity,
    resolve_agentteams_service_account,
)
from seed_admin_data import seed_agentteams_service_account, seed_system_configs
from tests.conftest import TestSessionLocal, encrypt_password_for_test


def _add_config(db_session, key, value):
    db_session.add(SystemConfig(key=key, value=str(value), description=key))
    db_session.flush()


def test_ensure_agentteams_service_account_creates_non_admin_service_user(db_session):
    user = ensure_agentteams_service_account(db_session)
    db_session.commit()

    assert user.account_type == 'service'
    assert user.login_disabled is True
    assert user.is_admin is False
    assert user.role != 'admin'


def test_ensure_agentteams_service_account_is_idempotent(db_session):
    user = ensure_agentteams_service_account(db_session)
    first_id = user.id
    db_session.commit()

    same_user = ensure_agentteams_service_account(db_session)
    db_session.commit()

    assert same_user.id == first_id
    assert db_session.query(User).filter_by(username='agentteams-service').count() == 1


def test_ensure_agentteams_service_account_repairs_existing_user(db_session):
    user = User(username='agentteams-service', email=None, is_admin=True, role='admin')
    user.set_password('Service@123')
    db_session.add(user)
    db_session.commit()
    old_token_version = user.token_version

    ensured = ensure_agentteams_service_account(db_session)
    db_session.commit()

    assert ensured.id == user.id
    assert ensured.account_type == 'service'
    assert ensured.login_disabled is True
    assert ensured.is_admin is False
    assert ensured.role == 'viewer'
    assert ensured.token_version == old_token_version + 1


def test_seed_initializes_agentteams_configs_and_service_account(db_session):
    seed_system_configs(db_session)
    seed_agentteams_service_account(db_session)

    keys = {
        row.key: row.value
        for row in db_session.query(SystemConfig)
        .filter(SystemConfig.key.in_([
            AGENTTEAMS_INTEGRATION_ENABLED,
            AGENTTEAMS_SERVICE_ACCOUNT_USERNAME,
        ]))
        .all()
    }
    user = resolve_agentteams_service_account(db_session)

    assert keys[AGENTTEAMS_INTEGRATION_ENABLED] == 'true'
    assert keys[AGENTTEAMS_SERVICE_ACCOUNT_USERNAME] == 'agentteams-service'
    assert user is not None


def test_get_agentteams_capacity_reports_configured_state_without_balance(db_session):
    user = ensure_agentteams_service_account(db_session)
    db_session.commit()

    capacity = get_agentteams_capacity(db_session)
    assert capacity['configured'] is True
    assert capacity['enabled'] is True
    assert capacity['user_id'] == user.id
    assert capacity['username'] == 'agentteams-service'
    # 开源自部署无计费概念，容量不再暴露余额字段
    assert 'balance' not in capacity
    assert 'has_enough' not in capacity


def test_service_account_login_is_rejected_with_generic_401(client):
    session = TestSessionLocal()
    try:
        user = User(
            username='agentteams-service',
            email=None,
            account_type='service',
            login_disabled=True,
            role='viewer',
        )
        user.set_password('Service@123')
        session.add(user)
        session.commit()
    finally:
        session.close()

    encrypted_password = encrypt_password_for_test('Service@123')
    response = client.post('/api/auth/login', json={
        'username': 'agentteams-service',
        'password': encrypted_password,
    })

    assert response.status_code == 401
    assert 'access_token' not in response.text
    assert 'access_token' not in response.cookies


def test_admin_cannot_promote_service_account_to_admin(client, admin_auth_header):
    session = TestSessionLocal()
    try:
        user = User(
            username='agentteams-service',
            email=None,
            account_type='service',
            login_disabled=True,
            role='viewer',
        )
        user.set_password('Service@123')
        session.add(user)
        session.commit()
        service_user_id = user.id
    finally:
        session.close()

    response = client.put(
        f'/api/admin/users/{service_user_id}/role',
        json={'role': 'admin'},
        headers=admin_auth_header,
    )

    assert response.status_code == 400

    session = TestSessionLocal()
    try:
        user = session.get(User, service_user_id)
        assert user.is_admin is False
        assert user.role != 'admin'
    finally:
        session.close()


def test_admin_can_update_human_user_role(client, admin_auth_header):
    session = TestSessionLocal()
    try:
        user = User(username='normal-role-user', email='normal-role@example.com')
        user.set_password('Human@123')
        session.add(user)
        session.commit()
        human_user_id = user.id
    finally:
        session.close()

    response = client.put(
        f'/api/admin/users/{human_user_id}/role',
        json={'role': 'viewer'},
        headers=admin_auth_header,
    )

    assert response.status_code == 200
    assert response.json()['user']['role'] == 'viewer'
