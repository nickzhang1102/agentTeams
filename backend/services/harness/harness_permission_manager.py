"""
OpenHarness Permission Manager

扩展权限检查并集成钩子系统，实现完整的权限治理
"""
import subprocess
import logging
import os
import json
from pathlib import Path
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class HarnessPermissionManager:
    """
    权限治理管理器

    扩展权限检查（路径、命令）并集成钩子系统
    """

    # 路径规则
    ALLOWED_PATH_PATTERNS = [
        "data/files",
        "data/workspace",
        ".claude",
    ]

    DENIED_PATH_PATTERNS = [
        ".env",
        ".git",
        "credentials",
        "secrets",
    ]

    # 命令规则
    DENIED_COMMAND_PATTERNS = [
        "rm -rf /",
        "sudo",
        "chmod 777",
        "curl",
        "| bash",
    ]

    def __init__(self, hooks_dir: str, config: Optional[Dict] = None):
        """
        初始化权限治理管理器

        Args:
            hooks_dir: 钩子脚本目录
            config: 配置字典（可选）
        """
        self.hooks_dir = Path(hooks_dir)
        self.hooks_dir.mkdir(parents=True, exist_ok=True)
        self.config = config or {}

        logger.info(f"Permission manager initialized: hooks_dir={self.hooks_dir}")

    def _is_path_in_allowed_directory(self, path: str, allowed_pattern: str) -> bool:
        """检查路径规范化后是否仍位于允许目录内"""
        try:
            normalized_path = Path(path).resolve(strict=False)
            allowed_path = Path(allowed_pattern).resolve(strict=False)
            return normalized_path == allowed_path or allowed_path in normalized_path.parents
        except (OSError, RuntimeError, ValueError):
            return False

    def check_path_permission(self, path: str) -> Dict[str, Any]:
        """
        检查路径权限

        Args:
            path: 文件路径

        Returns:
            {"allowed": bool, "reason": str}
        """
        path_lower = path.lower()

        # 检查是否在拒绝列表
        for denied_pattern in self.DENIED_PATH_PATTERNS:
            if denied_pattern.lower() in path_lower:
                reason = f"Path matches denied pattern: {denied_pattern}"
                logger.warning(f"Path permission denied: {path} - {reason}")
                return {"allowed": False, "reason": reason}

        # 检查是否在允许列表
        for allowed_pattern in self.ALLOWED_PATH_PATTERNS:
            if self._is_path_in_allowed_directory(path, allowed_pattern):
                logger.debug(f"Path permission allowed: {path}")
                return {"allowed": True, "reason": f"Path in allowed directory: {allowed_pattern}"}

        # 默认拒绝
        reason = "Path not in allowed list"
        logger.warning(f"Path permission denied: {path} - {reason}")
        return {"allowed": False, "reason": reason}

    def check_command_permission(self, command: str) -> Dict[str, Any]:
        """
        检查命令权限

        Args:
            command: Shell 命令

        Returns:
            {"allowed": bool, "reason": str}
        """
        command_lower = command.lower()

        # 检查是否在拒绝列表
        for denied_pattern in self.DENIED_COMMAND_PATTERNS:
            if denied_pattern.lower() in command_lower:
                reason = f"Command matches denied pattern: {denied_pattern}"
                logger.warning(f"Command permission denied: {command} - {reason}")
                return {"allowed": False, "reason": reason}

        # 默认允许
        logger.debug(f"Command permission allowed: {command}")
        return {"allowed": True, "reason": "Command allowed"}

    def check_permission(
        self,
        action: str,
        resource: str,
        context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        综合权限检查

        Args:
            action: 操作类型（file_read, file_write, command_execute 等）
            resource: 资源（文件路径或命令）
            context: 上下文信息

        Returns:
            {"allowed": bool, "reason": str}
        """
        context = context or {}

        if action in ["file_read", "file_write"]:
            return self.check_path_permission(resource)
        elif action == "command_execute":
            return self.check_command_permission(resource)
        elif action == "start_leader":
            # Leader 启动操作，默认允许
            logger.debug(f"Leader start permission granted: {resource}")
            return {"allowed": True, "reason": "Leader start allowed"}
        else:
            # 未知操作类型，默认拒绝（安全原则）
            logger.warning(f"Unknown action type: {action}")
            return {"allowed": False, "reason": f"Unknown action type: {action}"}

    def register_hook(self, hook_name: str, hook_script: str) -> None:
        """
        注册钩子脚本

        Args:
            hook_name: 钩子名称（PreToolUse, PostToolUse, PreAgentSpawn 等）
            hook_script: 钩子脚本内容
        """
        hook_file = self.hooks_dir / f"{hook_name}.sh"

        with open(hook_file, 'w', encoding='utf-8') as f:
            f.write(hook_script)

        # 设置可执行权限（Unix/Linux）
        if os.name != 'nt':  # Windows 不支持 chmod
            hook_file.chmod(0o755)

        logger.info(f"Hook registered: {hook_name}")

    def execute_hook(
        self,
        hook_name: str,
        data: Dict[str, Any],
        callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        执行钩子

        Args:
            hook_name: 钩子名称
            data: 传递给钩子的数据
            callback: 回调函数（可选）

        Returns:
            {"allowed": bool, "executed": bool, "output": str}
        """
        hook_file = self.hooks_dir / f"{hook_name}.sh"

        # 钩子不存在，允许通过
        if not hook_file.exists():
            logger.debug(f"Hook not found: {hook_name}, allowing by default")
            return {"allowed": True, "executed": False, "output": ""}

        try:
            # 执行钩子脚本
            # 将数据作为环境变量传递
            env = {**os.environ, "HOOK_DATA": json.dumps(data)}

            # Windows 兼容：使用 Git Bash 或 WSL 执行 .sh 脚本
            if os.name == 'nt':
                # Windows 下尝试用 bash 命令执行（需要 Git Bash 或 WSL）
                result = subprocess.run(
                    ["bash", str(hook_file)],
                    capture_output=True,
                    text=True,
                    env=env,
                    timeout=10  # 10 秒超时
                )
            else:
                # Unix/Linux 直接执行
                result = subprocess.run(
                    [str(hook_file)],
                    capture_output=True,
                    text=True,
                    env=env,
                    timeout=10  # 10 秒超时
                )

            executed = True
            allowed = result.returncode == 0
            output = result.stdout.strip()

            logger.info(f"Hook executed: {hook_name}, allowed={allowed}, output={output}")

            # 执行回调
            if callback:
                callback(hook_name, allowed, output)

            return {
                "allowed": allowed,
                "executed": executed,
                "output": output
            }

        except subprocess.TimeoutExpired:
            logger.error(f"Hook execution timeout: {hook_name}")
            return {
                "allowed": False,
                "executed": True,
                "output": "Hook execution timeout"
            }
        except FileNotFoundError:
            # Windows 下可能找不到 bash 命令
            logger.error(f"Hook execution failed: {hook_name} - bash not found on Windows")
            return {
                "allowed": False,
                "executed": False,
                "output": "bash not found on Windows, install Git Bash or WSL"
            }
        except Exception as e:
            logger.error(f"Hook execution failed: {hook_name} - {e}")
            return {
                "allowed": False,
                "executed": False,
                "output": str(e)
            }
