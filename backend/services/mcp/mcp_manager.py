"""
MCP Manager - OpenHarness McpClientManager 单例管理模块。

在应用启动时初始化 MCP 连接池，后续复用。
"""
import asyncio
import logging
import threading
from typing import Optional, Dict, Any

from openharness.mcp import McpClientManager
from openharness.mcp.types import McpStdioServerConfig, McpHttpServerConfig

logger = logging.getLogger(__name__)

# 全局单例
_manager_instance: Optional[McpClientManager] = None
_init_lock = threading.Lock()
_initialized = False


def _get_runtime_server_env(name: str, configured_env: Optional[Dict[str, str]]) -> Optional[Dict[str, str]]:
    """Build process env without persisting database-managed credentials."""
    runtime_env = dict(configured_env or {})

    if name == 'exa':
        # Discard legacy plaintext copies from mcp_settings.json. The encrypted
        # SystemConfig row is the only supported source for this credential.
        runtime_env.pop('EXA_API_KEY', None)

        from db import SessionLocal
        from models import SystemConfig

        session = SessionLocal()
        try:
            setting = session.query(SystemConfig).filter_by(key='EXA_API_KEY').first()
            if setting and setting.value:
                runtime_env['EXA_API_KEY'] = setting.value
            else:
                logger.warning('Exa MCP is enabled but EXA_API_KEY is not configured in admin settings')
        finally:
            session.close()

    return runtime_env or None


def get_mcp_manager() -> "McpClientManager":
    """同步获取 MCP 单例。

    Returns:
        已初始化的 McpClientManager 实例。

    Raises:
        RuntimeError: MCP manager 未初始化。
    """
    global _manager_instance
    if _manager_instance is None:
        raise RuntimeError("MCP manager not initialized. Call init_mcp_manager() first.")
    return _manager_instance


def is_mcp_initialized() -> bool:
    """检查 MCP 是否已初始化。"""
    return _initialized and _manager_instance is not None


def reset_mcp_manager():
    """重置 MCP 管理器（用于测试）。"""
    global _manager_instance, _initialized
    with _init_lock:
        _manager_instance = None
        _initialized = False


async def init_mcp_async() -> None:
    """异步初始化 MCP 连接池。

    从 ClaudeChat 的 mcp_settings.json 加载配置，
    转换为 OpenHarness 配置格式，创建 McpClientManager 单例。

    即使配置为空或连接失败，也会创建单例实例（空工具列表）。
    """
    global _manager_instance, _initialized

    with _init_lock:
        if _initialized:
            logger.info("MCP manager already initialized, skipping")
            return

        # 从 ClaudeChat 配置加载
        from .mcp_config import get_mcp_config
        mcp_mgr = get_mcp_config()

        # 转换为 OpenHarness 配置格式
        configs: Dict[str, Any] = {}
        for name, server in mcp_mgr.servers.items():
            if server.disabled:
                logger.debug(f"Skipping disabled MCP server: {name}")
                continue

            transport = server.transport.lower()
            if transport == 'stdio':
                configs[name] = McpStdioServerConfig(
                    type='stdio',
                    command=server.command or '',
                    args=server.args or [],
                    env=_get_runtime_server_env(name, server.env),
                )
            elif transport in ('sse', 'http'):
                # ClaudeChat 使用 'sse'，OpenHarness 使用 'http'
                # 优先使用 headers 字段，fallback 到 env（向后兼容）
                http_headers: Dict[str, Any] = {}
                if isinstance(server.headers, dict) and server.headers:
                    http_headers = server.headers
                elif isinstance(server.env, dict) and server.env:
                    http_headers = server.env
                configs[name] = McpHttpServerConfig(
                    type='http',
                    url=server.url or '',
                    headers=http_headers,
                )
            else:
                logger.warning(f"Unknown MCP transport type: {name} -> {transport}")
                continue

        # 创建 McpClientManager
        _manager_instance = McpClientManager(configs)

        # 连接所有服务器
        try:
            await _manager_instance.connect_all()
            tools = _manager_instance.list_tools()
            logger.info(f"MCP manager initialized: {len(configs)} servers, {len(tools)} tools")
        except Exception as e:
            logger.error(f"MCP connect_all failed: {e}")
            # 即使连接失败，单例已创建（部分服务器可能成功）

        _initialized = True


async def shutdown_mcp() -> None:
    """关闭 MCP 连接池（lifespan shutdown 调用）。"""
    global _manager_instance, _initialized

    if _manager_instance is not None:
        try:
            await _manager_instance.disconnect_all()
            logger.info("MCP manager disconnected all servers")
        except Exception as e:
            logger.error(f"MCP disconnect_all failed: {e}")
        finally:
            _manager_instance = None
            _initialized = False


def init_mcp_manager() -> None:
    """同步初始化 MCP 连接池（用于应用启动时）。

    在独立线程中运行 asyncio.run(init_mcp_async())。
    """
    import threading

    def run_async_init():
        try:
            asyncio.run(init_mcp_async())
            logger.info("MCP manager initialized (async thread)")
        except Exception as e:
            logger.error(f"MCP async init failed: {e}")

    thread = threading.Thread(target=run_async_init, name="mcp-init", daemon=True)
    thread.start()
    thread.join(timeout=30)  # 等待初始化完成，最多 30 秒（daemon 保证超时挂起不阻碍进程退出）

    if thread.is_alive():
        logger.warning("MCP init thread did not complete in 30s, continuing anyway")
    elif is_mcp_initialized():
        logger.info("MCP manager initialization completed successfully")
    else:
        logger.warning("MCP manager initialization failed or produced no instance")
