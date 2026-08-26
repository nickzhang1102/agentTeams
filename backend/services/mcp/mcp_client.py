"""
MCP 客户端
实现 Model Context Protocol 客户端功能
支持 stdio 和 SSE 传输

安全说明：
- connect_stdio 使用命令白名单校验
- 仅允许 node, npx, python, uvx 等安全命令
- 阻止 shell 元字符和路径遍历
- 子进程环境按白名单继承（_MCP_ENV_ALLOWLIST），不透传后端密钥

异步说明（MCP-2 修复）：
- SSE 路径：connect_sse / _send_sse_request 使用 httpx.AsyncClient，
  避免阻塞 FastAPI 事件循环
- stdio 路径：保持同步（subprocess.Popen），但加 per-connection
  threading.Lock 保护 request_id 递增和 stdin/stdout 并发访问
- 提供 execute_tool_async / get_resource_async 供 async 上下文使用
"""
import os
import json
import logging
import subprocess
import asyncio
import threading
import re
from typing import Dict, List, Any, Optional, Callable, Set
from dataclasses import dataclass
from concurrent.futures import Future

logger = logging.getLogger(__name__)


# MCP 命令白名单（仅允许这些基础命令）
ALLOWED_MCP_COMMANDS: Set[str] = {
    'node', 'npm', 'npx', 'yarn', 'pnpm',
    'python', 'python3', 'py',
    'uvx', 'uv',
    'java', 'jruby',
    'go',
    'ruby',
    'php',
}

# 禁止的 shell 元字符
BLOCKED_CHARS: Set[str] = {
    ';', '|', '&', '$', '`', '\\', '\n', '\r',
    '>', '<', '(', ')', '{', '}',
}

# MCP 子进程环境变量白名单：仅传递运行所必需的系统变量，避免把
# DATABASE_URL / SECRET_KEY / JWT_SECRET_KEY 等后端密钥经进程环境泄漏给
# MCP server（含 npx -y 拉取的第三方包）。额外放行项用 MCP_ENV_PASSTHROUGH
# 环境变量（逗号分隔）显式声明。
_MCP_ENV_ALLOWLIST: Set[str] = {
    'PATH', 'PATHEXT', 'HOME', 'USERPROFILE',
    'APPDATA', 'LOCALAPPDATA', 'PROGRAMFILES', 'SYSTEMROOT', 'COMSPEC',
    'LANG', 'LC_ALL', 'TMP', 'TEMP', 'TMPDIR',
}


def _build_mcp_process_env() -> Dict[str, str]:
    """构建 MCP 子进程环境：白名单系统变量 + MCP_ENV_PASSTHROUGH 显式扩展。"""
    allow = set(_MCP_ENV_ALLOWLIST)
    extra = os.environ.get('MCP_ENV_PASSTHROUGH', '')
    allow.update(key.strip() for key in extra.split(',') if key.strip())
    return {key: value for key, value in os.environ.items() if key in allow}


def validate_mcp_command(command: str, args: List[str]) -> tuple[bool, str]:
    """校验 MCP 命令安全性

    策略：
    1. 提取 basename（如 /usr/bin/python → python），白名单校验 basename
    2. BLOCKED_CHARS 仅用于参数部分，不对命令本身拦截（绝对路径含 / \\ 不应被拒）

    Args:
        command: 命令字符串
        args: 参数列表

    Returns:
        (is_valid, error_message)
    """
    if not command:
        return False, "Empty command"

    # 1. 提取命令基本名称（支持绝对路径如 /usr/bin/python）
    #    command 可能含空格（如 "node script.js"），取第一段的 basename
    first_token = command.split()[0] if ' ' in command else command
    base_cmd = os.path.basename(first_token)

    # 2. 白名单校验 basename
    if base_cmd not in ALLOWED_MCP_COMMANDS:
        return False, f"Command not in whitelist: {base_cmd}"

    # 3. 检查参数中的 shell 元字符注入（命令本身已过白名单，不额外拦截）
    for char in BLOCKED_CHARS:
        for arg in args:
            if char in arg:
                return False, f"Blocked character in args: {char}"

    # 4. 检查路径遍历
    if '..' in command or '..' in ''.join(args):
        return False, "Path traversal detected"

    return True, ""


