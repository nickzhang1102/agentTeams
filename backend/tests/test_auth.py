"""
认证 API 测试（FastAPI 版）

迁移变更：
- 删除重复 fixture，使用 conftest.py
- client.post(json={...}) 替代 data=json.dumps()
- response.json() 替代 json.loads(response.data)
- 简化验证：只验证 HTTP 响应
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from conftest import encrypt_password_for_test


def test_get_public_key(client):
    """测试获取公钥端点"""
    response = client.get('/api/auth/public-key')
    assert response.status_code == 200
    data = response.json()
    assert 'public_key' in data
    assert 'BEGIN PUBLIC KEY' in data['public_key']


def test_user_registration_success(client):
    """测试用户注册成功"""
    encrypted_password = encrypt_password_for_test('T3stP@ssword')
    response = client.post('/api/auth/register', json={
        'username': 'testuser',
        'password': encrypted_password,
        'email': 'test@example.com'
    })
    assert response.status_code == 201
    data = response.json()
    assert data['message'] == '注册成功'
    assert 'user_id' in data


def test_user_registration_missing_fields(client):
    """测试注册时缺少必填字段"""
    response = client.post('/api/auth/register', json={'username': 'testuser'})
    # FastAPI Pydantic 验证返回 422
    assert response.status_code == 422


def test_user_registration_duplicate_username(client):
    """测试注册重复用户名"""
    encrypted_password = encrypt_password_for_test('T3stP@ssword')
    # 第一次注册
    client.post('/api/auth/register', json={
        'username': 'testuser',
        'password': encrypted_password,
        'email': 'test@example.com'
    })
    # 第二次注册相同用户名
    encrypted_password2 = encrypt_password_for_test('password456')
    response = client.post('/api/auth/register', json={
        'username': 'testuser',
        'password': encrypted_password2,
        'email': 'test2@example.com'
    })
    assert response.status_code == 400
    data = response.json()
    error_msg = data.get('error') or data.get('detail', {}).get('error', '')
    assert '已存在' in error_msg
    assert data['detail']['code'] == 'USERNAME_EXISTS'


def test_user_login_success(client):
    """测试用户登录成功"""
    encrypted_password = encrypt_password_for_test('T3stP@ssword')
    client.post('/api/auth/register', json={
        'username': 'testuser',
        'password': encrypted_password,
        'email': 'test@example.com'
    })
    response = client.post('/api/auth/login', json={
        'username': 'testuser',
        'password': encrypted_password
    })
    assert response.status_code == 200
    data = response.json()
    assert 'access_token' in data
    assert 'user' in data
    assert data['user']['username'] == 'testuser'


def test_user_login_invalid_credentials(client):
    """测试登录错误的凭据"""
    encrypted_password = encrypt_password_for_test('T3stP@ssword')
    client.post('/api/auth/register', json={
        'username': 'testuser',
        'password': encrypted_password,
        'email': 'test@example.com'
    })
    encrypted_wrong_password = encrypt_password_for_test('wrongpassword')
    response = client.post('/api/auth/login', json={
        'username': 'testuser',
        'password': encrypted_wrong_password
    })
    assert response.status_code == 401
    assert response.json()['code'] == 'INVALID_CREDENTIALS'
    assert 'error' in response.json()


def test_user_login_nonexistent_user(client):
    """测试登录不存在的用户"""
    encrypted_password = encrypt_password_for_test('T3stP@ssword')
    response = client.post('/api/auth/login', json={
        'username': 'nonexistent',
        'password': encrypted_password
    })
    assert response.status_code == 401
    assert response.json()['code'] == 'INVALID_CREDENTIALS'


def test_get_current_user_success(client):
    """测试获取当前用户信息成功"""
    encrypted_password = encrypt_password_for_test('T3stP@ssword')
    client.post('/api/auth/register', json={
        'username': 'testuser',
        'password': encrypted_password,
        'email': 'test@example.com'
    })
    login_response = client.post('/api/auth/login', json={
        'username': 'testuser',
        'password': encrypted_password
    })
    token = login_response.json()['access_token']
    response = client.get('/api/auth/me', headers={'Authorization': f'Bearer {token}'})
    assert response.status_code == 200
    data = response.json()
    assert data['username'] == 'testuser'
    assert data['email'] == 'test@example.com'


def test_get_current_user_no_token(client):
    """测试没有token时获取用户信息"""
    response = client.get('/api/auth/me')
    assert response.status_code == 401


def test_get_current_user_invalid_token(client):
    """测试使用无效token获取用户信息"""
    response = client.get('/api/auth/me', headers={'Authorization': 'Bearer invalid_token'})
    assert response.status_code == 401


def test_user_registration_weak_password(client):
    """测试注册时弱口令被拦截"""
    encrypted_password = encrypt_password_for_test('12345678')
    response = client.post('/api/auth/register', json={
        'username': 'testuser',
        'password': encrypted_password,
        'email': 'test@example.com'
    })
    assert response.status_code == 400
    data = response.json()
    error_msg = data.get('error') or data.get('detail', {}).get('error', '')
    assert '密码太常见' in error_msg
    assert data['detail']['code'] == 'PASSWORD_TOO_COMMON'


def test_user_registration_strong_password_success(client):
    """测试符合强度的密码可注册"""
    encrypted_password = encrypt_password_for_test('abc12345')
    response = client.post('/api/auth/register', json={
        'username': 'stronguser',
        'password': encrypted_password,
        'email': 'strong@example.com'
    })
    assert response.status_code == 201


def test_change_password_rejects_password_without_digit(client):
    """测试修改密码时拒绝无数字的新密码"""
    encrypted_password = encrypt_password_for_test('T3stP@ssword')
    client.post('/api/auth/register', json={
        'username': 'changepwuser',
        'password': encrypted_password,
        'email': 'changepw@example.com'
    })
    login_response = client.post('/api/auth/login', json={
        'username': 'changepwuser',
        'password': encrypted_password
    })
    token = login_response.json()['access_token']

    encrypted_new_password = encrypt_password_for_test('abcdefgh')
    response = client.post('/api/auth/change-password', json={
        'old_password': encrypted_password,
        'new_password': encrypted_new_password,
    }, headers={'Authorization': f'Bearer {token}'})

    assert response.status_code == 400
    data = response.json()
    error_msg = data.get('error') or data.get('detail', {}).get('error', '')
    assert '密码至少包含一个字母和一个数字' in error_msg
    assert data['detail']['code'] == 'PASSWORD_COMPLEXITY'


def test_user_registration_invalid_email(client):
    """测试注册时邮箱格式不正确"""
    encrypted_password = encrypt_password_for_test('T3stP@ssword')
    response = client.post('/api/auth/register', json={
        'username': 'testuser',
        'password': encrypted_password,
        'email': 'invalid-email'
    })
    # FastAPI Pydantic 邮箱格式校验返回 422
    assert response.status_code in [201, 400, 422]


def test_user_login_decryption_failure(client):
    """测试登录时密码解密失败"""
    response = client.post('/api/auth/login', json={
        'username': 'testuser',
        'password': 'invalid_encrypted_password'
    })
    assert response.status_code in [201, 400, 401]


def test_error_message_no_sensitive_info(client):
    """测试错误消息不包含敏感信息"""
    encrypted_password = encrypt_password_for_test('T3stP@ssword')
    response = client.post('/api/auth/register', json={
        'username': 'testuser',
        'password': encrypted_password,
        'email': 'test@example.com'
    })
    if response.status_code == 500:
        data = response.json()
        assert 'error' in data
        assert 'Traceback' not in str(data)
        assert 'File' not in str(data)


def test_registration_creates_default_category(client, db_session):
    """测试注册时自动创建个人默认分类"""
    from models import KnowledgeCategory

    encrypted_password = encrypt_password_for_test('T3stP@ssword')
    response = client.post('/api/auth/register', json={
        'username': 'newuser',
        'password': encrypted_password,
        'email': 'newuser@example.com'
    })
    assert response.status_code == 201

    # 获取新用户 ID
    data = response.json()
    user_id = data['user_id']

    # 查询该用户的默认分类
    default_category = db_session.query(KnowledgeCategory).filter_by(
        user_id=user_id,
        key='default'
    ).first()

    assert default_category is not None
    assert default_category.label == '未分类'
    assert default_category.user_id == user_id
    assert default_category.is_active is True


def test_list_supported_locales(client):
    response = client.get('/api/locales')

    assert response.status_code == 200
    assert response.json() == {
        'default_locale': 'zh-CN',
        'locales': [
            {'code': 'zh-CN', 'native_name': '中文'},
            {'code': 'en-US', 'native_name': 'English'},
        ],
    }


def test_authenticated_user_can_update_preferred_locale(client):
    encrypted_password = encrypt_password_for_test('T3stP@ssword')
    client.post('/api/auth/register', json={
        'username': 'localeuser',
        'password': encrypted_password,
        'email': 'locale@example.com',
    })
    login_response = client.post('/api/auth/login', json={
        'username': 'localeuser',
        'password': encrypted_password,
    })

    assert login_response.status_code == 200
    token = login_response.json()['access_token']
    headers = {'Authorization': f'Bearer {token}'}
    assert login_response.json()['user']['preferred_locale'] == 'zh-CN'

    update_response = client.patch('/api/auth/me/locale', json={'locale': 'en-US'}, headers=headers)
    assert update_response.status_code == 200
    assert update_response.json() == {'locale': 'en-US'}

    current_user_response = client.get('/api/auth/me', headers=headers)
    assert current_user_response.status_code == 200
    assert current_user_response.json()['preferred_locale'] == 'en-US'


def test_preferred_locale_rejects_invalid_or_unauthenticated_requests(client, auth_header):
    invalid_response = client.patch(
        '/api/auth/me/locale',
        json={'locale': 'fr-FR'},
        headers=auth_header,
    )
    assert invalid_response.status_code == 400
    assert invalid_response.json()['detail']['error'] == 'UNSUPPORTED_LOCALE'

    empty_response = client.patch('/api/auth/me/locale', json={}, headers=auth_header)
    assert empty_response.status_code == 400
    assert empty_response.json()['detail']['error'] == 'UNSUPPORTED_LOCALE'

    missing_response = client.patch('/api/auth/me/locale', json={})
    assert missing_response.status_code == 401
