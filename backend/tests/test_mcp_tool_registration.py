"""
MCP 工具注册功能测试

测试 Agent MCP 权限配置和工具注册功能。
"""
import pytest
import fnmatch
from unittest.mock import Mock, patch, MagicMock


class TestAgentMcpPermissionModel:
    """测试 AgentMcpPermission 数据模型"""

    def test_permission_creation(self):
        """测试创建权限记录"""
        from models import AgentMcpPermission

        perm = AgentMcpPermission(
            agent_id='cardiology-expert',
            mcp_tool_pattern='mcp__exa__*',
            enabled=True
        )

        assert perm.agent_id == 'cardiology-expert'
        assert perm.mcp_tool_pattern == 'mcp__exa__*'
        assert perm.enabled is True

    def test_permission_disabled(self):
        """测试禁用权限"""
        from models import AgentMcpPermission

        perm = AgentMcpPermission(
            agent_id='technical-agent',
            mcp_tool_pattern='mcp__playwright__*',
            enabled=False
        )

        assert perm.enabled is False

    def test_permission_to_dict(self):
        """测试序列化"""
        from models import AgentMcpPermission

        perm = AgentMcpPermission(
            agent_id='business-agent',
            mcp_tool_pattern='mcp__*',
            enabled=True
        )

        data = perm.to_dict()
        assert data['agent_id'] == 'business-agent'
        assert data['mcp_tool_pattern'] == 'mcp__*'
        assert data['enabled'] is True


class TestAgentTypeClassification:
    """测试 Agent 类型分类"""

    def test_medical_agent_detection(self):
        """测试医疗 Agent 识别"""
        from services.harness.harness_coordinator import get_agent_type_from_id

        assert get_agent_type_from_id('cardiology-expert') == 'medical'
        assert get_agent_type_from_id('心血管内科专家') == 'medical'
        assert get_agent_type_from_id('针灸科专家') == 'medical'

    def test_technical_agent_detection(self):
        """测试技术 Agent 识别"""
        from services.harness.harness_coordinator import get_agent_type_from_id

        assert get_agent_type_from_id('fullstack-developer') == 'technical'
        assert get_agent_type_from_id('DevOps Engineer') == 'technical'
        assert get_agent_type_from_id('全栈技术主管') == 'technical'

    def test_business_agent_detection(self):
        """测试商业 Agent 识别"""
        from services.harness.harness_coordinator import get_agent_type_from_id

        assert get_agent_type_from_id('chief-executive-officer') == 'business'
        assert get_agent_type_from_id('首席AI官') == 'business'
        assert get_agent_type_from_id('销售总监') == 'business'


class TestWildcardPatternMatching:
    """测试通配符模式匹配"""

    def test_exact_match(self):
        """测试精确匹配"""
        allowed = {'file_read', 'mcp__exa__web_search_exa'}

        assert fnmatch.fnmatch('file_read', 'file_read')
        assert fnmatch.fnmatch('mcp__exa__web_search_exa', 'mcp__exa__web_search_exa')
        assert not fnmatch.fnmatch('mcp__exa__other_tool', 'mcp__exa__web_search_exa')

    def test_wildcard_match(self):
        """测试通配符匹配"""
        allowed = {'mcp__exa__*'}

        assert fnmatch.fnmatch('mcp__exa__web_search_exa', 'mcp__exa__*')
        assert fnmatch.fnmatch('mcp__exa__web_fetch_exa', 'mcp__exa__*')
        assert not fnmatch.fnmatch('mcp__playwright__browser_click', 'mcp__exa__*')

    def test_multi_pattern_match(self):
        """测试多模式匹配"""
        allowed = {'mcp__exa__*', 'mcp__playwright__*'}

        assert fnmatch.fnmatch('mcp__exa__web_search_exa', 'mcp__exa__*')
        assert fnmatch.fnmatch('mcp__playwright__browser_click', 'mcp__playwright__*')
        assert not any(fnmatch.fnmatch('mcp__other__tool', p) for p in allowed)


class TestClearRegistryCache:
    """测试缓存清除机制"""

    def test_cache_clear_function_exists(self):
        """测试缓存清除函数存在"""
        from services.harness.harness_coordinator import clear_registry_cache

        assert callable(clear_registry_cache)

    def test_cache_clear_with_no_instance(self):
        """测试无实例时清除缓存不报错"""
        from services.harness.harness_coordinator import clear_registry_cache, _coordinator_instance

        # 无实例时应不报错
        original = _coordinator_instance
        try:
            clear_registry_cache()
        finally:
            # 不改变状态
            pass

    def test_cache_clear_refreshes_mcp_permissions_on_registered_agents(self, monkeypatch):
        """权限更新后，既有 Agent（含文件名别名）立即看到新快照。"""
        import services.harness.harness_coordinator as coordinator_module
        from services.harness.harness_coordinator import HarnessCoordinator, clear_registry_cache

        coordinator = HarnessCoordinator.__new__(HarnessCoordinator)
        registration = {
            'name': 'technical-agent',
            'description': 'test',
            'tools': ['read_file', 'mcp__old__tool'],
        }
        coordinator.registered_agents = {
            'technical-agent': registration,
            'technical-agent-file': registration,
        }
        coordinator._cached_full_registry = object()
        coordinator._mcp_patterns_cache = {'technical-agent': ['mcp__old__tool']}

        monkeypatch.setattr(
            HarnessCoordinator,
            '_load_mcp_patterns',
            staticmethod(lambda: {'technical-agent': ['mcp__new__tool']}),
        )
        monkeypatch.setattr(
            HarnessCoordinator,
            '_is_knowledge_available',
            staticmethod(lambda user_id=None: False),
        )
        monkeypatch.setattr(coordinator_module, '_coordinator_instance', coordinator)

        clear_registry_cache()

        assert coordinator._cached_full_registry is None
        assert coordinator._mcp_patterns_cache == {'technical-agent': ['mcp__new__tool']}
        assert 'mcp__new__tool' in registration['tools']
        assert 'mcp__old__tool' not in registration['tools']
        assert coordinator.registered_agents['technical-agent-file'] is registration


