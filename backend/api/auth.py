"""
FastAPI 认证路由模块

实现 JWT 认证 API：
- POST /public-key - 获取 RSA 公钥
- POST /register - 用户注册
- POST /login - 用户登录
- GET /me - 获取当前用户
- POST /change-password - 修改密码
- POST /refresh - 刷新令牌
"""
import base64
import logging
import os
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, EmailStr
from sqlalchemy.orm import Session

from db import SessionLocal
from config import Config, generate_rsa_key_pair
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
from models import User
from api.deps import get_current_user, get_db
from utils.jwt_utils import create_access_token
from utils.locale_utils import is_supported_locale
from utils.rate_limit import limiter, get_limit


logger = logging.getLogger(__name__)

# 创建认证路由
router = APIRouter(prefix="/api/auth", tags=["auth"])

# 线程安全的密钥加载锁
_rsa_lock = threading.Lock()
# 内存缓存的密钥对
_rsa_keys_cache = {}


# ==================== Pydantic 模型 ====================

class PublicKeyResponse(BaseModel):
    public_key: str


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)  # RSA 加密后的 Base64


class LoginResponse(BaseModel):
    access_token: str
    user: dict


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)  # RSA 加密后的 Base64
    email: EmailStr = Field(...)  # 邮箱，Pydantic EmailStr 格式校验


class RegisterResponse(BaseModel):
    message: str
    user_id: int


class UserResponse(BaseModel):
    id: int
    username: str
    email: Optional[str]
    is_admin: bool = False
    preferred_locale: str


class LocaleUpdateRequest(BaseModel):
    locale: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1)  # RSA 加密后的 Base64
    new_password: str = Field(..., min_length=1)  # RSA 加密后的 Base64


class RefreshResponse(BaseModel):
    access_token: str
    user: dict


# ==================== 辅助函数 ====================

@dataclass(frozen=True)
class PasswordValidationResult:
    """密码强度校验结果"""
    valid: bool
    error: Optional[str] = None
    code: Optional[str] = None


def validate_password(password: str) -> PasswordValidationResult:
    """验证密码强度"""
    # 常见弱口令黑名单（全部小写比较）
    WEAK_PASSWORDS = frozenset({
        'password', '123456', '12345678', '123456789', '1234567890',
        'qwerty', 'abc123', 'monkey', 'master', 'dragon',
        'letmein', 'login', 'princess', 'football', 'shadow',
        'sunshine', 'trustno1', 'iloveyou', 'batman', 'access',
        'hello', 'charlie', 'donald', 'admin', 'admin123',
        'password1', 'password123', 'password1234',
        'welcome', 'welcome1', 'p@ssw0rd', 'passw0rd',
        'qwerty123', '1q2w3e4r', '1qaz2wsx',
    })

    if password.lower() in WEAK_PASSWORDS:
        return PasswordValidationResult(
            valid=False,
            error="密码太常见，请使用更强的密码",
            code="PASSWORD_TOO_COMMON"
        )

    if not password or len(password) < Config.PASSWORD_MIN_LENGTH:
        return PasswordValidationResult(
            valid=False,
            error=f"密码长度至少为{Config.PASSWORD_MIN_LENGTH}个字符",
            code="PASSWORD_TOO_SHORT"
        )

    if Config.PASSWORD_REQUIRE_LETTER and not re.search(r"[A-Za-z]", password):
        return PasswordValidationResult(valid=False, error="密码至少包含一个字母和一个数字", code="PASSWORD_COMPLEXITY")

    if Config.PASSWORD_REQUIRE_DIGIT and not re.search(r"\d", password):
        return PasswordValidationResult(valid=False, error="密码至少包含一个字母和一个数字", code="PASSWORD_COMPLEXITY")

    return PasswordValidationResult(valid=True)


def _record_auth_failure(user: User, db_session: Session) -> None:
    """记录认证失败（原子自增 + 锁定判断）。

    login 和 change_password 共用此逻辑，避免重复。
    调用方在捕获 HTTPException 前调用，失败计数已持久化到 DB。
    """
    # 原子自增（SQL 层面 SET failed = failed + 1，避免读后写竞态）
    db_session.query(User).filter_by(id=user.id).update(
        {"failed_login_attempts": User.failed_login_attempts + 1}
    )
    db_session.flush()
    db_session.refresh(user, attribute_names=['failed_login_attempts'])

    if user.failed_login_attempts >= 5:
        user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
        user.lockout_reason = '连续登录失败超过5次'
        logger.warning(
            f"Account locked due to failed attempts: user_id={user.id}, "
            f"attempts={user.failed_login_attempts}"
        )

    db_session.commit()


