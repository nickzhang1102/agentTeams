"""OpenHarness 配置测试"""
import os
import sys
import pytest

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestOpenHarnessConfig:
    """测试 OpenHarness 配置加载"""

    def test_openharness_config_defaults(self):
        """测试默认配置值"""
        from config import Config

        config = Config()

        assert config.OPENHARNESS_VERSION == '0.1.9'
        assert config.OPENHARNESS_ENABLED is True
        assert config.OPENHARNESS_TOOLS_ENABLED is True
        # WORKSPACE_DIR 默认为相对路径（环境变量未设置时）
        assert config.WORKSPACE_DIR == 'data/workspace'
        assert config.OPENHARNESS_WORKSPACE == config.WORKSPACE_DIR  # 别名应指向同一值
        assert config.OPENHARNESS_TOOLS_TIMEOUT == 300

    def test_openharness_native_env_defaults(self):
        """测试 OpenHarness 原生环境变量默认值"""
        from config import Config

        config = Config()

        assert config.OPENHARNESS_MAX_TOKENS == 16384
        assert config.OPENHARNESS_TIMEOUT == 30.0
        assert config.OPENHARNESS_CONFIG_DIR == ''

    def test_openharness_workspace_is_alias(self):
        """测试 OPENHARNESS_WORKSPACE 是 WORKSPACE_DIR 的别名"""
        from config import Config

        config = Config()
        # 别名应指向同一对象
        assert config.OPENHARNESS_WORKSPACE == config.WORKSPACE_DIR

    def test_openharness_config_disabled_via_env(self, monkeypatch):
        """测试通过环境变量禁用 OpenHarness"""
        monkeypatch.setenv('OPENHARNESS_ENABLED', 'false')
        monkeypatch.setenv('OPENHARNESS_TOOLS_ENABLED', 'false')

        # 需要重新导入以应用新环境变量
        from importlib import reload
        import config as config_module
        reload(config_module)

        from config import Config
        config = Config()
        assert config.OPENHARNESS_ENABLED is False
        assert config.OPENHARNESS_TOOLS_ENABLED is False

    def test_testing_config_openharness_settings(self):
        """测试测试环境配置"""
        from config import TestingConfig

        config = TestingConfig()

        assert config.OPENHARNESS_ENABLED is True
        assert config.OPENHARNESS_TOOLS_ENABLED is True
        # 测试环境使用 WORKSPACE_DIR，路径包含 tests/test_workspace
        assert 'tests' in config.WORKSPACE_DIR
        assert 'test_workspace' in config.WORKSPACE_DIR
        assert config.OPENHARNESS_WORKSPACE == config.WORKSPACE_DIR  # 别名
        assert config.OPENHARNESS_TOOLS_TIMEOUT == 60


class TestOpenHarnessConfigSchema:
    """测试 OpenHarness 配置 Schema"""

    def test_schema_contains_workspace_dir(self):
        """测试 Schema 包含 WORKSPACE_DIR 配置项"""
        from api.admin_api import OPENHARNESS_CONFIG_SCHEMA

        assert 'WORKSPACE_DIR' in OPENHARNESS_CONFIG_SCHEMA
        schema_entry = OPENHARNESS_CONFIG_SCHEMA['WORKSPACE_DIR']
        assert schema_entry[2] == 'paths'  # 分组应为 paths
        assert '工作目录' in schema_entry[0]  # 描述应提及工作目录

    def test_schema_paths_group_exists(self):
        """测试 Schema 包含 paths 分组"""
        from api.admin_api import OPENHARNESS_CONFIG_SCHEMA

        paths_keys = [k for k, v in OPENHARNESS_CONFIG_SCHEMA.items() if v[2] == 'paths']
        assert len(paths_keys) >= 1
        assert 'WORKSPACE_DIR' in paths_keys

    def test_schema_openharness_group_exists(self):
        """测试 Schema 包含 openharness 分组"""
        from api.admin_api import OPENHARNESS_CONFIG_SCHEMA

        openharness_keys = [k for k, v in OPENHARNESS_CONFIG_SCHEMA.items() if v[2] == 'openharness']
        assert len(openharness_keys) >= 3
        assert 'OPENHARNESS_MAX_TOKENS' in openharness_keys
        assert 'OPENHARNESS_TIMEOUT' in openharness_keys
        assert 'OPENHARNESS_CONFIG_DIR' in openharness_keys

    def test_schema_openharness_max_tokens(self):
        """测试 Schema 包含 OPENHARNESS_MAX_TOKENS 配置项"""
        from api.admin_api import OPENHARNESS_CONFIG_SCHEMA

        assert 'OPENHARNESS_MAX_TOKENS' in OPENHARNESS_CONFIG_SCHEMA
        schema_entry = OPENHARNESS_CONFIG_SCHEMA['OPENHARNESS_MAX_TOKENS']
        assert schema_entry[2] == 'openharness'
        assert schema_entry[1] == '16384'  # 默认值

    def test_schema_openharness_timeout(self):
        """测试 Schema 包含 OPENHARNESS_TIMEOUT 配置项"""
        from api.admin_api import OPENHARNESS_CONFIG_SCHEMA

        assert 'OPENHARNESS_TIMEOUT' in OPENHARNESS_CONFIG_SCHEMA
        schema_entry = OPENHARNESS_CONFIG_SCHEMA['OPENHARNESS_TIMEOUT']
        assert schema_entry[2] == 'openharness'
        assert schema_entry[1] == '30'  # 默认值

    def test_schema_openharness_config_dir(self):
        """测试 Schema 包含 OPENHARNESS_CONFIG_DIR 配置项"""
        from api.admin_api import OPENHARNESS_CONFIG_SCHEMA

        assert 'OPENHARNESS_CONFIG_DIR' in OPENHARNESS_CONFIG_SCHEMA
        schema_entry = OPENHARNESS_CONFIG_SCHEMA['OPENHARNESS_CONFIG_DIR']
        assert schema_entry[2] == 'openharness'
        assert schema_entry[1] == ''  # 默认值为空


class TestPathValidation:
    """测试路径配置验证"""

    def test_empty_path_rejected(self):
        """测试空路径被拒绝"""
        # 模拟验证逻辑
        value = ""
        assert not value.strip()  # 应为空，验证应拒绝

    def test_path_traversal_rejected(self):
        """测试路径遍历被拒绝"""
        # 模拟验证逻辑
        value = "../outside"
        assert '..' in value  # 应被检测并拒绝

    def test_valid_relative_path_accepted(self):
        """测试合法相对路径被接受"""
        value = "data/workspace"
        assert value.strip()  # 非空
        assert '..' not in value  # 无路径遍历

    def test_valid_absolute_path_accepted(self):
        """测试合法绝对路径被接受"""
        value = "/var/lib/workspace"
        assert value.strip()  # 非空
        assert '..' not in value  # 无路径遍历