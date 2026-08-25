"""测试 OpenHarness 适配器（独立测试，不依赖 conftest）"""
import sys
import os
import pytest

# 添加 backend 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestHarnessToolRegistry:
    """测试工具注册适配器"""

    def test_registry_initialization(self):
        """测试工具注册初始化"""
        from services.harness.harness_adapter import HarnessToolRegistry

        registry = HarnessToolRegistry(workspace_dir='/tmp/test_workspace')

        # 验证工具数量（37 个可用工具，留余量）
        tools = registry.list_tools()
        assert len(tools) >= 35, f"Expected >= 35 tools, got {len(tools)}"

        # 验证工具结构
        tool = tools[0]
        assert 'name' in tool
        assert 'description' in tool
        assert 'input_schema' in tool

    def test_list_tools_returns_valid_structure(self):
        """测试工具列表返回正确结构"""
        from services.harness.harness_adapter import HarnessToolRegistry

        registry = HarnessToolRegistry(workspace_dir='/tmp/test_workspace')
        tools = registry.list_tools()

        for tool in tools:
            assert isinstance(tool, dict)
            assert 'name' in tool
            assert 'description' in tool
            assert 'input_schema' in tool

    def test_registry_has_core_tools(self):
        """测试注册了核心工具"""
        from services.harness.harness_adapter import HarnessToolRegistry

        registry = HarnessToolRegistry(workspace_dir='/tmp/test_workspace')
        tools = registry.list_tools()
        tool_names = {tool['name'] for tool in tools}

        # 验证核心工具存在
        core_tools = {'bash', 'read_file', 'write_file', 'edit_file', 'grep', 'glob', 'agent'}
        assert core_tools.issubset(tool_names), f"Missing tools: {core_tools - tool_names}"

    def test_get_tool_schema(self):
        """测试获取单个工具 schema"""
        from services.harness.harness_adapter import HarnessToolRegistry

        registry = HarnessToolRegistry(workspace_dir='/tmp/test_workspace')

        # 获取 bash 工具 schema
        schema = registry.get_tool_schema('bash')
        assert schema is not None
        assert schema['name'] == 'bash'
        assert 'description' in schema
        assert 'input_schema' in schema

    def test_get_nonexistent_tool_schema(self):
        """测试获取不存在的工具 schema"""
        from services.harness.harness_adapter import HarnessToolRegistry

        registry = HarnessToolRegistry(workspace_dir='/tmp/test_workspace')

        schema = registry.get_tool_schema('nonexistent_tool')
        assert schema is None

    def test_execute_tool_success(self):
        """测试工具正常执行"""
        import tempfile
        from services.harness.harness_adapter import HarnessToolRegistry

        with tempfile.TemporaryDirectory() as workspace:
            registry = HarnessToolRegistry(workspace_dir=workspace)

            # 执行 bash 工具
            result = registry.execute_tool('bash', {
                'command': 'echo "test"',
                'timeout_seconds': 10
            })

            assert result['success'] is True
            assert 'test' in result['result']
            assert result['error'] is None
            assert 'metadata' in result

    def test_execute_tool_not_found(self):
        """测试执行不存在的工具"""
        from services.harness.harness_adapter import HarnessToolRegistry

        registry = HarnessToolRegistry(workspace_dir='/tmp/test_workspace')

        result = registry.execute_tool('nonexistent_tool', {})

        assert result['success'] is False
        assert 'not found' in result['error']

    def test_execute_tool_invalid_params(self):
        """测试工具执行参数错误"""
        from services.harness.harness_adapter import HarnessToolRegistry

        registry = HarnessToolRegistry(workspace_dir='/tmp/test_workspace')

        # bash 工具缺少必需的 command 参数
        result = registry.execute_tool('bash', {})

        assert result['success'] is False
        assert 'error' in result