def get_or_create_rsa_keys() -> tuple[str, str]:
    """
    获取或创建 RSA 密钥对（持久化存储）

    密钥存储策略：
    1. 优先从内存缓存读取（性能优化）
    2. 其次从文件系统读取（持久化）
    3. 最后生成新密钥并保存到文件
    """
    # 快速路径：检查内存缓存
    if 'private_key' in _rsa_keys_cache and 'public_key' in _rsa_keys_cache:
        return _rsa_keys_cache['private_key'], _rsa_keys_cache['public_key']

    # 加锁进行慢速路径
    with _rsa_lock:
        # 双重检查
        if 'private_key' in _rsa_keys_cache and 'public_key' in _rsa_keys_cache:
            return _rsa_keys_cache['private_key'], _rsa_keys_cache['public_key']

        # 获取密钥文件路径
        keys_dir = Config.RSA_KEYS_DIR or 'keys'
        private_key_path = os.path.join(keys_dir, 'private_key.pem')
        public_key_path = os.path.join(keys_dir, 'public_key.pem')

        try:
            # 尝试从文件加载密钥
            if os.path.exists(private_key_path) and os.path.exists(public_key_path):
                logger.info(f"Loading RSA keys from {keys_dir}")

                with open(private_key_path, 'r', encoding='utf-8') as f:
                    private_key = f.read()

                with open(public_key_path, 'r', encoding='utf-8') as f:
                    public_key = f.read()

                logger.info("RSA keys loaded successfully from files")
            else:
                # 文件不存在，生成新密钥对
                logger.warning(f"RSA keys not found in {keys_dir}, generating new keys")

                Path(keys_dir).mkdir(parents=True, exist_ok=True)

                private_key, public_key = generate_rsa_key_pair()

                with open(private_key_path, 'w', encoding='utf-8') as f:
                    f.write(private_key)

                with open(public_key_path, 'w', encoding='utf-8') as f:
                    f.write(public_key)

                os.chmod(private_key_path, 0o600)
                os.chmod(public_key_path, 0o644)

                logger.info(f"New RSA keys generated and saved to {keys_dir}")

            # 缓存到内存
            _rsa_keys_cache['private_key'] = private_key
            _rsa_keys_cache['public_key'] = public_key

            return private_key, public_key

        except Exception as e:
            logger.error(f"Failed to load or generate RSA keys: {str(e)}", exc_info=True)
            raise RuntimeError(
                "RSA 密钥加载失败，请检查 data/keys/ 目录权限和磁盘空间"
            ) from e


def decrypt_password(encrypted_base64: str) -> Optional[str]:
    """使用 RSA 私钥解密密码（OAEP 优先，PKCS1v15 兼容回退）"""
    try:
        private_key_pem, _ = get_or_create_rsa_keys()

        private_key = serialization.load_pem_private_key(
            private_key_pem.encode('utf-8'),
            password=None,
            backend=default_backend()
        )

        encrypted_bytes = base64.b64decode(encrypted_base64)

        # 优先 OAEP（更安全，防 Bleichenbacher 攻击）
        try:
            decrypted_bytes = private_key.decrypt(
                encrypted_bytes,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None
                )
            )
            return decrypted_bytes.decode('utf-8')
        except (ValueError, TypeError) as oaep_err:
            # ValueError: 块大小不匹配（非 OAEP 密文）；TypeError: 密钥格式问题
            logger.debug("OAEP 解密失败，回退 PKCS1v15: %s", oaep_err)

        # 回退 PKCS1v15（兼容前端 JSEncrypt）
        decrypted_bytes = private_key.decrypt(
            encrypted_bytes,
            padding.PKCS1v15()
        )
        return decrypted_bytes.decode('utf-8')
    except Exception as e:
        logger.error("解密密码失败: %s", e)
        return None


# ==================== 路由端点 ====================

