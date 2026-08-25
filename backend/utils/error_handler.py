"""
统一安全错误处理工具

提供不泄露内部异常细节的错误响应构建函数。
异常详情通过 error_ref 关联日志，便于排查。
"""
import logging
import uuid

logger = logging.getLogger(__name__)


def safe_error_response(e: Exception, user_message: str = "服务器内部错误") -> dict:
    """返回安全的错误响应 dict，不泄露内部异常细节。

    Args:
        e: 捕获的异常
        user_message: 面向用户的通用错误消息

    Returns:
        dict: 包含 error 消息和 error_ref 追溯码
    """
    error_ref = uuid.uuid4().hex[:8]
    logger.error("[%s] %s: %s", error_ref, user_message, e, exc_info=True)
    return {"error": user_message, "error_ref": error_ref}


def safe_sse_error(e: Exception, user_message: str = "处理消息时发生错误") -> dict:
    """SSE 流中的安全错误事件。

    Args:
        e: 捕获的异常
        user_message: 面向用户的通用错误消息

    Returns:
        dict: SSE error 事件
    """
    error_ref = uuid.uuid4().hex[:8]
    logger.error("[%s] %s: %s", error_ref, user_message, e, exc_info=True)
    return {"type": "error", "message": f"{user_message} (ref: {error_ref})"}
