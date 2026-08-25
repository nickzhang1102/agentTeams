"""Graphify MCP 注册功能测试

测试 graphify MCP 服务配置注册功能：
- 用户级图谱路径配置（get_user_graph_path）
- 预置模板扩展
- API 状态查询
- API 启用服务
"""

import os
import json
import re
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestGraphifyConfig:
    """测试用户级图谱路径配置"""

    def test_user_graph_path_config_exists(self):
        """验证 get_user_graph_path 方法存在并返回有效路径"""
        from config import Config

        assert hasattr(Config, 'get_user_graph_path')
        path = Config.get_user_graph_path(123)
        assert path is not None
        # 用户图谱路径包含 knowledge 根目录与 user_{id}_graph.json
        assert 'knowledge' in path
        assert 'user_123_graph.json' in path


class TestGraphifyPreset:
    """测试预置模板扩展"""

    def test_graphify_in_preset_servers(self):
        """验证 graphify 在预置模板中"""
        from services.mcp.mcp_config import PRESET_MCP_SERVERS

        assert 'graphify' in PRESET_MCP_SERVERS

    def test_graphify_preset_has_required_fields(self):
        """验证 graphify 预置模板字段完整"""
        from services.mcp.mcp_config import PRESET_MCP_SERVERS

        preset = PRESET_MCP_SERVERS['graphify']
        assert preset['name'] == 'graphify'
        assert preset['transport'] == 'stdio'
        assert preset['command'] == 'python'
        assert preset['args'] == ['-m', 'graphify.serve']
        assert preset['category'] == 'knowledge'
        # 全局图谱符号已删除，preset 不再声明 requires 依赖
        assert 'requires' not in preset

    def test_graphify_preset_disabled_by_default(self):
        """验证 graphify 预置模板默认禁用"""
        from services.mcp.mcp_config import PRESET_MCP_SERVERS

        preset = PRESET_MCP_SERVERS['graphify']
        assert preset['disabled'] is True


class TestGraphifyMcpSettings:
    """测试 MCP 配置写入"""

    def test_mcp_settings_has_graphify(self):
        """验证 mcp_settings.json 含 graphify 配置"""
        settings_path = Path(__file__).parent.parent / 'mcp_settings.json'

        if settings_path.exists():
            data = json.loads(settings_path.read_text(encoding='utf-8'))
            assert 'graphify' in data.get('mcpServers', {})


class TestGraphifyStatusAPI:
    """测试状态查询 API"""

    def test_api_endpoint_exists(self):
        """验证 API 端点函数存在"""
        from api.admin.mcp_admin_api import get_graphify_status

        assert get_graphify_status is not None
        assert callable(get_graphify_status)

    def test_api_imports_correct_modules(self):
        """验证 API 导入正确的模块"""
        # 验证函数定义中使用的模块可以导入
        from services.mcp.mcp_config import get_mcp_config
        from config import Config
        from pathlib import Path

        assert get_mcp_config is not None
        assert hasattr(Config, 'get_user_graph_path')


class TestGraphifyEnableAPI:
    """测试启用服务 API"""

    def test_api_endpoint_exists(self):
        """验证 API 端点函数存在"""
        from api.admin.mcp_admin_api import enable_graphify

        assert enable_graphify is not None
        assert callable(enable_graphify)


class TestExplicitlyNotDoing:
    """明确不做反向核对

    使用 pathlib 遍历 + 字符串匹配实现跨平台静态扫描，
    替代早期依赖外部 grep 与硬编码绝对路径的实现
    （旧实现在无 grep 的 Windows 上必然失败，且指向已迁移的旧路径会假通过）。
    """

    # 静态扫描时跳过的目录（缓存 / 虚拟环境）
    SKIP_DIRS = {'__pycache__', '.pytest_cache', 'venv', '.venv'}

    @classmethod
    def _repo_root(cls) -> Path:
        """仓库根目录：backend/tests/xx.py -> backend -> 仓库根"""
        return Path(__file__).resolve().parents[2]

    @classmethod
    def _iter_py_files(cls, root: Path):
        """遍历目录下所有 .py 文件，跳过缓存与虚拟环境目录"""
        for path in root.rglob('*.py'):
            if any(part in cls.SKIP_DIRS for part in path.parts):
                continue
            yield path

    @classmethod
    def _read_lines(cls, path: Path) -> list[str]:
        """读取文件行；errors='replace' 防御非 UTF-8 内容导致扫描中断"""
        return path.read_text(encoding='utf-8', errors='replace').splitlines()

    def test_no_graphify_extract_cli_invocation(self):
        """不做图谱提取 - API 层无 subprocess 直调 graphify extract CLI

        注意：mcp_admin_api.py 中的 "Run graphify extract first" 只是用户提示信息，
        不是实际的 CLI 调用代码。
        """
        api_root = self._repo_root() / 'backend' / 'api'
        offenders = [
            f'{path}:{lineno}'
            for path in self._iter_py_files(api_root)
            for lineno, line in enumerate(self._read_lines(path), start=1)
            # 同一行同时出现 subprocess 与 graphify 视为 CLI 直调
            if 'subprocess' in line.lower() and 'graphify' in line.lower()
        ]
        assert not offenders, f'API 层发现 subprocess 直调 graphify：{offenders}'

    def test_no_daemon_management(self):
        """不做 daemon 管理 - MCP 服务层无进程守护代码

        豁免 threading.Thread(daemon=True) 这类线程标志，
        它与进程守护（daemonize / PID 文件 / supervisor）无关。
        """
        mcp_root = self._repo_root() / 'backend' / 'services' / 'mcp'
        offenders = []
        for path in self._iter_py_files(mcp_root):
            for lineno, line in enumerate(self._read_lines(path), start=1):
                if 'daemon' not in line.lower():
                    continue
                # 线程标志参数不算进程守护
                if re.search(r'daemon\s*=\s*True', line, re.IGNORECASE):
                    continue
                offenders.append(f'{path}:{lineno}: {line.strip()}')
        assert not offenders, f'MCP 服务层发现疑似进程守护代码：{offenders}'

    def test_no_frontend_changes(self):
        """不做前端 UI - frontend/src 源码中无 graphify 相关内容"""
        src_root = self._repo_root() / 'frontend' / 'src'
        source_exts = {'.vue', '.js', '.ts', '.jsx', '.tsx', '.scss', '.css'}
        offenders = [
            str(path)
            for path in src_root.rglob('*')
            if path.suffix in source_exts and path.is_file()
            for text in [path.read_text(encoding='utf-8', errors='replace')]
            if 'graphify' in text.lower()
        ]
        assert not offenders, f'前端源码出现 graphify 引用：{offenders}'

    def test_no_merge_graphs_call(self):
        """不做图谱合并 - backend 非 test 代码无 merge_graphs 实际调用"""
        backend_root = self._repo_root() / 'backend'
        offenders = [
            str(path)
            for path in self._iter_py_files(backend_root)
            # 测试文件与 conftest 自身不参与本断言
            if 'test' not in path.name.lower()
            for text in ['\n'.join(self._read_lines(path))]
            if 'merge_graphs' in text
        ]
        assert not offenders, f'backend 非 test 代码出现 merge_graphs：{offenders}'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])