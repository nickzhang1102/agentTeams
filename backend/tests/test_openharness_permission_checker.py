"""测试 OpenHarness 权限检查器使用实际工具名"""
import pytest

from services.harness.openharness_permission_checker import (
    create_permission_checker_for_agent,
    get_agent_type_from_id,
)


class TestPermissionCheckerActualToolNames:
    """验证权限集合使用 OpenHarness 实际工具名"""

    def test_medical_tools_use_actual_names(self):
        checker = create_permission_checker_for_agent("medical")
        assert "read_file" in checker.agent_tools
        assert "write_file" in checker.agent_tools
        assert "file_read" not in checker.agent_tools
        assert "file_write" not in checker.agent_tools

    def test_technical_tools_use_actual_names(self):
        checker = create_permission_checker_for_agent("technical")
        assert "read_file" in checker.agent_tools
        assert "write_file" in checker.agent_tools
        assert "edit_file" in checker.agent_tools
        assert "bash" in checker.agent_tools
        assert "file_edit" not in checker.agent_tools
        assert "file_read" not in checker.agent_tools

    def test_business_tools_use_actual_names(self):
        checker = create_permission_checker_for_agent("business")
        assert "read_file" in checker.agent_tools
        assert "write_file" in checker.agent_tools
        assert "file_read" not in checker.agent_tools

    def test_medical_has_common_tools(self):
        checker = create_permission_checker_for_agent("medical")
        assert "grep" in checker.agent_tools
        assert "glob" in checker.agent_tools
        assert "web_search" in checker.agent_tools

    def test_technical_has_bash(self):
        checker = create_permission_checker_for_agent("technical")
        assert "bash" in checker.agent_tools
        assert "edit_file" in checker.agent_tools

    def test_medical_lacks_bash(self):
        checker = create_permission_checker_for_agent("medical")
        assert "bash" not in checker.agent_tools
        assert "edit_file" not in checker.agent_tools


class TestAgentTypeDetection:
    """验证 Agent 类型检测逻辑"""

    def test_medical_keyword_detection(self):
        assert get_agent_type_from_id("cardiology-expert") == "medical"
        assert get_agent_type_from_id("neurology-doctor") == "medical"

    def test_technical_keyword_detection(self):
        assert get_agent_type_from_id("fullstack-developer") == "technical"
        assert get_agent_type_from_id("devops-engineer") == "technical"

    def test_business_default(self):
        assert get_agent_type_from_id("ceo") == "business"
        assert get_agent_type_from_id("marketing") == "business"
