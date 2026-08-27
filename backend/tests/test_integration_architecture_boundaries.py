"""通用集成层的静态架构边界检查。

这些测试编码了通用集成对账问题中的依赖规则：
提供者中立的模块不得导入 Agent Teams 负载模式或 LangGraph 工作流内部细节。
检查是静态（基于 AST）的，因此即使可选的 workflow 依赖未安装，这些
约束在测试环境中依然成立。
"""

import ast
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]

# 构成提供者中立 SPI 表面的模块。外部系统只能依赖这些模块
# （外加带版本号的通用 API 路由）。
GENERIC_SERVICE_MODULES = (
    'services/integration_gateway.py',
    'services/integration_client_service.py',
)

# 必须保留在适配器之后的 LangGraph / workflow 内部细节。
BANNED_MODULE_PREFIXES = (
    'langgraph',
    'langchain',
    'leader.langgraph',
    'leader.leader_persistence',
)

# Agent Teams 适配器实现模块。通用模块必须通过适配器 SPI 调用，而不能直接导入这些模块。
BANNED_ADAPTER_MODULES = (
    'services.agentteams_integration_launch',
    'api.agentteams_integration_api',
)

# 有据可查的旧版桥接：兼容性 Agent Teams 客户端仍然通过旧版账户模块配置。
# 这既不是 Agent Teams 负载模式，也不是 LangGraph 内部细节，迁移完成后会
# 随旧版路由一起移除。
ALLOWED_LEGACY_BRIDGE = 'services.agentteams_integration_account'

# 仅为旧版路由定义的 Agent Teams 负载模式类名。
AGENTTEAMS_PAYLOAD_SCHEMA_NAMES = {
    'AgentTeamsLaunchRequest',
    'AgentTeamsEmbedAnswersRequest',
}

# 不得出现在提供者中立契约字段名中的标记词。
PATIENT_FIELD_TOKENS = ('patient', 'agentteams', 'medical', 'diagnos', 'tumor', 'tumour')


def _parse(relative_path: str) -> ast.Module:
    source = (BACKEND_ROOT / relative_path).read_text(encoding='utf-8')
    return ast.parse(source, filename=relative_path)


def _module_level_imports(tree: ast.Module):
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, None
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                yield node.module, alias.name


def _all_imports(tree: ast.Module):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, None
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                yield node.module, alias.name


def _is_banned(module: str) -> bool:
    if module == ALLOWED_LEGACY_BRIDGE:
        return False
    if any(module == banned or module.startswith(banned + '.') for banned in BANNED_ADAPTER_MODULES):
        return True
    return any(module == banned or module.startswith(banned + '.') for banned in BANNED_MODULE_PREFIXES)


def test_generic_modules_do_not_import_langgraph_or_adapter_internals():
    for relative_path in GENERIC_SERVICE_MODULES:
        tree = _parse(relative_path)
        # 网关模块还在 register_builtin_adapters() 内部承载了内置适配器接线，
        # 因此只有其模块级导入需要保持中立；其他模块必须在任何位置保持中立。
        if relative_path.endswith('integration_gateway.py'):
            imports = _module_level_imports(tree)
        else:
            imports = _all_imports(tree)
        for module, name in imports:
            assert not _is_banned(module), (
                f'{relative_path} imports banned module {module!r}; '
                'generic integration modules must stay behind the adapter SPI'
            )
            assert name not in AGENTTEAMS_PAYLOAD_SCHEMA_NAMES, (
                f'{relative_path} imports Agent Teams payload schema {name!r}'
            )


def test_gateway_top_level_imports_stay_provider_neutral():
    # 网关模块还承载了内置的 Agent Teams 适配器，因此在 register_builtin_adapters()
    # 和适配器方法内部预期会出现适配器实现导入。模块级导入必须保持中立。
    tree = _parse('services/integration_gateway.py')
    for module, name in _module_level_imports(tree):
        assert not _is_banned(module), (
            f'integration_gateway imports {module!r} at module level; '
            'adapter wiring must stay inside register_builtin_adapters()'
        )
        assert name not in AGENTTEAMS_PAYLOAD_SCHEMA_NAMES


def test_adapter_spi_method_surface_is_stable():
    from services.integration_gateway import IntegrationAdapter

    expected = {'launch', 'get_status', 'reconcile', 'schedule_launch'}
    actual = {
        name
        for name in dir(IntegrationAdapter)
        if not name.startswith('_') and name != 'adapter_key'
    }
    assert expected <= actual, (
        f'adapter SPI drifted: missing methods {sorted(expected - actual)}; '
        'SPI changes require a versioned contract update'
    )


def test_provider_neutral_schemas_have_no_patient_specific_fields():
    from api.agentteams_integration_api import IntegrationLaunchRequest

    for schema in (IntegrationLaunchRequest,):
        for field_name in schema.model_fields:
            lowered = field_name.lower()
            assert not any(token in lowered for token in PATIENT_FIELD_TOKENS), (
                f'{schema.__name__}.{field_name} leaks a patient-specific field '
                'name into the provider-neutral contract'
            )


def test_generic_error_status_set_is_stable():
    from services.integration_gateway import IntegrationAdapterRegistry, register_builtin_adapters

    previous = IntegrationAdapterRegistry._adapters.pop('agentteams', None)
    try:
        register_builtin_adapters()
        adapter = IntegrationAdapterRegistry.get('agentteams')
        assert adapter is not None
        normalized = adapter._normalize_status
        assert {normalized(value) for value in ('not_found', 'created', 'completed', 'failed', 'stopped')} == {
            'not_found', 'created', 'completed', 'failed', 'stopped',
        }
        assert normalized('in_progress') == 'running'
        assert normalized('anything-else') == 'running'
    finally:
        IntegrationAdapterRegistry._adapters.pop('agentteams', None)
        if previous is not None:
            IntegrationAdapterRegistry._adapters['agentteams'] = previous
