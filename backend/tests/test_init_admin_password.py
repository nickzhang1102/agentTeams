"""init_admin 管理员密码解析与校验的单元测试（纯逻辑，不依赖数据库）"""
import os

import pytest

from config import Config
from init_admin import (
    initial_password_file_path,
    resolve_initial_password,
    validate_admin_password,
)


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    """每个用例默认清除 ADMIN_INITIAL_PASSWORD，互不串扰。"""
    monkeypatch.delenv('ADMIN_INITIAL_PASSWORD', raising=False)


class TestResolveInitialPassword:
    def test_unset_returns_none(self):
        assert resolve_initial_password() is None

    def test_blank_returns_none(self, monkeypatch):
        monkeypatch.setenv('ADMIN_INITIAL_PASSWORD', '   ')
        assert resolve_initial_password() is None

    def test_valid_password_returned_stripped(self, monkeypatch):
        monkeypatch.setenv('ADMIN_INITIAL_PASSWORD', '  Passw0rd123  ')
        assert resolve_initial_password() == 'Passw0rd123'

    def test_too_short_fails_closed(self, monkeypatch):
        monkeypatch.setenv('ADMIN_INITIAL_PASSWORD', 'ab1')
        with pytest.raises(RuntimeError, match='长度'):
            resolve_initial_password()

    def test_missing_digit_fails_closed(self, monkeypatch):
        monkeypatch.setenv('ADMIN_INITIAL_PASSWORD', 'abcdefgh')
        with pytest.raises(RuntimeError, match='数字'):
            resolve_initial_password()

    def test_missing_letter_fails_closed(self, monkeypatch):
        monkeypatch.setenv('ADMIN_INITIAL_PASSWORD', '12345678')
        with pytest.raises(RuntimeError, match='字母'):
            resolve_initial_password()


class TestValidateAdminPassword:
    def test_min_length_boundary_accepted(self):
        pw = 'a' * (Config.PASSWORD_MIN_LENGTH - 1) + '1'
        assert validate_admin_password(pw) is None

    def test_empty_invalid(self):
        assert validate_admin_password('') is not None

    def test_policy_flags_off(self, monkeypatch):
        monkeypatch.setattr(Config, 'PASSWORD_MIN_LENGTH', 4)
        monkeypatch.setattr(Config, 'PASSWORD_REQUIRE_LETTER', False)
        monkeypatch.setattr(Config, 'PASSWORD_REQUIRE_DIGIT', False)
        assert validate_admin_password('abcd') is None


def test_password_file_path():
    path = initial_password_file_path()
    assert os.path.basename(path) == '.admin_initial_password'
    assert 'data' in path