@router.get("/public-key", response_model=PublicKeyResponse)
async def get_public_key():
    """获取 RSA 公钥用于加密密码"""
    try:
        _, public_key = get_or_create_rsa_keys()
        return {"public_key": public_key}
    except Exception as e:
        logger.error(f"获取公钥错误: {str(e)}")
        raise HTTPException(status_code=500, detail={"code": "PUBLIC_KEY_UNAVAILABLE", "error": "获取公钥失败"})


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(get_limit('register'))
async def register(request: Request, body: RegisterRequest, db_session: Session = Depends(get_db)):
    """用户注册"""
    try:
        username = body.username.strip()
        encrypted_password = body.password
        email = body.email.strip()

        # 解密密码
        password = decrypt_password(encrypted_password)
        if password is None:
            raise HTTPException(
                status_code=400,
                detail={"code": "PASSWORD_DECRYPTION_FAILED", "error": "密码解密失败，请刷新页面重试"}
            )

        # 验证密码强度
        password_validation = validate_password(password)
        if not password_validation.valid:
            raise HTTPException(
                status_code=400,
                detail={"code": password_validation.code, "error": password_validation.error}
            )

        # 检查用户名是否已存在
        existing_user = db_session.query(User).filter_by(username=username).first()
        if existing_user:
            raise HTTPException(
                status_code=400,
                detail={"code": "USERNAME_EXISTS", "error": "用户名已存在"}
            )

        # 检查邮箱是否已存在
        existing_email = db_session.query(User).filter_by(email=email).first()
        if existing_email:
            raise HTTPException(
                status_code=400,
                detail={"code": "EMAIL_EXISTS", "error": "邮箱已被注册"}
            )

        # 创建新用户
        user = User(username=username, email=email)
        user.set_password(password)

        db_session.add(user)
        db_session.flush()

        # 创建个人默认分类（新用户福利）
        from models import KnowledgeCategory
        default_category = KnowledgeCategory(
            key="default",
            label="未分类",
            user_id=user.id,
            description="默认分类",
            icon="Document",
            sort_order=0,
            is_active=True
        )
        db_session.add(default_category)

        db_session.commit()

        logger.info(f"User registered: {user.username}")

        return {
            "message": "注册成功",
            "user_id": user.id
        }

    except HTTPException:
        raise
    except Exception as e:
        db_session.rollback()
        logger.error(f"注册错误: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={"code": "REGISTER_FAILED", "error": "注册失败，请稍后重试"}
        )


@router.post("/login", response_model=LoginResponse)
@limiter.limit(get_limit('login'))
async def login(request: Request, body: LoginRequest, db_session: Session = Depends(get_db)):
    """用户登录（带账户锁定保护）"""
    try:
        username = body.username.strip()
        encrypted_password = body.password

        # 解密密码
        password = decrypt_password(encrypted_password)
        if password is None:
            logger.warning(f"密码解密失败: username={username}")
            raise HTTPException(
                status_code=401,
                detail={"code": "INVALID_CREDENTIALS", "error": "用户名或密码错误"}
            )

        # 查找用户
        user = db_session.query(User).filter_by(username=username).first()

        if not user:
            raise HTTPException(
                status_code=401,
                detail={"code": "INVALID_CREDENTIALS", "error": "用户名或密码错误"}
            )

        # 检查账户是否被锁定
        if user.locked_until and user.locked_until > datetime.now(timezone.utc):
            # 统一错误提示，不泄露锁定状态
            raise HTTPException(
                status_code=401,
                detail={"code": "INVALID_CREDENTIALS", "error": "用户名或密码错误"}
            )

        # 如果锁定已过期，重置计数
        if user.locked_until and user.locked_until <= datetime.now(timezone.utc):
            user.failed_login_attempts = 0
            user.locked_until = None
            user.lockout_reason = None

        if user.account_type == 'service' or user.login_disabled:
            logger.warning(f"Disabled login rejected: user_id={user.id}, account_type={user.account_type}")
            raise HTTPException(
                status_code=401,
                detail={"code": "INVALID_CREDENTIALS", "error": "用户名或密码错误"}
            )

        # 验证密码
        if not user.check_password(password):
            _record_auth_failure(user, db_session)
            raise HTTPException(
                status_code=401,
                detail={"code": "INVALID_CREDENTIALS", "error": "用户名或密码错误"}
            )

        # 登录成功，重置失败计数
        user.failed_login_attempts = 0
        user.locked_until = None
        user.lockout_reason = None
        user.last_login = datetime.now(timezone.utc)
        db_session.commit()

        # 创建访问令牌（包含 token_version）
        access_token = create_access_token(identity=user.id, token_version=user.token_version)

        # secure=True 仅在非开发环境启用（开发 HTTP 环境下设 secure 则 cookie 不发送）
        is_production = os.environ.get('APP_ENV') != 'development'

        # 构建响应，设置 httpOnly cookie（XSS 无法读取）
        response = JSONResponse(content={
            "access_token": access_token,
            "user": {
                "id": user.id,
                "username": user.username,
                "is_admin": user.is_admin,
                "preferred_locale": user.preferred_locale,
            }
        })
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            samesite="strict",
            secure=is_production,
            max_age=86400  # 24 小时
        )
        return response

    except HTTPException:
        raise
    except Exception as e:
        db_session.rollback()
        logger.error(f"登录错误: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={"code": "LOGIN_FAILED", "error": "登录失败，请稍后重试"}
        )


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    """获取当前登录用户信息"""
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "is_admin": user.is_admin,
        "preferred_locale": user.preferred_locale,
    }


