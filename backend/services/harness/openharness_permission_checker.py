"""
OpenHarness Permission Checker

实现基于 Agent 类型的权限检查
"""
import logging
from typing import Set

from openharness.permissions.checker import PermissionChecker, PermissionDecision
from openharness.permissions.modes import PermissionMode
from openharness.config.settings import PermissionSettings

logger = logging.getLogger(__name__)


class OpenHarnessPermissionChecker(PermissionChecker):
    """
    基于 Agent 类型的权限检查器

    继承 OpenHarness PermissionChecker，根据 Agent 类型控制工具权限
    """

    def __init__(
        self,
        agent_tools: Set[str],
        mode: PermissionMode = PermissionMode.DEFAULT
    ):
        """
        初始化权限检查器

        Args:
            agent_tools: Agent 可用的工具集合
            mode: 权限模式（default/plan/full_auto）
        """
        # 构建权限设置
        settings = PermissionSettings(
            mode=mode,
            allowed_tools=list(agent_tools),
            denied_tools=[],
        )

        super().__init__(settings)
        self.agent_tools = agent_tools

        logger.info(f"Permission checker initialized: mode={mode.value}, tools={agent_tools}")

    def evaluate(
        self,
        tool_name: str,
        *,
        is_read_only: bool,
        file_path: str | None = None,
        command: str | None = None,
    ) -> PermissionDecision:
        """
        评估工具调用权限

        Args:
            tool_name: 工具名称
            is_read_only: 是否只读工具
            file_path: 文件路径（可选）
            command: 命令（可选）

        Returns:
            PermissionDecision: 权限决策
        """
        # 首先检查工具是否在 Agent 允许的工具列表中
        if tool_name not in self.agent_tools:
            return PermissionDecision(
                allowed=False,
                reason=f"Tool '{tool_name}' is not allowed for this agent type"
            )

        # 调用父类方法进行进一步检查
        return super().evaluate(
            tool_name,
            is_read_only=is_read_only,
            file_path=file_path,
            command=command
        )


def create_permission_checker_for_agent(
    agent_type: str,
    mode: PermissionMode = PermissionMode.DEFAULT
) -> OpenHarnessPermissionChecker:
    """
    为指定类型的 Agent 创建权限检查器

    Args:
        agent_type: Agent 类型（medical/technical/business）
        mode: 权限模式

    Returns:
        OpenHarnessPermissionChecker 实例
    """
    # 根据 Agent 类型确定工具集（名称须与 OpenHarness 工具注册名一致）
    if agent_type == "medical":
        tools = {"read_file", "write_file", "grep", "glob", "web_search"}
    elif agent_type == "technical":
        tools = {"read_file", "write_file", "edit_file", "grep", "glob", "bash", "web_search"}
    else:  # business
        tools = {"read_file", "write_file", "grep", "glob", "web_search"}

    return OpenHarnessPermissionChecker(tools, mode)


def get_agent_type_from_id(agent_id: str) -> str:
    """
    根据 Agent ID 推断 Agent 类型

    Args:
        agent_id: Agent ID

    Returns:
        Agent 类型（medical/technical/business）
    """
    agent_lower = agent_id.lower()

    # 医疗 Agent 关键词
    medical_keywords = [
        "surgery", "expert", "medicine", "doctor",
        "cardiology", "neurology", "pediatrics", "oncology",
        "gynecology", "orthopedics", "psychiatry", "radiology"
    ]

    # 技术 Agent 关键词
    technical_keywords = [
        "developer", "devops", "fullstack", "qa",
        "backend", "frontend", "engineer", "architect"
    ]

    # 检查 Agent 类型
    if any(keyword in agent_lower for keyword in medical_keywords):
        return "medical"
    elif any(keyword in agent_lower for keyword in technical_keywords):
        return "technical"
    else:
        return "business"