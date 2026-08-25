from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from api.admin.mcp_admin_api import get_openharness_tools
from api.admin.tool_logs_api import get_tools
from catalog.tool_descriptions import localize_tool_description


class _FakeTool:
    """Execute a shell command."""


class _FakeRegistry:
    def __init__(self):
        self.oh_registry = self

    def list_tools(self):
        return [{
            'name': 'bash',
            'description': 'Run shell commands.',
            'input_schema': {'type': 'object'},
        }]

    def get(self, name):
        return _FakeTool() if name == 'bash' else None


class _FakeQuery:
    def filter(self, *_args, **_kwargs):
        return self

    def all(self):
        return []


class _FakeDb:
    def query(self, *_args, **_kwargs):
        return _FakeQuery()


def test_default_tool_description_preserves_existing_zh_cn_override():
    source = {
        'name': 'bash',
        'description': 'Run shell commands.',
        'detailed_description': 'Execute a shell command.',
    }

    localized = localize_tool_description(source)

    assert localized['description'] == '在本地仓库中执行 Shell 命令。'
    assert localized['detailed_description'] == '执行 Shell 命令，捕获 stdout/stderr 输出。'
    assert source['description'] == 'Run shell commands.'


def test_default_tool_description_preserves_unknown_tool_source():
    source = {
        'name': 'custom_tool',
        'description': 'Custom description.',
        'detailed_description': 'Custom details.',
    }

    assert localize_tool_description(source) == source


def test_en_us_tool_description_uses_registry_source():
    source = {
        'name': 'bash',
        'description': 'Run shell commands.',
        'detailed_description': 'Execute a shell command.',
    }

    assert localize_tool_description(source, 'en-US') == source


def _request(accept_language: str = 'zh-CN') -> Request:
    return Request({
        'type': 'http',
        'method': 'GET',
        'path': '/',
        'headers': [(b'accept-language', accept_language.encode('ascii'))],
    })


@pytest.mark.parametrize('endpoint', [get_tools, get_openharness_tools])
def test_admin_tool_endpoints_reject_unsupported_explicit_locale(endpoint):
    kwargs = {
        'request': _request(),
        'locale': 'fr-FR',
        'admin': SimpleNamespace(preferred_locale='zh-CN'),
    }
    if endpoint is get_tools:
        kwargs['db_session'] = None

    with pytest.raises(HTTPException) as exc_info:
        endpoint(**kwargs)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail['code'] == 'UNSUPPORTED_LOCALE'


@pytest.mark.parametrize(
    ('locale', 'expected'),
    [
        ('zh-CN', '在本地仓库中执行 Shell 命令。'),
        ('en-US', 'Run shell commands.'),
    ],
)
def test_both_admin_tool_endpoints_share_locale_descriptions(monkeypatch, locale, expected):
    registry = _FakeRegistry()
    monkeypatch.setattr(
        'services.harness.harness_adapter.HarnessToolRegistry',
        lambda workspace_dir: registry,
    )
    monkeypatch.setattr(
        'api.admin.mcp_admin_api._get_tools_registry_cached',
        lambda: registry,
    )
    admin = SimpleNamespace(preferred_locale='zh-CN')

    tools_response = get_tools(
        request=_request(),
        locale=locale,
        db_session=_FakeDb(),
        admin=admin,
    )
    openharness_response = get_openharness_tools(
        request=_request(),
        locale=locale,
        admin=admin,
    )

    assert tools_response['tools'][0]['description'] == expected
    assert openharness_response['tools'][0]['description'] == expected