@router.patch("/me/locale")
async def update_preferred_locale(
    body: LocaleUpdateRequest,
    user: User = Depends(get_current_user),
    db_session: Session = Depends(get_db),
):
    """Persist the authenticated user's explicit UI locale preference."""
    if not is_supported_locale(body.locale):
        raise HTTPException(
            status_code=400,
            detail={"error": "UNSUPPORTED_LOCALE"},
        )

    user.preferred_locale = body.locale
    db_session.commit()
    return {"locale": user.preferred_locale}


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db_session: Session = Depends(get_db)
):
    """修改密码"""
    try:
        # 解密密码
        old_password = decrypt_password(request.old_password)
        new_password = decrypt_password(request.new_password)

        if old_password is None or new_password is None:
            raise HTTPException(
                status_code=400,
                detail={"code": "PASSWORD_DECRYPTION_FAILED", "error": "密码解密失败，请刷新页面重试"}
            )

        # 验证旧密码（复用登录侧失败计数逻辑，防暴力破解）
        if not user.check_password(old_password):
            _record_auth_failure(user, db_session)
            raise HTTPException(
                status_code=400,
                detail={"code": "OLD_PASSWORD_INCORRECT", "error": "旧密码错误"}
            )

        # 验证新密码强度
        password_validation = validate_password(new_password)
        if not password_validation.valid:
            raise HTTPException(
                status_code=400,
                detail={"code": password_validation.code, "error": password_validation.error}
            )

        # 新密码不能与旧密码相同
        if old_password == new_password:
            raise HTTPException(
                status_code=400,
                detail={"code": "PASSWORD_REUSED", "error": "新密码不能与旧密码相同"}
            )

        # 更新密码
        user.set_password(new_password)
        user.token_version += 1  # 使旧 token 失效
        # 改密成功，重置失败计数
        user.failed_login_attempts = 0
        user.locked_until = None
        user.lockout_reason = None
        db_session.commit()

        # 清除 httpOnly cookie，强制当前设备重新登录
        response = JSONResponse(content={"message": "密码修改成功"})
        response.delete_cookie("access_token")
        return response

    except HTTPException:
        raise
    except Exception as e:
        db_session.rollback()
        logger.error(f"修改密码错误: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={"code": "CHANGE_PASSWORD_FAILED", "error": "修改密码失败，请稍后重试"}
        )



@router.post("/refresh", response_model=RefreshResponse)
@limiter.limit(get_limit('refresh'))
async def refresh_token(
    request: Request,
    user: User = Depends(get_current_user),
    db_session: Session = Depends(get_db)
):
    """刷新访问令牌（不递增 token_version，多端会话不互踢）"""
    try:
        # 不递增 token_version：token_version 仅用于改密/吊销场景
        # 多端 refresh 时旧 token 仍有效，避免并发会话互踢

        # 创建新的访问令牌
        access_token = create_access_token(identity=user.id, token_version=user.token_version)

        is_production = os.environ.get('APP_ENV') != 'development'

        # 构建响应，刷新 httpOnly cookie
        response = JSONResponse(content={
            "access_token": access_token,
            "user": {
                "id": user.id,
                "username": user.username,
                "is_admin": user.is_admin
            }
        })
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            samesite="strict",
            secure=is_production,
            max_age=86400
        )
        return response

    except Exception as e:
        db_session.rollback()
        logger.error(f"刷新令牌错误: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={"error": "刷新令牌失败"}
        )
