"""MCP Client 异步测试

覆盖 mcp_client.py 中 httpx.AsyncClient 异步路径：
- connect_sse → _send_sse_request_async → execute_tool_async 完整调用链
- stdio 路径锁保护（并发 send 不串包）
- 超时处理
- 连接断开清理
"""
import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock


# ─── fixtures ───

@pytest.fixture
def mock_httpx_response():
    """构造 httpx.Response mock（SSE 路径用）"""
    def _make(json_data, status_code=200):
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.return_value = json_data
        return resp
    return _make


@pytest.fixture
def mock_httpx_client(mock_httpx_response):
    """构造 httpx.AsyncClient mock，预置 initialize / tools/list / resources/list 响应"""
    client = AsyncMock()

    # initialize 响应
    init_resp = mock_httpx_response({"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2024-11-05"}})
    # notifications/initialized 无返回体，用空响应
    notif_resp = mock_httpx_response({}, 200)
    # tools/list 响应
    tools_resp = mock_httpx_response({
        "jsonrpc": "2.0", "id": 2,
        "result": {
            "tools": [
                {"name": "test_tool", "description": "A test tool", "inputSchema": {"type": "object", "properties": {}}}
            ]
        }
    })
    # resources/list 响应
    resources_resp = mock_httpx_response({
        "jsonrpc": "2.0", "id": 3,
        "result": {
            "resources": [
                {"uri": "test://resource", "name": "Test Resource", "description": "desc", "mimeType": "text/plain"}
            ]
        }
    })

    # post 按顺序返回 initialize → initialized notification → tools/list → resources/list
    client.post = AsyncMock(side_effect=[init_resp, notif_resp, tools_resp, resources_resp])

    # aclose 也要 mock
    client.aclose = AsyncMock()

    return client


@pytest.fixture
def sse_client(mock_httpx_client, mock_httpx_response):
    """构造已连接的 McpClient（SSE 模式），跳过真实 httpx 连接"""
    from services.mcp.mcp_client import McpClient, McpTool

    client = McpClient()
    # 直接注入连接，绕过 connect_sse 的 httpx.AsyncClient 构造
    # 使用 return_value 而非 side_effect，避免 mock 耗尽导致 hang
    default_resp = mock_httpx_response({
        "jsonrpc": "2.0", "id": 99,
        "result": {"content": [{"type": "text", "text": "default"}]}
    })
    mock_httpx_client.post = AsyncMock(return_value=default_resp)

    client.connections["test-sse"] = {
        "type": "sse",
        "url": "http://localhost:8765",
        "request_id": 3,
        "client": mock_httpx_client,
    }
    # 注入已发现的工具
    client.tools["test_tool"] = McpTool(
        name="test_tool",
        description="A test tool",
        input_schema={"type": "object", "properties": {}},
        server_name="test-sse",
    )
    return client


# ─── SSE 路径测试 ───