@dataclass
class McpTool:
    """MCP 工具定义"""
    name: str
    description: str
    input_schema: Dict[str, Any]
    server_name: str
    
    def to_claude_format(self) -> Dict[str, Any]:
        """转换为 Claude API 格式"""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema
        }


@dataclass
class McpResource:
    """MCP 资源定义"""
    uri: str
    name: str
    description: str
    mime_type: str
    server_name: str


class McpClient:
    """MCP 客户端"""
    
    def __init__(self):
        """初始化 MCP 客户端"""
        self.connections: Dict[str, Any] = {}  # server_name -> connection
        self.tools: Dict[str, McpTool] = {}  # tool_name -> McpTool
        self.resources: Dict[str, McpResource] = {}  # uri -> McpResource
        self._lock = threading.Lock()
        self._stdio_locks: Dict[str, threading.Lock] = {}  # per-connection stdio 锁
    
    def connect_stdio(self, server_name: str, command: str, args: List[str], env: Dict[str, str] = None) -> bool:
        """
        连接到 stdio 传输的 MCP 服务器

        Args:
            server_name: 服务器名称
            command: 命令
            args: 参数列表
            env: 环境变量

        Returns:
            bool: 是否连接成功
        """
        try:
            # 安全校验：命令白名单 + shell 元字符检测
            is_valid, error_msg = validate_mcp_command(command, args)
            if not is_valid:
                logger.warning(f"MCP command blocked: {error_msg} (server={server_name})")
                return False

            # 准备环境变量：仅白名单系统变量 + server 自定义配置，
            # 防止后端密钥经进程环境泄漏给 MCP server（见 SECURITY.md）
            process_env = _build_mcp_process_env()
            if env:
                process_env.update(env)
            
            # 启动进程
            process = subprocess.Popen(
                [command] + args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=process_env,
                text=True,
                bufsize=1
            )
            
            # 存储连接
            self.connections[server_name] = {
                "type": "stdio",
                "process": process,
                "request_id": 0
            }
            self._stdio_locks[server_name] = threading.Lock()
            
            # 发送初始化请求
            if not self._initialize(server_name):
                logger.error(f"Failed to initialize MCP server: {server_name}")
                self.disconnect(server_name)
                return False
            
            # 获取工具和资源列表
            self._discover_tools(server_name)
            self._discover_resources(server_name)
            
            logger.info(f"Connected to MCP server: {server_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to MCP server {server_name}: {e}")
            return False
    
    async def connect_sse(self, server_name: str, url: str, headers: Dict[str, str] = None) -> bool:
        """
        连接到 SSE 传输的 MCP 服务器（async，使用 httpx.AsyncClient）

        Args:
            server_name: 服务器名称
            url: SSE 端点 URL
            headers: 可选的 HTTP headers（如鉴权 token）

        Returns:
            bool: 是否连接成功
        """
        try:
            import httpx

            # 存储连接信息，使用 httpx.AsyncClient 替代同步 requests.Session
            self.connections[server_name] = {
                "type": "sse",
                "url": url,
                "request_id": 0,
                "client": httpx.AsyncClient(base_url=url, timeout=30.0, headers=headers or {})
            }

            # 发送初始化请求（async 版本）
            if not await self._initialize_async(server_name):
                logger.error(f"Failed to initialize MCP server: {server_name}")
                await self._disconnect_async(server_name)
                return False

            # 获取工具和资源列表（async 版本）
            await self._discover_tools_async(server_name)
            await self._discover_resources_async(server_name)

            logger.info(f"Connected to MCP server via SSE: {server_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to MCP server {server_name} via SSE: {e}")
            return False
    
    def disconnect(self, server_name: str):
        """断开与服务器的连接"""
        if server_name not in self.connections:
            return

        conn = self.connections[server_name]

        try:
            if conn["type"] == "stdio":
                process = conn["process"]
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    logger.warning(f"Process {server_name} did not terminate gracefully, killing...")
                    process.kill()
                    process.wait(timeout=2)
            elif conn["type"] == "sse":
                # 关闭 httpx.AsyncClient，防止套接字泄漏
                client = conn.get("client")
                if client:
                    try:
                        loop = asyncio.new_event_loop()
                        try:
                            loop.run_until_complete(client.aclose())
                        finally:
                            loop.close()
                    except Exception as e:
                        logger.warning(f"Error closing SSE client for {server_name}: {e}")
        except Exception as e:
            logger.warning(f"Error disconnecting from {server_name}: {e}")

        # 移除该服务器的工具和资源
        with self._lock:
            self.tools = {k: v for k, v in self.tools.items() if v.server_name != server_name}
            self.resources = {k: v for k, v in self.resources.items() if v.server_name != server_name}
            del self.connections[server_name]
            self._stdio_locks.pop(server_name, None)

        logger.info(f"Disconnected from MCP server: {server_name}")

    async def _disconnect_async(self, server_name: str):
        """异步断开 SSE 连接（关闭 httpx.AsyncClient）"""
        if server_name not in self.connections:
            return

        conn = self.connections[server_name]
        try:
            if conn["type"] == "sse" and "client" in conn:
                await conn["client"].aclose()
        except Exception as e:
            logger.warning(f"Error closing httpx client for {server_name}: {e}")

        with self._lock:
            self.tools = {k: v for k, v in self.tools.items() if v.server_name != server_name}
            self.resources = {k: v for k, v in self.resources.items() if v.server_name != server_name}
            self.connections.pop(server_name, None)

        logger.info(f"Disconnected from MCP server (async): {server_name}")
    
    def _send_request(self, server_name: str, method: str, params: Dict = None) -> Optional[Dict]:
        """发送 JSON-RPC 请求（同步，stdio 路径使用）"""
        if server_name not in self.connections:
            return None

        conn = self.connections[server_name]

        # stdio 路径：request_id 递增移入锁内，防止竞态
        if conn["type"] == "stdio":
            stdio_lock = self._stdio_locks.get(server_name)
            if stdio_lock:
                with stdio_lock:
                    conn["request_id"] += 1
                    request = {
                        "jsonrpc": "2.0",
                        "id": conn["request_id"],
                        "method": method,
                        "params": params or {}
                    }
                    try:
                        return self._send_stdio_request(conn, request)
                    except Exception as e:
                        logger.error(f"Failed to send request to {server_name}: {e}")
                        return None
            else:
                # 无锁时直接发送（初始化阶段）
                conn["request_id"] += 1
                request = {
                    "jsonrpc": "2.0",
                    "id": conn["request_id"],
                    "method": method,
                    "params": params or {}
                }
                try:
                    return self._send_stdio_request(conn, request)
                except Exception as e:
                    logger.error(f"Failed to send request to {server_name}: {e}")
                    return None

        return None

    async def _send_request_async(self, server_name: str, method: str, params: Dict = None) -> Optional[Dict]:
        """发送 JSON-RPC 请求（async，SSE 路径使用）"""
        if server_name not in self.connections:
            return None

        conn = self.connections[server_name]
        conn["request_id"] += 1

        request = {
            "jsonrpc": "2.0",
            "id": conn["request_id"],
            "method": method,
            "params": params or {}
        }

        try:
            if conn["type"] == "sse":
                return await self._send_sse_request(conn, request)
        except Exception as e:
            logger.error(f"Failed to send async request to {server_name}: {e}")
            return None

        return None
    
    def _send_stdio_request(self, conn: Dict, request: Dict) -> Optional[Dict]:
        """发送 stdio 请求（同步，调用方应持有 per-connection 锁）"""
        import select
        process = conn["process"]

        # 发送请求
        request_line = json.dumps(request) + "\n"
        process.stdin.write(request_line)
        process.stdin.flush()

        # 读取响应（带超时，防止无限阻塞）
        if os.name == 'nt':
            # Windows 不支持 select 对 pipe，使用线程超时读取
            result_holder = [None]

            def _read():
                try:
                    result_holder[0] = process.stdout.readline()
                except Exception:
                    pass

            t = threading.Thread(target=_read, daemon=True)
            t.start()
            t.join(timeout=30.0)
            if t.is_alive():
                logger.warning("stdio readline timed out (Windows)")
                return None
            response_line = result_holder[0] or ""
        else:
            # Unix: 使用 select 带超时
            ready, _, _ = select.select([process.stdout], [], [], 30.0)
            if not ready:
                logger.warning("stdio readline timed out")
                return None
            response_line = process.stdout.readline()

        if not response_line:
            return None

        try:
            return json.loads(response_line)
        except json.JSONDecodeError:
            logger.warning("MCP stdio: non-JSON response: %s", response_line[:200])
            return None
    
    async def _send_sse_request(self, conn: Dict, request: Dict) -> Optional[Dict]:
        """发送 SSE 请求（async，使用 httpx.AsyncClient）"""
        client = conn["client"]

        response = await client.post(
            "/",
            json=request,
            headers={"Content-Type": "application/json"}
        )

        if response.status_code == 200:
            return response.json()

        return None
    
    def _initialize(self, server_name: str) -> bool:
        """初始化 MCP 连接"""
        response = self._send_request(server_name, "initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {},
                "resources": {}
            },
            "clientInfo": {
                "name": "claude-chat",
                "version": "1.0.0"
            }
        })
        
        if not response or "error" in response:
            return False
        
        # 发送 initialized 通知
        self._send_request(server_name, "notifications/initialized", {})
        
        return True
    
    def _discover_tools(self, server_name: str):
        """发现服务器提供的工具"""
        response = self._send_request(server_name, "tools/list", {})
        
        if not response or "result" not in response:
            return
        
        tools = response["result"].get("tools", [])
        
        with self._lock:
            for tool_data in tools:
                tool = McpTool(
                    name=tool_data["name"],
                    description=tool_data.get("description", ""),
                    input_schema=tool_data.get("inputSchema", {}),
                    server_name=server_name
                )
                self.tools[tool.name] = tool
                logger.info(f"Discovered MCP tool: {tool.name} from {server_name}")
    
    def _discover_resources(self, server_name: str):
        """发现服务器提供的资源"""
        response = self._send_request(server_name, "resources/list", {})
        
        if not response or "result" not in response:
            return
        
        resources = response["result"].get("resources", [])
        
        with self._lock:
            for res_data in resources:
                resource = McpResource(
                    uri=res_data["uri"],
                    name=res_data.get("name", ""),
                    description=res_data.get("description", ""),
                    mime_type=res_data.get("mimeType", "text/plain"),
                    server_name=server_name
                )
                self.resources[resource.uri] = resource
                logger.info(f"Discovered MCP resource: {resource.uri} from {server_name}")
    
    def execute_tool(self, tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行 MCP 工具

        Args:
            tool_name: 工具名称
            tool_input: 工具输入参数

        Returns:
            Dict with 'success' and 'result' or 'error'
        """
        if tool_name not in self.tools:
            return {
                "success": False,
                "error": f"Unknown MCP tool: {tool_name}"
            }

        tool = self.tools[tool_name]
        server_name = tool.server_name
        conn = self.connections.get(server_name)

        # SSE 路径需要 async：新建事件循环运行 async 版，兼容同步调用方
        if conn and conn.get("type") == "sse":
            try:
                loop = asyncio.new_event_loop()
                try:
                    return loop.run_until_complete(
                        self.execute_tool_async(tool_name, tool_input)
                    )
                finally:
                    loop.close()
            except Exception as e:
                logger.error(f"SSE tool execution error: {e}", exc_info=True)
                return {"success": False, "error": str(e)}

        # stdio 路径走同步
        response = self._send_request(server_name, "tools/call", {
            "name": tool_name,
            "arguments": tool_input
        })

        if not response:
            return {
                "success": False,
                "error": "No response from MCP server"
            }

        if "error" in response:
            return {
                "success": False,
                "error": response["error"].get("message", "Unknown error")
            }

        result = response.get("result", {})
        content = result.get("content", [])

        # 提取文本内容
        text_content = ""
        for item in content:
            if item.get("type") == "text":
                text_content += item.get("text", "")

        return {
            "success": True,
            "result": text_content or json.dumps(result)
        }
    
    def get_resource(self, uri: str) -> Dict[str, Any]:
        """
        获取 MCP 资源

        Args:
            uri: 资源 URI

        Returns:
            Dict with 'success' and 'content' or 'error'
        """
        if uri not in self.resources:
            return {
                "success": False,
                "error": f"Unknown MCP resource: {uri}"
            }

        resource = self.resources[uri]
        server_name = resource.server_name
        conn = self.connections.get(server_name)

        # SSE 路径需要 async：新建事件循环运行 async 版，兼容同步调用方
        if conn and conn.get("type") == "sse":
            try:
                loop = asyncio.new_event_loop()
                try:
                    return loop.run_until_complete(
                        self.get_resource_async(uri)
                    )
                finally:
                    loop.close()
            except Exception as e:
                logger.error(f"SSE resource read error: {e}", exc_info=True)
                return {"success": False, "error": str(e)}

        # stdio 路径走同步
        response = self._send_request(server_name, "resources/read", {
            "uri": uri
        })

        if not response:
            return {
                "success": False,
                "error": "No response from MCP server"
            }

        if "error" in response:
            return {
                "success": False,
                "error": response["error"].get("message", "Unknown error")
            }

        result = response.get("result", {})

        return {
            "success": True,
            "content": result.get("contents", []),
            "mime_type": resource.mime_type
        }

    # ---- async 版本（SSE 路径使用）----

    async def _initialize_async(self, server_name: str) -> bool:
        """初始化 MCP 连接（async）"""
        response = await self._send_request_async(server_name, "initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {},
                "resources": {}
            },
            "clientInfo": {
                "name": "claude-chat",
                "version": "1.0.0"
            }
        })

        if not response or "error" in response:
            return False

        # 发送 initialized 通知
        await self._send_request_async(server_name, "notifications/initialized", {})

        return True

    async def _discover_tools_async(self, server_name: str):
        """发现服务器提供的工具（async）"""
        response = await self._send_request_async(server_name, "tools/list", {})

        if not response or "result" not in response:
            return

        tools = response["result"].get("tools", [])

        with self._lock:
            for tool_data in tools:
                tool = McpTool(
                    name=tool_data["name"],
                    description=tool_data.get("description", ""),
                    input_schema=tool_data.get("inputSchema", {}),
                    server_name=server_name
                )
                self.tools[tool.name] = tool
                logger.info(f"Discovered MCP tool: {tool.name} from {server_name}")

    async def _discover_resources_async(self, server_name: str):
        """发现服务器提供的资源（async）"""
        response = await self._send_request_async(server_name, "resources/list", {})

        if not response or "result" not in response:
            return

        resources = response["result"].get("resources", [])

        with self._lock:
            for res_data in resources:
                resource = McpResource(
                    uri=res_data["uri"],
                    name=res_data.get("name", ""),
                    description=res_data.get("description", ""),
                    mime_type=res_data.get("mimeType", "text/plain"),
                    server_name=server_name
                )
                self.resources[resource.uri] = resource
                logger.info(f"Discovered MCP resource: {resource.uri} from {server_name}")

    async def execute_tool_async(self, tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行 MCP 工具（async 版本，供 async 上下文使用）

        Args:
            tool_name: 工具名称
            tool_input: 工具输入参数

        Returns:
            Dict with 'success' and 'result' or 'error'
        """
        if tool_name not in self.tools:
            return {
                "success": False,
                "error": f"Unknown MCP tool: {tool_name}"
            }

        tool = self.tools[tool_name]
        server_name = tool.server_name
        conn = self.connections.get(server_name)

        # 根据连接类型选择 sync 或 async 发送
        if conn and conn["type"] == "sse":
            response = await self._send_request_async(server_name, "tools/call", {
                "name": tool_name,
                "arguments": tool_input
            })
        else:
            # stdio 路径：在线程池中执行同步操作，避免阻塞事件循环
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self._send_request(server_name, "tools/call", {
                    "name": tool_name,
                    "arguments": tool_input
                })
            )

        if not response:
            return {
                "success": False,
                "error": "No response from MCP server"
            }

        if "error" in response:
            return {
                "success": False,
                "error": response["error"].get("message", "Unknown error")
            }

        result = response.get("result", {})
        content = result.get("content", [])

        # 提取文本内容
        text_content = ""
        for item in content:
            if item.get("type") == "text":
                text_content += item.get("text", "")

        return {
            "success": True,
            "result": text_content or json.dumps(result)
        }

    async def get_resource_async(self, uri: str) -> Dict[str, Any]:
        """
        获取 MCP 资源（async 版本）

        Args:
            uri: 资源 URI

        Returns:
            Dict with 'success' and 'content' or 'error'
        """
        if uri not in self.resources:
            return {
                "success": False,
                "error": f"Unknown MCP resource: {uri}"
            }

        resource = self.resources[uri]
        server_name = resource.server_name
        conn = self.connections.get(server_name)

        if conn and conn["type"] == "sse":
            response = await self._send_request_async(server_name, "resources/read", {"uri": uri})
        else:
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self._send_request(server_name, "resources/read", {"uri": uri})
            )

        if not response:
            return {
                "success": False,
                "error": "No response from MCP server"
            }

        if "error" in response:
            return {
                "success": False,
                "error": response["error"].get("message", "Unknown error")
            }

        result = response.get("result", {})

        return {
            "success": True,
            "content": result.get("contents", []),
            "mime_type": resource.mime_type
        }

    def get_tools_for_claude(self) -> List[Dict[str, Any]]:
        """获取所有 MCP 工具的 Claude 格式定义"""
        return [tool.to_claude_format() for tool in self.tools.values()]
    
    def list_tools(self) -> List[Dict[str, Any]]:
        """列出所有 MCP 工具"""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
                "server_name": tool.server_name
            }
            for tool in self.tools.values()
        ]
    
    def list_resources(self) -> List[Dict[str, Any]]:
        """列出所有 MCP 资源"""
        return [
            {
                "uri": res.uri,
                "name": res.name,
                "description": res.description,
                "mime_type": res.mime_type,
                "server_name": res.server_name
            }
            for res in self.resources.values()
        ]
    
    def list_connections(self) -> List[Dict[str, Any]]:
        """列出所有连接"""
        return [
            {
                "server_name": name,
                "type": conn["type"],
                "tools_count": len([t for t in self.tools.values() if t.server_name == name]),
                "resources_count": len([r for r in self.resources.values() if r.server_name == name])
            }
            for name, conn in self.connections.items()
        ]


# 全局 MCP 客户端实例
_client_instance: Optional[McpClient] = None


def get_mcp_client() -> McpClient:
    """获取 MCP 客户端单例"""
    global _client_instance
    
    if _client_instance is None:
        _client_instance = McpClient()
    
    return _client_instance


def reset_mcp_client():
    """重置 MCP 客户端（用于测试）"""
    global _client_instance
    
    if _client_instance:
        for server_name in list(_client_instance.connections.keys()):
            _client_instance.disconnect(server_name)
    
    _client_instance = None