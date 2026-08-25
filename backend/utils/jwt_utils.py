"""
JWT 工具模块

提供 JWT token 创建函数，与 FastAPI 认证兼容。
"""
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

from jose import jwt

from config import Config


# JWT 配置
JWT_ALGORITHM = "HS256"
JWT_ACCESS_TOKEN_EXPIRES = Config.JWT_ACCESS_TOKEN_EXPIRES  # 24h


def create_access_token(
    identity: str | int,
    expires_delta: Optional[timedelta] = None,
    additional_claims: Optional[Dict[str, Any]] = None,
    token_version: int = 0
) -> str:
    """
    创建 JWT access token。

    Args:
        identity: 用户标识（通常是 user_id）
        expires_delta: 自定义过期时间，默认使用配置值
        additional_claims: 额外的 payload 字段
        token_version: 用户的 token 版本号

    Returns:
        str: JWT token 字符串
    """
    if expires_delta is None:
        expires_delta = JWT_ACCESS_TOKEN_EXPIRES

    now = datetime.now(timezone.utc)
    expire = now + expires_delta

    payload = {
        "sub": str(identity),
        "exp": expire,
        "iat": now,
        "type": "access",
        "token_version": token_version
    }

    if additional_claims:
        payload.update(additional_claims)

    token = jwt.encode(
        payload,
        Config.JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM
    )

    return token