"""
API 限流配置模块

使用 slowapi 实现 API 访问频率限制
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

from config import Config


def get_client_ip(request):
    """返回限流键客户端 IP。

    仅当 TRUST_PROXY=true（应用位于可信反代之后）时解析 X-Forwarded-For；
    否则按直连地址计数，避免客户端伪造该头绕过限流。

    X-Forwarded-For 取「最右」条目：项目自带的 nginx 反代用
    $proxy_add_x_forwarded_for 追加真实来源 IP，最左条目是客户端可任意
    伪造的值——取最左会让每次请求拿到全新限流桶，登录/注册等严格限流
    形同虚设。单层可信代理下最右条目即代理写入的真实来源。
    """
    if Config.TRUST_PROXY:
        forwarded = request.headers.get('X-Forwarded-For')
        if forwarded:
            entries = [entry.strip() for entry in forwarded.split(',') if entry.strip()]
            if entries:
                return entries[-1]
    return get_remote_address(request)


# 全局 limiter 实例，app.py 中注入到 app.state.limiter
limiter = Limiter(key_func=get_client_ip, default_limits=["100 per minute"])


# 限流配置常量
RATE_LIMITS = {
    # 认证相关 - 严格限流
    'login': '5 per minute',           # 登录：每分钟5次
    'register': '3 per minute',        # 注册：每分钟3次
    'refresh': '10 per minute',        # 刷新令牌：每分钟10次

    # Leader 分析与翻译
    'leader': '10 per minute',         # Leader模式：每分钟10次
    'translation': '20 per minute',    # 历史内容翻译：每分钟20次

    # 文件上传 - 中等限流
    'file_upload': '20 per minute',    # 文件上传：每分钟20次

    # 管理员操作 - 宽松限流
    'admin': '100 per minute',         # 管理员操作：每分钟100次

    # Agent 创建 - 防止滥用
    'agent_create': '10 per hour',     # 创建 Agent：每小时10次

    # Agent 更新/删除 - 防止滥用
    'agent_update': '20 per hour',     # 更新 Agent：每小时20次
    'agent_delete': '10 per hour',     # 删除 Agent：每小时10次

    # 查询操作 - 宽松限流
    'query': '60 per minute',          # 查询操作：每分钟60次

    # Agent 列表/详情 - 中等限流
    'agent_list': '60 per minute',     # Agent 列表：每分钟60次
    'agent_detail': '120 per minute',  # Agent 详情：每分钟120次
}


def get_limit(limit_name: str) -> str:
    """
    获取限流配置

    Args:
        limit_name: 限流配置名称

    Returns:
        str: 限流配置值（如 "10 per hour"）
    """
    if limit_name not in RATE_LIMITS:
        import logging
        logging.getLogger(__name__).warning(f"Unknown rate limit name: '{limit_name}', using default 60/min")
    return RATE_LIMITS.get(limit_name, '60 per minute')