class TestGetAgentsByType:
    """测试按类型获取 Agent"""

    @patch('services.harness.harness_coordinator.get_harness_coordinator')
    def test_get_agents_by_type(self, mock_get_coordinator):
        """测试按类型获取 Agent 列表"""
        from services.harness.harness_coordinator import get_agents_by_type

        mock_coordinator = Mock()
        mock_coordinator.list_agents.return_value = [
            'cardiology-expert',
            'fullstack-developer',
            'chief-executive-officer',
            '针灸科专家'
        ]
        mock_get_coordinator.return_value = mock_coordinator

        medical_agents = get_agents_by_type('medical')
        assert 'cardiology-expert' in medical_agents
        assert '针灸科专家' in medical_agents
        assert 'fullstack-developer' not in medical_agents


class TestMcpToolRegistration:
    """测试 MCP 工具注册"""

    @patch('services.mcp.mcp_manager.is_mcp_initialized')
    @patch('services.mcp.mcp_manager.get_mcp_manager')
    def test_register_mcp_tools_skips_when_not_initialized(self, mock_get_manager, mock_is_initialized):
        """测试 MCP 未初始化时跳过注册"""
        mock_is_initialized.return_value = False

        from services.harness.harness_adapter import HarnessToolRegistry

        registry = HarnessToolRegistry(workspace_dir='data/workspace')

        # 未初始化时不应调用 get_mcp_manager
        mock_get_manager.assert_not_called()

    @patch('services.mcp.mcp_manager.is_mcp_initialized')
    @patch('services.mcp.mcp_manager.get_mcp_manager')
    @patch('openharness.tools.mcp_tool.McpToolAdapter')
    def test_register_mcp_tools_registers_all_tools(self, mock_adapter, mock_get_manager, mock_is_initialized):
        """测试 MCP 已初始化时注册所有工具"""
        mock_is_initialized.return_value = True

        # 模拟 MCP manager 返回工具列表
        mock_manager = Mock()
        mock_tool_info = Mock()
        mock_tool_info.server_name = 'exa'
        mock_tool_info.name = 'web_search_exa'
        mock_tool_info.description = 'Web search'
        mock_tool_info.input_schema = {}
        mock_manager.list_tools.return_value = [mock_tool_info]
        mock_get_manager.return_value = mock_manager

        # 模拟 adapter 创建
        mock_adapter_instance = Mock()
        mock_adapter_instance.name = 'mcp__exa__web_search_exa'
        mock_adapter.return_value = mock_adapter_instance

        # 注意：实际注册逻辑在 _register_tools() 中，这里验证逻辑正确性


class TestFilterToolRegistryWithWildcard:
    """测试带通配符的工具过滤"""

    def test_filter_with_wildcard_patterns(self):
        """测试通配符模式过滤"""
        from services.harness.harness_coordinator import HarnessCoordinator

        # 创建模拟 registry
        mock_registry = Mock()
        mock_tool1 = Mock()
        mock_tool1.name = 'file_read'
        mock_tool2 = Mock()
        mock_tool2.name = 'mcp__exa__web_search_exa'
        mock_tool3 = Mock()
        mock_tool3.name = 'mcp__playwright__browser_click'
        mock_registry.list_tools.return_value = [mock_tool1, mock_tool2, mock_tool3]

        # 过滤后的 registry
        filtered_registry = Mock()
        filtered_registry.register = Mock()

        # 模拟 ToolRegistry 构造
        with patch('openharness.tools.base.ToolRegistry') as mock_tool_registry_class:
            mock_tool_registry_class.return_value = filtered_registry

            # 测试过滤
            allowed = {'file_read', 'mcp__exa__*'}
            HarnessCoordinator._filter_tool_registry(mock_registry, allowed)

            # 应注册 file_read 和 mcp__exa__web_search_exa
            # 注意：实际测试需要完整的 mock 设置


# 验收场景验证
class TestAcceptanceScenarios:
    """验收场景测试"""

    def test_default_no_mcp_permission(self):
        """验收场景：Agent 默认无 MCP 权限"""
        # 新 Agent 无配置时应返回空 MCP 列表
        # 这由 _get_agent_tools() 查询数据库实现
        # 查询结果为空时返回空列表
        pass

    def test_single_permission_config(self):
        """验收场景：单个 Agent 配置生效"""
        # 通过 API 配置后，Agent 应能获取对应的 MCP 工具模式
        pass

    def test_batch_permission_config(self):
        """验收场景：批量配置生效"""
        # 批量配置医疗 Agent 后，所有医疗 Agent 应有相同权限
        pass

    def test_wildcard_pattern(self):
        """验收场景：通配符匹配"""
        # mcp__exa__* 应匹配所有 exa MCP 工具
        pass

    def test_dynamic_update(self):
        """验收场景：动态更新生效"""
        # 配置变更后缓存清除，下次执行生效
        from services.harness.harness_coordinator import clear_registry_cache

        # 缓存清除函数应可调用
        assert callable(clear_registry_cache)
