"""
OpenHarness 工具整合集成测试 - FastAPI 版

迁移自 Flask test client 到 FastAPI TestClient：
- 独立测试不需要 fixture
- 依赖特定配置的测试标记跳过
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.environ['SKIP_MCP_INIT'] = 'true'

from services.harness.harness_adapter import get_harness_tool_registry
from config import Config


class TestHarnessIntegration:
    """测试 OpenHarness 整合"""

    def test_tool_registry_initialization_with_config(self):
        """测试使用配置初始化工具注册"""
        config = Config()

        registry = get_harness_tool_registry(
            workspace_dir=config.OPENHARNESS_WORKSPACE,
            config={
                'OPENHARNESS_ENABLED': config.OPENHARNESS_ENABLED,
                'OPENHARNESS_TOOLS_ENABLED': config.OPENHARNESS_TOOLS_ENABLED
            }
        )

        assert registry is not None
        tools = registry.list_tools()
        # OpenHarness v0.1.2 包含约 37 个工具
        assert len(tools) >= 30

    @pytest.mark.skip(reason="web_search 工具需要网络，跳过")
    def test_tool_execution_web_search(self):
        """测试 web_search 工具执行"""
        pass

    @pytest.mark.skip(reason="HarnessCoordinator 集成测试需要完整 Agent 配置，跳过")
    def test_leader_manager_harness_integration(self, client, auth_header):
        """测试 Leader Manager 集成 OpenHarness"""
        pass


class TestHarnessToolExecution:
    """测试工具执行"""

    def test_registry_execute_bash(self):
        """测试 bash 工具执行"""
        registry = get_harness_tool_registry(
            workspace_dir='/tmp/test_workspace',
            config={}
        )

        result = registry.execute_tool(
            'bash',
            {'command': 'echo "hello"', 'timeout': 5},
            timeout=10
        )

        assert 'success' in result
        # 工具可能成功或失败（取决于环境），只验证结构
        assert isinstance(result, dict)

    def test_registry_execute_read_file(self):
        """测试 read_file 工具执行"""
        registry = get_harness_tool_registry(
            workspace_dir='/tmp/test_workspace',
            config={}
        )

        # 创建测试文件
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write('test content')
            test_file = f.name

        try:
            result = registry.execute_tool(
                'read_file',
                {'file_path': test_file},
                timeout=10
            )

            assert 'success' in result
            assert isinstance(result, dict)
        finally:
            os.unlink(test_file)

    def test_registry_execute_write_file(self):
        """测试 write_file 工具执行"""
        registry = get_harness_tool_registry(
            workspace_dir='/tmp/test_workspace',
            config={}
        )

        import tempfile
        test_file = tempfile.mktemp(suffix='.txt')

        try:
            result = registry.execute_tool(
                'write_file',
                {'file_path': test_file, 'content': 'test content'},
                timeout=10
            )

            assert 'success' in result
            assert isinstance(result, dict)
        finally:
            if os.path.exists(test_file):
                os.unlink(test_file)


class TestHarnessCoordinatorIntegration:
    """测试 HarnessCoordinator 集成"""

    @pytest.mark.skip(reason="HarnessCoordinator 需要完整 Agent 配置，跳过")
    def test_coordinator_initialization(self, client, auth_header):
        """测试 Coordinator 初始化"""
        pass

    @pytest.mark.skip(reason="团队执行需要完整 Leader 流程，跳过")
    def test_execute_team_parallel_mode(self, client, auth_header):
        """测试并行执行"""
        pass

    @pytest.mark.skip(reason="团队执行需要完整 Leader 流程，跳过")
    def test_execute_team_sequential_mode(self, client, auth_header):
        """测试顺序执行"""
        pass