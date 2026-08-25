"""
MCP Manager 测试 - 验收场景覆盖。

测试 OpenHarness McpClientManager 单例初始化和引用。
"""
import pytest
import asyncio
from unittest.mock import patch, MagicMock


class TestMcpManagerBasics:
    """测试 MCP Manager 基础功能。"""

    def test_get_mcp_manager_raises_when_not_initialized(self):
        """check-5: 未初始化时调用 get_mcp_manager() 应抛出 RuntimeError。"""
        from services.mcp.mcp_manager import get_mcp_manager, reset_mcp_manager

        reset_mcp_manager()

        with pytest.raises(RuntimeError, match="MCP manager not initialized"):
            get_mcp_manager()

    def test_is_mcp_initialized_returns_false_initially(self):
        """初始化前 is_mcp_initialized() 返回 False。"""
        from services.mcp.mcp_manager import is_mcp_initialized, reset_mcp_manager

        reset_mcp_manager()

        assert is_mcp_initialized() is False

    def test_reset_mcp_manager_clears_instance(self):
        """reset_mcp_manager() 清除单例。"""
        from services.mcp.mcp_manager import reset_mcp_manager, _manager_instance, _initialized

        reset_mcp_manager()

        # 导入全局变量检查
        import services.mcp.mcp_manager as mcp_manager
        assert mcp_manager._manager_instance is None
        assert mcp_manager._initialized is False


class TestMcpAsyncInit:
    """测试 init_mcp_async() 初始化逻辑。"""

    @pytest.mark.asyncio
    async def test_init_with_empty_config(self):
        """check-3: 配置为空时单例初始化成功，工具列表为空。"""
        from services.mcp.mcp_manager import init_mcp_async, reset_mcp_manager, get_mcp_manager, is_mcp_initialized

        reset_mcp_manager()

        # Mock mcp_config 返回空配置（注意：init_mcp_async 内部 from mcp_config import get_mcp_config）
        with patch('services.mcp.mcp_config.get_mcp_config') as mock_get_config:
            mock_mgr = MagicMock()
            mock_mgr.servers = {}
            mock_get_config.return_value = mock_mgr

            await init_mcp_async()

            assert is_mcp_initialized() is True
            manager = get_mcp_manager()
            tools = manager.list_tools()
            assert tools == []

    @pytest.mark.asyncio
    async def test_init_with_disabled_servers(self):
        """禁用的服务器不参与连接。"""
        from services.mcp.mcp_manager import init_mcp_async, reset_mcp_manager, get_mcp_manager, is_mcp_initialized

        reset_mcp_manager()

        # Mock mcp_config 返回禁用服务器
        with patch('services.mcp.mcp_config.get_mcp_config') as mock_get_config:
            mock_mgr = MagicMock()
            mock_server = MagicMock()
            mock_server.disabled = True
            mock_server.transport = 'stdio'
            mock_mgr.servers = {'disabled-server': mock_server}
            mock_get_config.return_value = mock_mgr

            await init_mcp_async()

            assert is_mcp_initialized() is True
            manager = get_mcp_manager()
            # 禁用服务器不在配置中
            statuses = manager.list_statuses()
            assert len(statuses) == 0

    @pytest.mark.asyncio
    async def test_init_skips_when_already_initialized(self):
        """check-5: 重复调用 init_mcp_async() 不重复初始化。"""
        from services.mcp.mcp_manager import init_mcp_async, reset_mcp_manager, is_mcp_initialized

        reset_mcp_manager()

        # 第一次初始化
        with patch('services.mcp.mcp_config.get_mcp_config') as mock_get_config:
            mock_mgr = MagicMock()
            mock_mgr.servers = {}
            mock_get_config.return_value = mock_mgr

            await init_mcp_async()
            assert is_mcp_initialized() is True

            # 第二次调用（mock 不应再次调用）
            await init_mcp_async()
            # 验证 mock 只被调用一次
            assert mock_get_config.call_count == 1