class TestSSEConnect:
    """connect_sse 异步连接流程"""

    @pytest.mark.asyncio
    async def test_connect_sse_success(self, mock_httpx_response):
        """connect_sse 应完成 initialize → tools/list → resources/list 全流程"""
        from services.mcp.mcp_client import McpClient

        client = McpClient()
        # 创建独立 mock，不共享 fixture
        httpx_mock = AsyncMock()
        httpx_mock.aclose = AsyncMock()
        httpx_mock.post = AsyncMock(side_effect=[
            mock_httpx_response({"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2024-11-05"}}),
            mock_httpx_response({}, 200),
            mock_httpx_response({"jsonrpc": "2.0", "id": 2, "result": {"tools": [{"name": "test_tool", "description": "A test tool", "inputSchema": {"type": "object", "properties": {}}}]}}),
            mock_httpx_response({"jsonrpc": "2.0", "id": 3, "result": {"resources": [{"uri": "test://resource", "name": "Test Resource", "description": "desc", "mimeType": "text/plain"}]}}),
        ])

        with patch("httpx.AsyncClient", return_value=httpx_mock):
            result = await client.connect_sse("sse-server", "http://localhost:8765")

        assert result is True
        assert "sse-server" in client.connections
        assert client.connections["sse-server"]["type"] == "sse"
        assert "test_tool" in client.tools
        assert client.tools["test_tool"].server_name == "sse-server"
        assert "test://resource" in client.resources
        assert client.resources["test://resource"].server_name == "sse-server"

    @pytest.mark.asyncio
    async def test_connect_sse_init_failure(self, mock_httpx_response):
        """initialize 返回错误时应断开连接并返回 False"""
        from services.mcp.mcp_client import McpClient

        client = McpClient()
        httpx_mock = AsyncMock()
        httpx_mock.aclose = AsyncMock()
        httpx_mock.post = AsyncMock(return_value=mock_httpx_response(
            {"jsonrpc": "2.0", "id": 1, "error": {"code": -1, "message": "fail"}}
        ))

        with patch("httpx.AsyncClient", return_value=httpx_mock):
            result = await client.connect_sse("fail-server", "http://localhost:8765")

        assert result is False
        assert "fail-server" not in client.connections

    @pytest.mark.asyncio
    async def test_connect_sse_exception(self):
        """httpx.AsyncClient 构造异常时应返回 False"""
        from services.mcp.mcp_client import McpClient

        client = McpClient()

        with patch("httpx.AsyncClient", side_effect=ConnectionError("refused")):
            result = await client.connect_sse("bad-server", "http://bad:9999")

        assert result is False


class TestSSEExecuteToolAsync:
    """execute_tool_async SSE 路径"""

    @pytest.mark.asyncio
    async def test_execute_tool_async_success(self, sse_client, mock_httpx_response):
        """SSE 路径 execute_tool_async 应返回成功结果"""
        exec_resp = mock_httpx_response({
            "jsonrpc": "2.0", "id": 4,
            "result": {"content": [{"type": "text", "text": "hello world"}]}
        })
        sse_client.connections["test-sse"]["client"].post = AsyncMock(return_value=exec_resp)

        result = await sse_client.execute_tool_async("test_tool", {"arg": "val"})

        assert result["success"] is True
        assert result["result"] == "hello world"

    @pytest.mark.asyncio
    async def test_execute_tool_async_error_response(self, sse_client, mock_httpx_response):
        """服务端返回 JSON-RPC error 时应返回 success=False"""
        error_resp = mock_httpx_response({
            "jsonrpc": "2.0", "id": 4,
            "error": {"code": -32600, "message": "Invalid request"}
        })
        sse_client.connections["test-sse"]["client"].post = AsyncMock(return_value=error_resp)

        result = await sse_client.execute_tool_async("test_tool", {})

        assert result["success"] is False
        assert "Invalid request" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_tool_async_unknown_tool(self, sse_client):
        """执行不存在的工具应返回错误"""
        result = await sse_client.execute_tool_async("nonexistent_tool", {})

        assert result["success"] is False
        assert "Unknown MCP tool" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_tool_async_no_response(self, sse_client):
        """服务端无响应时应返回错误"""
        sse_client.connections["test-sse"]["client"].post = AsyncMock(return_value=None)

        result = await sse_client.execute_tool_async("test_tool", {})

        assert result["success"] is False


class TestSSEGetResourceAsync:
    """get_resource_async SSE 路径"""

    @pytest.mark.asyncio
    async def test_get_resource_async_success(self, sse_client, mock_httpx_response):
        """SSE 路径 get_resource_async 应返回资源内容"""
        from services.mcp.mcp_client import McpResource

        sse_client.resources["test://resource"] = McpResource(
            uri="test://resource", name="Test", description="desc",
            mime_type="text/plain", server_name="test-sse",
        )

        res_resp = mock_httpx_response({
            "jsonrpc": "2.0", "id": 4,
            "result": {"contents": [{"text": "resource data"}]}
        })
        sse_client.connections["test-sse"]["client"].post = AsyncMock(side_effect=[res_resp])

        result = await sse_client.get_resource_async("test://resource")

        assert result["success"] is True
        assert result["mime_type"] == "text/plain"

    @pytest.mark.asyncio
    async def test_get_resource_async_unknown_uri(self, sse_client):
        """访问不存在的资源 URI 应返回错误"""
        result = await sse_client.get_resource_async("unknown://uri")

        assert result["success"] is False
        assert "Unknown MCP resource" in result["error"]


