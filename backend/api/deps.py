"""
FastAPI 依赖注入模块

提供认证相关的依赖注入函数，供路由层使用。
"""
import logging

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError, ExpiredSignatureError
from sqlalchemy.orm import Session

from config import Config
from models import User, SecurityLog
from database import get_db  # 从 database 导入，使用 scoped_session
from utils.locale_utils import SupportedLocale, resolve_locale

logger = logging.getLogger(__name__)

# HTTPBearer 安全方案（auto_error=False 以自定义 401 响应）
security = HTTPBearer(auto_error=False)


def _extract_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
) -> str | None:
    """
    从请求中提取 JWT token。

    优先级：
    1. Authorization header（显式指定，优先）
    2. httpOnly cookie（自动携带，fallback）
    """
    # 优先：Authorization header（调用方显式指定，优先级最高）
    if credentials is not None:
        return credentials.credentials

    # 回退：httpOnly cookie（浏览器自动携带）
    cookie_token = request.cookies.get("access_token")
    if cookie_token:
        return cookie_token

    return None


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db_session: Session = Depends(get_db)
) -> User:
    """
    从 JWT token 解析并验证当前用户。

    支持两种 token 传递方式（优先级：cookie > header）：
    - httpOnly cookie: access_token（新方式，XSS 安全）
    - Authorization header: Bearer <token>（旧方式，向后兼容）
    """
    token = _extract_token(request, credentials)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "缺少认证令牌", "message": "请登录或在 Authorization header 中提供 Bearer token"}
        )

    try:
        payload = jwt.decode(
            token,
            Config.JWT_SECRET_KEY,
            algorithms=["HS256"]
        )

        user_id_str = payload.get("sub")
        if user_id_str is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "无效的令牌", "message": "token 缺少 subject"}
            )

        user_id = int(user_id_str)

    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "令牌已过期", "message": "请刷新令牌或重新登录"}
        )

    except JWTError as e:
        logger.debug("JWT verification failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "无效的令牌", "message": "令牌验证失败"}
        )

    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "无效的令牌", "message": "user_id 格式错误"}
        )

    user = db_session.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "用户不存在", "message": "token 对应的用户已删除"}
        )

    # 验证 token_version，使改密后旧 token 失效
    token_version = payload.get("token_version", 0)
    if token_version != user.token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "令牌已失效", "message": "密码已修改，请重新登录"}
        )

    return user


def get_admin_user(
    user: User = Depends(get_current_user)
) -> User:
    """
    验证当前用户是否为管理员。
    用于管理端点的权限控制。
    """
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "需要管理员权限", "message": "您没有权限访问此资源"}
        )
    return user


def resolve_request_locale(
    request: Request,
    explicit_locale: str | None,
    user: User,
) -> SupportedLocale:
    """Resolve a locale snapshot or return the canonical API error."""
    try:
        return resolve_locale(
            explicit_locale,
            user.preferred_locale,
            request.headers.get('accept-language'),
        )
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail={'code': 'UNSUPPORTED_LOCALE', 'error': '不支持的语言'},
        )


# 角色等级：admin > editor > viewer
ROLE_HIERARCHY = {'viewer': 0, 'editor': 1, 'admin': 2}


def audit_log(
    user_id: int,
    action: str,
    resource_type: str = None,
    resource_id: int = None,
    details: dict = None,
    db_session: Session = None
) -> None:
    """
    记录 API 操作审计日志

    Args:
        user_id: 操作用户 ID
        action: 操作类型（如 conversation.create, file.upload）
        resource_type: 资源类型（如 conversation, file）
        resource_id: 资源 ID
        details: 附加详情（JSON）
        db_session: 数据库会话
    """
    try:
        log = SecurityLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details
        )
        db_session.add(log)
        db_session.flush()
    except Exception as e:
        logger.warning(f"审计日志写入失败: {e}")