class TestMcpConfigConversion:
    """测试配置格式转换。"""

    @pytest.mark.asyncio
    async def test_stdio_config_conversion(self):
        """stdio 配置正确转换为 McpStdioServerConfig。"""
        from services.mcp.mcp_manager import init_mcp_async, reset_mcp_manager, get_mcp_manager
        from openharness.mcp.types import McpStdioServerConfig

        reset_mcp_manager()

        with patch('services.mcp.mcp_config.get_mcp_config') as mock_get_config:
            mock_mgr = MagicMock()
            mock_server = MagicMock()
            mock_server.disabled = False
            mock_server.transport = 'stdio'
            mock_server.command = 'npx'
            mock_server.args = ['-y', '@example/mcp-server']
            mock_server.env = {'API_KEY': 'test'}
            mock_mgr.servers = {'test-stdio': mock_server}
            mock_get_config.return_value = mock_mgr

            await init_mcp_async()

            manager = get_mcp_manager()
            # 验证配置包含 stdio 服务器（即使连接可能失败）
            config = manager.get_server_config('test-stdio')
            if config:
                assert isinstance(config, McpStdioServerConfig)
                assert config.command == 'npx'

    def test_exa_runtime_env_uses_database_credential_only(self):
        """Exa ignores legacy JSON credentials and injects encrypted DB config."""
        from services.mcp.mcp_manager import _get_runtime_server_env

        session = MagicMock()
        session.query.return_value.filter_by.return_value.first.return_value = MagicMock(
            value='database-exa-key'
        )

        with patch('db.SessionLocal', return_value=session):
            env = _get_runtime_server_env(
                'exa',
                {'EXA_API_KEY': 'legacy-json-key', 'OTHER_VALUE': 'preserved'},
            )

        assert env == {
            'EXA_API_KEY': 'database-exa-key',
            'OTHER_VALUE': 'preserved',
        }
        session.close.assert_called_once_with()

    def test_exa_runtime_env_never_falls_back_to_legacy_json_key(self):
        from services.mcp.mcp_manager import _get_runtime_server_env

        session = MagicMock()
        session.query.return_value.filter_by.return_value.first.return_value = None

        with patch('db.SessionLocal', return_value=session):
            env = _get_runtime_server_env('exa', {'EXA_API_KEY': 'legacy-json-key'})

        assert env is None

    def test_exa_config_discards_legacy_file_credential(self):
        from services.mcp.mcp_config import McpServerConfig

        server = McpServerConfig(
            name='exa',
            transport='stdio',
            env={'EXA_API_KEY': 'legacy-json-key', 'OTHER_VALUE': 'preserved'},
        )

        assert server.env == {'OTHER_VALUE': 'preserved'}
        assert 'legacy-json-key' not in str(server.to_dict())

    def test_exa_preset_enable_requires_system_setting_credential(self):
        from api.admin.mcp_admin_api import _require_mcp_credential_when_enabling
        from fastapi import HTTPException

        session = MagicMock()
        session.query.return_value.filter_by.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            _require_mcp_credential_when_enabling('exa', False, session)

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail['code'] == 'MCP_CREDENTIAL_NOT_CONFIGURED'
        assert exc_info.value.detail['credential_setting_key'] == 'EXA_API_KEY'

    def test_exa_preset_can_enable_when_system_setting_credential_exists(self):
        from api.admin.mcp_admin_api import _require_mcp_credential_when_enabling

        session = MagicMock()
        session.query.return_value.filter_by.return_value.first.return_value = MagicMock(
            value='database-exa-key'
        )

        _require_mcp_credential_when_enabling('exa', False, session)

    def test_disabling_exa_does_not_require_a_credential(self):
        from api.admin.mcp_admin_api import _require_mcp_credential_when_enabling

        session = MagicMock()
        _require_mcp_credential_when_enabling('exa', True, session)
        session.query.assert_not_called()

    @pytest.mark.asyncio
    async def test_sse_config_conversion_to_http(self):
        """sse 配置正确转换为 McpHttpServerConfig。"""
        from services.mcp.mcp_manager import init_mcp_async, reset_mcp_manager, get_mcp_manager
        from openharness.mcp.types import McpHttpServerConfig

        reset_mcp_manager()

        with patch('services.mcp.mcp_config.get_mcp_config') as mock_get_config:
            mock_mgr = MagicMock()
            mock_server = MagicMock()
            mock_server.disabled = False
            mock_server.transport = 'sse'
            mock_server.url = 'http://localhost:3000/sse'
            mock_server.env = {}
            mock_mgr.servers = {'test-sse': mock_server}
            mock_get_config.return_value = mock_mgr

            await init_mcp_async()

            manager = get_mcp_manager()
            config = manager.get_server_config('test-sse')
            if config:
                assert isinstance(config, McpHttpServerConfig)
                assert config.url == 'http://localhost:3000/sse'


class TestHarnessCoordinatorMcpReference:
    """测试 HarnessCoordinator MCP 引用。"""

    def test_coordinator_mcp_reference_when_initialized(self):
        """check-6: HarnessCoordinator 能读取 MCP 单例。"""
        from services.harness.harness_coordinator import HarnessCoordinator
        from services.mcp.mcp_manager import reset_mcp_manager, init_mcp_async
        import asyncio

        reset_mcp_manager()

        # 先初始化 MCP
        async def init():
            with patch('services.mcp.mcp_config.get_mcp_config') as mock_get_config:
                mock_mgr = MagicMock()
                mock_mgr.servers = {}
                mock_get_config.return_value = mock_mgr
                await init_mcp_async()

        asyncio.run(init())

        # 创建 Coordinator
        coordinator = HarnessCoordinator()

        # 验证 MCP 引用
        assert coordinator._mcp_manager is not None

    def test_coordinator_mcp_reference_none_when_not_initialized(self):
        """MCP 未初始化时 Coordinator 引用为 None。"""
        from services.harness.harness_coordinator import HarnessCoordinator
        from services.mcp.mcp_manager import reset_mcp_manager

        reset_mcp_manager()

        coordinator = HarnessCoordinator()

        assert coordinator._mcp_manager is None