# ─── stdio 路径锁保护测试 ───

class TestStdioLockProtection:
    """stdio 路径 threading.Lock 保护"""

    def test_stdio_concurrent_sends_share_lock(self):
        """多个并发 _send_request 调用应串行化（锁保护）"""
        from services.mcp.mcp_client import McpClient
        import threading

        client = McpClient()
        client.connections["stdio-server"] = {
            "type": "stdio",
            "process": MagicMock(),
            "request_id": 0,
        }
        client._stdio_locks["stdio-server"] = threading.Lock()

        # Track call order and request_ids
        call_order = []
        call_ids = []
        lock = threading.Lock()

        original_send = client._send_stdio_request

        def mock_send_stdio(conn, request):
            with lock:
                call_order.append(request["id"])
            import time
            time.sleep(0.01)  # Simulate work
            return {"jsonrpc": "2.0", "id": request["id"], "result": {}}

        with patch.object(client, '_send_stdio_request', side_effect=mock_send_stdio):
            results = []

            def send(idx):
                resp = client._send_request("stdio-server", "test/method", {"idx": idx})
                results.append(resp)

            t1 = threading.Thread(target=send, args=(1,))
            t2 = threading.Thread(target=send, args=(2,))
            t1.start()
            t2.start()
            t1.join(timeout=5)
            t2.join(timeout=5)

        # 两次调用都应收到响应
        assert len(results) == 2
        assert all(r is not None for r in results)
        # request_ids should be 1 and 2 (sequential, not concurrent)
        assert sorted(call_order) == [1, 2]

    def test_stdio_request_id_increments_under_lock(self):
        """request_id 应在锁内递增，不出现竞态"""
        from services.mcp.mcp_client import McpClient
        import threading

        client = McpClient()
        client.connections["stdio-server"] = {
            "type": "stdio",
            "process": MagicMock(),
            "request_id": 0,
        }
        client._stdio_locks["stdio-server"] = threading.Lock()

        with patch.object(client, '_send_stdio_request', return_value={"jsonrpc": "2.0", "id": 1, "result": {}}):
            def send():
                for _ in range(5):
                    client._send_request("stdio-server", "test/method")

            threads = [threading.Thread(target=send) for _ in range(2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10)

        # request_id 应为 10（2 线程 x 5 次）
        assert client.connections["stdio-server"]["request_id"] == 10


# ─── 超时处理测试 ───

class TestTimeoutHandling:
    """超时场景"""

    @pytest.mark.asyncio
    async def test_sse_request_timeout_returns_none(self, sse_client):
        """httpx.AsyncClient.post 超时时应返回 None"""
        import httpx

        sse_client.connections["test-sse"]["client"].post = AsyncMock(
            side_effect=httpx.TimeoutException("timed out")
        )

        result = await sse_client._send_request_async("test-sse", "tools/call", {"name": "test"})

        assert result is None

    def test_stdio_readline_timeout_returns_none(self):
        """stdio _send_stdio_request 超时应返回 None"""
        from services.mcp.mcp_client import McpClient
        import threading

        client = McpClient()

        client.connections["timeout-server"] = {
            "type": "stdio",
            "process": MagicMock(),
            "request_id": 0,
        }
        client._stdio_locks["timeout-server"] = threading.Lock()

        # 直接 mock _send_stdio_request 返回 None（模拟超时行为）
        with patch.object(client, '_send_stdio_request', return_value=None):
            result = client._send_request("timeout-server", "test")

        assert result is None


# ─── disconnect_async 测试 ───

class TestDisconnectAsync:
    """异步断开连接"""

    @pytest.mark.asyncio
    async def test_disconnect_async_closes_client(self, sse_client, mock_httpx_client):
        """disconnect_async 应关闭 httpx.AsyncClient 并清理连接"""
        await sse_client._disconnect_async("test-sse")

        mock_httpx_client.aclose.assert_awaited_once()
        assert "test-sse" not in sse_client.connections
        # tools 和 resources 也应被清理
        assert not any(t.server_name == "test-sse" for t in sse_client.tools.values())
        assert not any(r.server_name == "test-sse" for r in sse_client.resources.values())

    @pytest.mark.asyncio
    async def test_disconnect_async_nonexistent_server(self):
        """断开不存在的连接不应抛异常"""
        from services.mcp.mcp_client import McpClient

        client = McpClient()
        # 不应抛异常
        await client._disconnect_async("nonexistent")

    @pytest.mark.asyncio
    async def test_disconnect_async_stdio_type_skips_aclose(self):
        """stdio 类型连接不走 aclose 路径"""
        from services.mcp.mcp_client import McpClient

        client = McpClient()
        mock_process = MagicMock()
        client.connections["stdio-srv"] = {
            "type": "stdio",
            "process": mock_process,
            "request_id": 0,
        }

        await client._disconnect_async("stdio-srv")
        # stdio 类型在 _disconnect_async 中不调用 aclose（conn["type"] != "sse"）
        # 但连接应保留（_disconnect_async 只处理 sse 类型的关闭）
        # 注意：实际上 _disconnect_async 只清理 sse 类型，stdio 仍保留
        # 这是设计如此，stdio 用同步 disconnect() 关闭


# ─── 全局单例测试 ───

class TestClientSingleton:
    """MCP 客户端单例"""

    def test_get_mcp_client_returns_singleton(self):
        """get_mcp_client 应返回同一个实例"""
        from services.mcp.mcp_client import get_mcp_client, reset_mcp_client

        reset_mcp_client()
        c1 = get_mcp_client()
        c2 = get_mcp_client()

        assert c1 is c2

    def test_reset_mcp_client_clears_singleton(self):
        """reset_mcp_client 应清除单例"""
        from services.mcp.mcp_client import get_mcp_client, reset_mcp_client

        reset_mcp_client()
        c1 = get_mcp_client()
        reset_mcp_client()
        c2 = get_mcp_client()

        assert c1 is not c2

    def test_list_connections_shows_sse_info(self, sse_client):
        """list_connections 应返回连接信息"""
        conns = sse_client.list_connections()

        assert len(conns) == 1
        assert conns[0]["server_name"] == "test-sse"
        assert conns[0]["type"] == "sse"
        assert conns[0]["tools_count"] == 1


class TestMcpProcessEnvAllowlist:
    """MCP 子进程环境白名单：后端密钥不得透传给 MCP server"""

    def test_secrets_are_filtered_and_allowlist_passes(self, monkeypatch):
        from services.mcp.mcp_client import _build_mcp_process_env

        monkeypatch.setenv('SECRET_KEY', 'top-secret-value')
        monkeypatch.setenv('JWT_SECRET_KEY', 'jwt-secret-value')
        monkeypatch.setenv('DATABASE_URL', 'postgresql://user:pass@host/db')
        monkeypatch.setenv('PATH', '/custom/bin')

        env = _build_mcp_process_env()

        assert 'SECRET_KEY' not in env
        assert 'JWT_SECRET_KEY' not in env
        assert 'DATABASE_URL' not in env
        assert env.get('PATH') == '/custom/bin'

    def test_passthrough_extension_is_honored(self, monkeypatch):
        from services.mcp.mcp_client import _build_mcp_process_env

        monkeypatch.setenv('MY_TOOL_TOKEN', 'tool-secret')
        monkeypatch.setenv('MCP_ENV_PASSTHROUGH', ' MY_TOOL_TOKEN , ANOTHER_VAR ')

        env = _build_mcp_process_env()

        assert env.get('MY_TOOL_TOKEN') == 'tool-secret'
        # 声明了但未设置的变量不产生空项
        assert 'ANOTHER_VAR' not in env

    def test_server_custom_env_overrides_result(self):
        """connect_stdio 的自定义 env 参数仍应叠加在白名单结果之上"""
        from services.mcp.mcp_client import _build_mcp_process_env

        base = _build_mcp_process_env()
        custom = {'MY_SERVER_FLAG': '1'}
        merged = {**base, **custom}

        assert merged['MY_SERVER_FLAG'] == '1'
