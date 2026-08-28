"""
Pytest 配置文件 - 提供通用 fixture（FastAPI 版）

安全：使用独立测试数据库（TEST_DATABASE_URL），不影响生产库。
测试隔离分两层：
1. FastAPI dependency_overrides 覆盖 Depends(get_db) 的路由层会话；
2. 全局重定向 db.SessionLocal / db.SessionScoped 为测试工厂，覆盖绕过
   依赖注入、直接使用 SessionLocal 的代码路径（模块级 from-import /
   函数默认参数 / 函数内延迟导入三种形态，详见下方重定向说明）。
"""
import pytest
import base64
import os

# 设置环境变量跳过 MCP 初始化（测试环境）
os.environ['SKIP_MCP_INIT'] = 'true'
# 测试环境禁用限流（避免测试间相互干扰）
os.environ['RATELIMIT_ENABLED'] = 'false'

from sqlalchemy import create_engine, text
from sqlalchemy.orm import scoped_session, sessionmaker
from fastapi.testclient import TestClient

from config import Config

# ==================== 测试数据库隔离 ====================

# 使用独立测试数据库，与生产库完全隔离
_test_db_url = Config.TEST_DATABASE_URL
if not _test_db_url and Config.SQLALCHEMY_DATABASE_URI:
    # 通用规则：主库名追加 _test 后缀作为测试库
    _base, _dbname = Config.SQLALCHEMY_DATABASE_URI.rsplit('/', 1)
    _test_db_url = f'{_base}/{_dbname}_test'

# fail-safe：测试库必须与主库不同名，绝不静默回退到生产库
# （teardown 会 DROP/TRUNCATE 全表，指错库即毁灭数据）
if not _test_db_url or not _test_db_url.rsplit('/', 1)[-1].endswith('_test'):
    raise RuntimeError(
        "测试数据库未正确配置！测试会清空目标库的全部表。\n"
        "请在环境变量中设置独立的测试库，例如：\n"
        "TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/agent_teams_test\n"
        "或确保 DATABASE_URL 的库名能安全追加 _test 后缀。"
    )

test_engine = create_engine(_test_db_url, pool_pre_ping=True)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

# ==================== SessionLocal 全局重定向 ====================
# 必须在导入任何业务模块之前执行！请勿把下方"业务模块导入"上移。
#
# 背景：约 9 处源码绕过 FastAPI Depends(get_db)，直接使用 SessionLocal，
# 覆盖三种导入形态：
#   - 模块级 from-import：api/auth.py:27、app.py:31、database.py:10、
#     translation/worker.py、translation/cache.py 等
#   - 函数默认参数（def f(session_factory=SessionLocal)，导入时求值绑定）：
#     services/agentteams_integration_launch.py 多处
#   - 函数内延迟导入：api/admin/agent_admin_api.py、services/mcp/mcp_manager.py
# dependency_overrides[get_db] 盖不住这些路径。
#
# 原理：Python 的 from-import 是"导入时刻"的一次性值拷贝，而 pytest 保证
# 本 conftest 先于所有测试模块与 fixture 加载。因此只要在业务模块首次
# 导入前替换 db 模块属性，之后一切 `from db import SessionLocal` 与函数
# 默认参数拿到的都是测试工厂。生产运行时不加载本文件，不受影响。
import db as _db_infra

_db_infra.SessionLocal = TestSessionLocal
# DBWrapper.session 与 Base.query 均走 scoped_session，需一并替换，
# 否则 db.session 仍指向主库
_db_infra.SessionScoped = scoped_session(TestSessionLocal)

# ---- 业务模块导入：必须位于上方重定向之后 ----
from db import Base, db
from database import get_db
from models import User
from api.auth import get_or_create_rsa_keys
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend


@pytest.fixture(scope="function")
def db_session():
    """测试数据库会话（每次测试后 TRUNCATE 全表，隔离数据）"""
    Base.metadata.create_all(bind=test_engine)
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()
        # 业务代码可能通过 db 的 scoped_session 绕过显式 fixture 会话；
        # 移除当前线程的全局会话，避免其未提交事务阻塞测试库清理。
        db.remove()
        # TRUNCATE 所有用户表，确保测试间数据隔离
        with test_engine.begin() as conn:
            result = conn.execute(text(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            ))
            tables = [row[0] for row in result]
            if tables:
                conn.execute(text(
                    f"TRUNCATE TABLE {', '.join(tables)} RESTART IDENTITY CASCADE"
                ))



def _override_get_db():
    """测试用数据库会话（指向测试库）"""
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


def encrypt_password_for_test(password: str) -> str:
    """测试辅助函数：RSA 加密密码"""
    _, public_key_pem = get_or_create_rsa_keys()
    public_key = serialization.load_pem_public_key(
        public_key_pem.encode('utf-8'),
        backend=default_backend()
    )
    encrypted_bytes = public_key.encrypt(
        password.encode('utf-8'),
        padding.PKCS1v15()
    )
    return base64.b64encode(encrypted_bytes).decode('utf-8')


@pytest.fixture(scope="function")
def client():
    """FastAPI 测试客户端（使用独立测试数据库）"""
    from app import app

    # 覆盖 FastAPI 依赖注入，路由层使用测试库
    app.dependency_overrides[get_db] = _override_get_db

    # 创建测试数据库表
    Base.metadata.create_all(bind=test_engine)

    yield TestClient(app)

    # 清理：删除所有表（仅测试库）
    db.remove()
    with test_engine.connect() as conn:
        result = conn.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        ))
        tables = [row[0] for row in result]
        if tables:
            conn.execute(text(f"DROP TABLE IF EXISTS {', '.join(tables)} CASCADE"))
            conn.commit()

    # 清除依赖覆盖
    app.dependency_overrides.clear()


@pytest.fixture
def auth_header(client):
    """创建认证用户并返回认证头"""
    encrypted_password = encrypt_password_for_test('T3stP@ssword')
    response = client.post('/api/auth/register', json={
        'username': 'testuser',
        'password': encrypted_password,
        'email': 'test@example.com'
    })
    assert response.status_code in [201, 400]

    login_response = client.post('/api/auth/login', json={
        'username': 'testuser',
        'password': encrypted_password
    })
    assert login_response.status_code == 200
    token = login_response.json()['access_token']

    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def another_user_auth_header(client):
    """创建另一个用户并返回认证头"""
    encrypted_password = encrypt_password_for_test('T3stP@ssword')
    response = client.post('/api/auth/register', json={
        'username': 'anotheruser',
        'password': encrypted_password,
        'email': 'another@example.com'
    })
    assert response.status_code in [201, 400]

    login_response = client.post('/api/auth/login', json={
        'username': 'anotheruser',
        'password': encrypted_password
    })
    assert login_response.status_code == 200
    token = login_response.json()['access_token']
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def admin_auth_header(client):
    """创建管理员用户并返回认证头"""
    from models import User

    encrypted_password = encrypt_password_for_test('Admin@123')
    # 注册普通用户
    response = client.post('/api/auth/register', json={
        'username': 'adminuser',
        'password': encrypted_password,
        'email': 'admin@example.com'
    })
    assert response.status_code in [201, 400]

    # 在测试数据库中提升为管理员
    session = TestSessionLocal()
    try:
        user = session.query(User).filter_by(username='adminuser').first()
        user.is_admin = True
        session.commit()
    finally:
        session.close()

    # 登录获取 token
    login_response = client.post('/api/auth/login', json={
        'username': 'adminuser',
        'password': encrypted_password
    })
    assert login_response.status_code == 200
    token = login_response.json()['access_token']
    return {'Authorization': f'Bearer {token}'}
