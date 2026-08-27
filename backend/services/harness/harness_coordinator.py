"""
HarnessCoordinator - Adapter layer for OpenHarness integration.

This module provides a unified interface for managing Claude Code agents
with OpenHarness tool ecosystem support.
"""
import os
import logging
import asyncio
import time
import threading
from pathlib import Path
from typing import Dict, List, Optional, Any
from concurrent.futures import ThreadPoolExecutor

import yaml

from db import db  # 使用独立的 db.py

logger = logging.getLogger(__name__)
MCP_PATTERNS_CACHE_TTL_SECONDS = 5.0


class HarnessCoordinator:
    """Coordinator for managing agents with OpenHarness tool support.

    This class adapts OpenHarness's AgentDefinition and TeamRegistry
    to work with the existing Claude Chat system's agent management.
    """

    def __init__(
        self,
        agents_dir: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        """Initialize the coordinator.

        Args:
            agents_dir: Directory containing agent configuration files.
                       Defaults to ../agents relative to backend dir.
            config: 应用配置 dict. If None, falls back to Config class.
        """
        self._config = config  # 保存注入的配置

        # 优先级：显式参数 > config['AGENTS_DIR'] > Config 类默认值
        if agents_dir:
            self.agents_dir = agents_dir
        elif config and config.get('AGENTS_DIR'):
            self.agents_dir = config['AGENTS_DIR']
        else:
            from config import Config
            self.agents_dir = Config.AGENTS_DIR
        self.registered_agents: Dict[str, Dict[str, Any]] = {}
        self._cached_full_registry = None  # 缓存全量 ToolRegistry，避免并行 Agent 重复创建
        self._mcp_manager = None  # MCP 单例引用
        self._mcp_patterns_cache: Optional[Dict[str, List[str]]] = None  # MCP 工具权限缓存（None=未加载）
        self._mcp_patterns_cache_loaded_at = 0.0

        # Lazy import OpenHarness components
        self.oh_coordinator = None
        self.agent_definition_class = None
        self.team_registry = None
        self._initialize_openharness()

        # 获取 MCP 单例引用（不重复初始化）
        self._initialize_mcp()

        # Register existing agents
        self._register_agents()

    def _initialize_openharness(self):
        """Initialize OpenHarness components with lazy import."""
        try:
            from openharness.coordinator.agent_definitions import (
                AgentDefinition,
                load_agents_dir,
            )
            from openharness.coordinator.coordinator_mode import (
                TeamRegistry,
                get_team_registry,
            )

            self.agent_definition_class = AgentDefinition
            self.team_registry = get_team_registry()
            self.load_agents_dir = load_agents_dir

            logger.info("OpenHarness components initialized successfully")
        except ImportError as e:
            logger.warning(f"OpenHarness not available: {e}. Tool support disabled.")
            self.agent_definition_class = None
            self.team_registry = None
            self.load_agents_dir = None

    def _initialize_mcp(self):
        """获取 MCP 单例引用（不重复初始化）。

        MCP 单例由应用启动时初始化，这里只获取引用。
        """
        try:
            from services.mcp.mcp_manager import get_mcp_manager, is_mcp_initialized

            if is_mcp_initialized():
                self._mcp_manager = get_mcp_manager()
                tools = self._mcp_manager.list_tools()
                logger.info(f"MCP manager referenced: {len(tools)} MCP tools available")
            else:
                logger.debug("MCP manager not initialized yet")
                self._mcp_manager = None
        except Exception as e:
            logger.warning(f"MCP manager reference failed: {e}")
            self._mcp_manager = None

    def _register_agents(self):
        """Register all agents from the agents directory."""
        if not os.path.isdir(self.agents_dir):
            logger.warning(f"Agents directory not found: {self.agents_dir}")
            return

        agents_path = Path(self.agents_dir)
        agent_files = list(agents_path.glob("*.md"))

        logger.info(f"Found {len(agent_files)} agent files in {self.agents_dir}")

        for agent_file in agent_files:
            try:
                config = self._parse_agent_config(agent_file)
                if config and "name" in config:
                    # Store filename stem as alias for dual-key registration
                    config["_file_stem"] = agent_file.stem
                    self._register_single_agent(config)
            except Exception as e:
                logger.error(f"Failed to register agent from {agent_file}: {e}")

        logger.info(f"Registered {len(self.registered_agents)} agents")

    def _parse_agent_config(self, agent_file: Path) -> Optional[Dict[str, Any]]:
        """Parse agent configuration from markdown file.

        Args:
            agent_file: Path to the agent markdown file.

        Returns:
            Dictionary with agent configuration, or None if parsing fails.
        """
        try:
            content = agent_file.read_text(encoding="utf-8")
            lines = content.splitlines()

            # Check for YAML frontmatter
            if not lines or lines[0].strip() != "---":
                logger.warning(f"No frontmatter found in {agent_file}")
                return None

            # Find end of frontmatter
            end_index = None
            for i, line in enumerate(lines[1:], start=1):
                if line.strip() == "---":
                    end_index = i
                    break

            if end_index is None:
                logger.warning(f"Invalid frontmatter in {agent_file}")
                return None

            # Parse YAML frontmatter
            fm_text = "\n".join(lines[1:end_index])
            frontmatter = yaml.safe_load(fm_text)

            if not isinstance(frontmatter, dict):
                logger.warning(f"Invalid frontmatter structure in {agent_file}")
                return None

            # Extract required fields
            name = frontmatter.get("name")
            description = frontmatter.get("description")

            if not name or not description:
                logger.warning(f"Missing required fields in {agent_file}")
                return None

            # Extract system prompt from body
            body = "\n".join(lines[end_index + 1 :]).strip()

            return {
                "name": str(name).strip(),
                "description": str(description).strip(),
                "model": frontmatter.get("model", "inherit"),
                "system_prompt": body,
                "color": frontmatter.get("color"),
                "effort": frontmatter.get("effort"),
                "permission_mode": frontmatter.get("permissionMode"),
                "max_turns": frontmatter.get("maxTurns"),
            }

        except Exception as e:
            logger.error(f"Error parsing {agent_file}: {e}")
            return None

    def _register_single_agent(self, config: Dict[str, Any]):
        """Register a single agent.

        Uses both the Chinese name (from frontmatter) and the filename stem
        as registration keys, so lookups work with either convention.

        Args:
            config: Agent configuration dictionary.
        """
        agent_id = config["name"]
        file_stem = config.get("_file_stem", "")

        # Get agent tools based on type
        tools = self._get_agent_tools(agent_id)

        # Build registration entry
        registration = {
            "name": config["name"],
            "description": config["description"],
            "model": config.get("model", "inherit"),
            "system_prompt": config.get("system_prompt"),
            "tools": tools,
            "color": config.get("color"),
            "effort": config.get("effort"),
            "permission_mode": config.get("permission_mode"),
            "max_turns": config.get("max_turns"),
        }

        # Register with Chinese name as primary key
        self.registered_agents[agent_id] = registration

        # Also register with filename stem as alias key
        # (e.g., "首席AI官" <-> "caio-ai")
        if file_stem and file_stem != agent_id:
            self.registered_agents[file_stem] = registration
            logger.debug(f"Registered alias: {file_stem} -> {agent_id}")

        # Register with OpenHarness if available
        if self.agent_definition_class and self.team_registry:
            try:
                agent_def = self.agent_definition_class(
                    name=config["name"],
                    description=config["description"],
                    system_prompt=config.get("system_prompt"),
                    tools=tools,
                    model=config.get("model"),
                    color=config.get("color"),
                    effort=config.get("effort"),
                    permission_mode=config.get("permission_mode"),
                    max_turns=config.get("max_turns"),
                )

                # Persist to team registry
                team_name = "default-team"
                try:
                    # Try to create default team if it doesn't exist
                    if team_name not in [t.name for t in self.team_registry.list_teams()]:
                        self.team_registry.create_team(name=team_name, description="Default agent pool")
                except Exception:
                    pass  # Team may already exist

                # Add agent to default team
                self.team_registry.add_agent(team_name, agent_def)
                logger.debug(f"Registered OpenHarness definition for agent: {agent_id}")
            except Exception as e:
                logger.warning(f"Failed to register OpenHarness definition for {agent_id}: {e}")

        logger.info(f"Registered agent: {agent_id}")

    def _get_agent_tools(self, agent_id: str) -> List[str]:
        """Determine available tools for an agent based on its type + MCP permissions.

        Args:
            agent_id: Agent identifier.

        Returns:
            List of tool names available to this agent.
        """
        agent_lower = agent_id.lower()

        # 使用模块级常量（已包含中文关键词）
        # 知识库可用时才分配 knowledge_search 工具
        knowledge_tool = ["knowledge_search"] if self._is_knowledge_available() else []

        # Check agent type based on keywords
        if any(keyword in agent_lower for keyword in MEDICAL_KEYWORDS):
            base_tools = ["read_file", "write_file", "grep", "glob", "web_search"] + knowledge_tool
        elif any(keyword in agent_lower for keyword in TECHNICAL_KEYWORDS):
            # shell 类工具默认不分配：与后端同用户运行、无容器隔离，
            # 显式开启 OPENHARNESS_SHELL_TOOLS_ENABLED 后才进入技术类白名单（见 SECURITY.md）。
            from config import Config
            shell_tools = ["edit_file", "bash"] if getattr(Config, 'OPENHARNESS_SHELL_TOOLS_ENABLED', False) else []
            base_tools = ["read_file", "write_file"] + shell_tools + ["grep", "glob", "web_search"] + knowledge_tool
        else:
            # Default: business/other agents get standard tool set
            base_tools = ["read_file", "write_file", "grep", "glob", "web_search"] + knowledge_tool

        # 读取 MCP 工具权限配置（默认空）。
        # 一次性加载全部启用权限并按 agent_id 分组缓存，避免逐 Agent N+1 查询
        # （注册 100+ 个文件 Agent 时，逐个查询会放大连接开销）
        cache_expired = (
            time.monotonic() - getattr(self, '_mcp_patterns_cache_loaded_at', 0.0)
            >= MCP_PATTERNS_CACHE_TTL_SECONDS
        )
        if self._mcp_patterns_cache is None or cache_expired:
            self._mcp_patterns_cache = self._load_mcp_patterns()
            self._mcp_patterns_cache_loaded_at = time.monotonic()
        mcp_patterns = self._mcp_patterns_cache.get(agent_id, [])

        return base_tools + mcp_patterns

    def _refresh_registered_agent_tools(self) -> None:
        """Recompute tools for already registered agents after permissions change.

        The filename-stem alias and the frontmatter name intentionally share one
        registration dictionary.  Refresh each dictionary once so aliases cannot
        observe different snapshots and a large agent directory does not trigger
        duplicate permission queries.
        """
        refreshed: set[int] = set()
        for registration in self.registered_agents.values():
            registration_id = id(registration)
            if registration_id in refreshed:
                continue
            refreshed.add(registration_id)
            agent_id = registration.get("name")
            if agent_id:
                registration["tools"] = self._get_agent_tools(agent_id)

    @staticmethod
    def _load_mcp_patterns() -> Dict[str, List[str]]:
        """加载所有启用的 MCP 工具权限，按 agent_id 分组。

        Returns:
            agent_id -> 工具模式列表的映射；查询失败时返回空映射（无 MCP 权限）。
        """
        try:
            from models import AgentMcpPermission
            rows = db.query(AgentMcpPermission).filter_by(enabled=True).all()
            grouped: Dict[str, List[str]] = {}
            for row in rows:
                grouped.setdefault(row.agent_id, []).append(row.mcp_tool_pattern)
            return grouped
        except Exception:
            return {}

    @staticmethod
    def _is_knowledge_available(user_id: Optional[int] = None) -> bool:
        """检查知识图谱是否有数据可检索。

        Args:
            user_id: 用户 ID。若提供，检查该用户的图谱文件；若为 None（如 Agent
                注册阶段无用户上下文），扫描 KNOWLEDGE_DATA_DIR 是否存在任意用户图谱，
                以保留注册时为 Agent 分配 knowledge_search 工具的既有行为。
        """
        try:
            from config import Config
            import os
            from glob import glob

            if user_id is not None:
                graph_path = Config.get_user_graph_path(user_id)
                return (
                    os.path.exists(graph_path)
                    and os.path.getsize(graph_path) > 10
                )

            # 注册阶段无 user_id：扫描知识库目录是否存在任意有效用户图谱
            pattern = os.path.join(Config.KNOWLEDGE_DATA_DIR, 'user_*_graph.json')
            for path in glob(pattern):
                try:
                    if os.path.getsize(path) > 10:
                        return True
                except OSError:
                    continue
            return False
        except Exception:
            return False

    @staticmethod
    def _filter_tool_registry(full_registry, allowed_tools: set) -> "ToolRegistry":
        """创建只包含允许工具的 ToolRegistry 子集。

        支持通配符匹配：mcp__exa__* 匹配所有 exa MCP 工具。

        Args:
            full_registry: 完整的 ToolRegistry
            allowed_tools: 允许的工具名称集合（支持通配符）

        Returns:
            过滤后的 ToolRegistry
        """
        from openharness.tools.base import ToolRegistry
        import fnmatch

        filtered = ToolRegistry()
        for tool in full_registry.list_tools():
            # 支持通配符匹配
            if any(fnmatch.fnmatch(tool.name, pattern) for pattern in allowed_tools):
                filtered.register(tool)
        return filtered

    # ------------------------------------------------------------------
    # 辅助方法：从 execute_agent 提取，消除嵌套闭包
    # ------------------------------------------------------------------

    @staticmethod
    def _cfg(app_config, key: str, default=None):
        """兼容 dict 和 Config 类两种访问方式。"""
        if isinstance(app_config, dict):
            return app_config.get(key, default)
        return getattr(app_config, key, default)

    def _get_app_config(self):
        """获取应用配置（注入配置或回退到 Config 类）。"""
        if self._config:
            return self._config
        from config import Config
        return Config()

    def _create_fallback_llm_service(self, app_config) -> "LLMService":
        """Create a fresh DB-backed service for non-workflow callers.

        Leader workflows inject their request-scoped service. Avoiding a global
        cache here ensures standalone calls observe model/key admin updates.
        """
        from services.llm_service import create_llm_service
        return create_llm_service(
            self._cfg(app_config, 'LLM_MODEL'),
            agents_dir=self.agents_dir,
            workspace_dir=self._cfg(app_config, 'WORKSPACE_DIR', 'data/workspace'),
        )

    def _ensure_tool_registry(self, app_config):
        """初始化或复用缓存的完整 ToolRegistry。"""
        if self._cached_full_registry is None:
            from .harness_adapter import HarnessToolRegistry
            self._cached_full_registry = HarnessToolRegistry(
                workspace_dir=self._cfg(app_config, 'WORKSPACE_DIR', 'data/workspace')
            ).oh_registry
        return self._cached_full_registry

    def _prepare_messages(
        self,
        task: str,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> list:
        """构建 ConversationMessage 列表（历史 + 当前任务）。"""
        from openharness.engine.messages import ConversationMessage

        messages = []
        if history:
            for msg in history:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "user":
                    messages.append(ConversationMessage.from_user_text(content))
                elif role == "assistant":
                    messages.append(ConversationMessage(role="assistant", text=content))
        messages.append(ConversationMessage.from_user_text(task))
        return messages

    def _build_query_context(
        self,
        app_config,
        agent_config: Dict[str, Any],
        agent_id: str,
        user_id: Optional[int] = None,
        llm_service: Optional["LLMService"] = None,
    ):
        """构建 OpenHarness QueryContext。"""
        from .openharness_llm_client import OpenHarnessLLMClient
        from .openharness_permission_checker import OpenHarnessPermissionChecker, get_agent_type_from_id
        from openharness.engine.query import QueryContext
        from openharness.permissions.modes import PermissionMode

        llm_service = llm_service or self._create_fallback_llm_service(app_config)
        api_client = OpenHarnessLLMClient(llm_service, model=llm_service.model)

        agent_type = get_agent_type_from_id(agent_id)
        permission_checker = OpenHarnessPermissionChecker(
            agent_tools=set(agent_config["tools"]),
            mode=PermissionMode.DEFAULT,
        )

        full_registry = self._ensure_tool_registry(app_config)
        agent_tools = set(agent_config["tools"])
        tool_registry = self._filter_tool_registry(full_registry, agent_tools)

        # 日志：工具数量
        try:
            api_schemas = tool_registry.to_api_schema()
            logger.info(f"tool_registry.to_api_schema() -> {len(api_schemas)} tools")
        except Exception as e:
            logger.error(f"tool_registry.to_api_schema() FAILED: {e}")

        cwd = Path(self._cfg(app_config, 'WORKSPACE_DIR', 'data/workspace'))
        model = agent_config.get("model", "inherit")
        if model == "inherit":
            model = llm_service.model

        max_tokens = self._cfg(app_config, 'LLM_MAX_TOKENS') or llm_service.get_max_output_tokens()
        max_turns = 5

        tool_metadata = {"user_id": user_id} if user_id is not None else {}
        query_context = QueryContext(
            api_client=api_client,
            tool_registry=tool_registry,
            permission_checker=permission_checker,
            cwd=cwd,
            model=model,
            system_prompt=agent_config.get("system_prompt", ""),
            max_tokens=max_tokens,
            max_turns=max_turns,
            tool_metadata=tool_metadata,
        )

        try:
            ctx_tools = query_context.tool_registry.to_api_schema()
            logger.debug(f"QueryContext created with {len(ctx_tools)} tools in registry")
        except Exception as e:
            logger.error(f"QueryContext tool_registry.to_api_schema() FAILED: {e}")

        return query_context, max_turns

    async def _execute_async(
        self,
        query_context,
        messages: list,
        agent_id: str,
        agent_config: Dict[str, Any],
        max_turns: int,
        event_callback: Optional[callable] = None,
    ) -> tuple:
        """执行 run_query 协程，返回 (content, tool_calls, total_tokens)。"""
        from openharness.engine.stream_events import (
            AssistantTextDelta,
            ToolExecutionStarted,
            ToolExecutionCompleted,
        )
        from openharness.engine.query import MaxTurnsExceeded, run_query

        content_parts: List[str] = []
        tool_calls: List[Dict[str, Any]] = []
        total_tokens = 0

        try:
            async for event, usage in run_query(query_context, messages):
                if isinstance(event, AssistantTextDelta):
                    content_parts.append(event.text)
                elif isinstance(event, ToolExecutionStarted):
                    tool_calls.append({
                        "tool": event.tool_name,
                        "input": event.tool_input,
                    })
                    if event_callback:
                        try:
                            event_callback({
                                "type": "tool_call_started",
                                "agent_id": agent_id,
                                "agent_name": agent_config.get("name", agent_id),
                                "tool_name": event.tool_name,
                                "tool_input": event.tool_input,
                            })
                        except Exception:
                            logger.debug("event_callback error for tool_call_started", exc_info=True)
                elif isinstance(event, ToolExecutionCompleted):
                    if tool_calls:
                        tool_calls[-1]["output"] = event.output
                    if event_callback:
                        try:
                            output_summary = str(event.output) if event.output else ""
                            event_callback({
                                "type": "tool_call_completed",
                                "agent_id": agent_id,
                                "agent_name": agent_config.get("name", agent_id),
                                "tool_name": event.tool_name,
                                "tool_output_summary": output_summary,
                                "is_error": getattr(event, 'is_error', False),
                            })
                        except Exception:
                            logger.debug("event_callback error for tool_call_completed", exc_info=True)

                if usage:
                    total_tokens = usage.total_tokens
        except MaxTurnsExceeded:
            logger.warning(
                f"Agent {agent_id} reached max_turns={max_turns}, "
                f"returning {len(content_parts)} text parts, {len(tool_calls)} tool calls"
            )

        return "".join(content_parts), tool_calls, total_tokens

    # ------------------------------------------------------------------
    # 主编排方法
    # ------------------------------------------------------------------

    def execute_agent(
        self,
        agent_id: str,
        task: str,
        context: Optional[Dict[str, Any]] = None,
        history: Optional[List[Dict[str, str]]] = None,
        event_callback: Optional[callable] = None,
        user_id: Optional[int] = None,
        llm_service: Optional["LLMService"] = None,
    ) -> Dict[str, Any]:
        """Execute a single agent with tool access.

        This method integrates OpenHarness run_query engine for actual agent execution
        with tool support, token tracking, and execution time measurement.

        Args:
            agent_id: ID of the agent to execute.
            task: Task description for the agent.
            context: Execution context (files, state, etc.).
            history: Conversation history.
            event_callback: Optional callback for real-time tool call events.
                Called with dict: {type, agent_id, tool_name, ...}
            llm_service: Request/workflow-scoped LLM service. Standalone callers
                may omit it and resolve the current database default per call.

        Returns:
            Execution result dictionary with:
            - success: Whether execution was successful
            - content: Agent output content
            - tool_calls: List of tool invocations made
            - tokens_used: Total tokens consumed
            - execution_time: Time taken in seconds
            - error: Error message if failed

        Raises:
            ValueError: If agent is not registered.
        """
        if agent_id not in self.registered_agents:
            raise ValueError(f"Agent '{agent_id}' not registered")

        agent_config = self.registered_agents[agent_id]
        logger.info(f"Executing agent: {agent_id}, tools={agent_config.get('tools', [])}, "
                    f"openharness={self.agent_definition_class is not None}")

        start_time = time.time()

        try:
            # Check if OpenHarness is available
            if not self.agent_definition_class:
                return self._execute_agent_legacy(agent_id, task, context, history)

            # 1. 配置
            app_config = self._get_app_config()

            # 2. 构建 QueryContext
            query_context, max_turns = self._build_query_context(
                app_config, agent_config, agent_id, user_id, llm_service
            )

            # 3. 构建消息
            messages = self._prepare_messages(task, history)

            # 4. 异步执行
            from utils.async_utils import safe_async_run
            content, tool_calls, tokens_used = safe_async_run(
                self._execute_async(
                    query_context, messages,
                    agent_id, agent_config, max_turns, event_callback,
                )
            )

            execution_time = time.time() - start_time

            result = {
                "success": True,
                "status": "completed",
                "agent_id": agent_id,
                "content": content,
                "tool_calls": tool_calls,
                "tokens_used": tokens_used,
                "execution_time": execution_time,
                "error": None,
            }

            logger.info(
                f"Agent {agent_id} executed successfully: "
                f"{len(tool_calls)} tool calls, "
                f"{tokens_used} tokens, "
                f"{execution_time:.2f}s"
            )

            return result

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Agent {agent_id} execution failed: {e}", exc_info=True)

            return {
                "success": False,
                "status": "failed",
                "agent_id": agent_id,
                "content": "",
                "tool_calls": [],
                "tokens_used": 0,
                "execution_time": execution_time,
                "error": str(e),
            }

    def _execute_agent_legacy(
        self,
        agent_id: str,
        task: str,
        context: Optional[Dict[str, Any]] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """Legacy execution fallback when OpenHarness is not available.

        Args:
            agent_id: Agent ID
            task: Task description
            context: Execution context
            history: Conversation history

        Returns:
            Execution result with framework_ready status
        """
        agent_config = self.registered_agents[agent_id]

        return {
            "success": True,
            "status": "framework_ready",
            "agent_id": agent_id,
            "content": "",
            "tool_calls": [],
            "tokens_used": 0,
            "execution_time": 0,
            "error": None,
            "message": "OpenHarness not available - framework ready",
            "tools_available": agent_config["tools"],
        }

    def execute_team(
        self,
        agents: List[str],
        task: str,
        parallel: bool = True,
        context: Optional[Dict[str, Any]] = None,
        event_callback: Optional[callable] = None,
    ) -> List[Dict[str, Any]]:
        """Execute multiple agents as a team.

        Args:
            agents: List of agent IDs to execute.
            task: Task description for the team.
            parallel: Whether to execute agents in parallel.
            context: Shared execution context.
            event_callback: Optional callback for real-time tool call events.

        Returns:
            List of execution results from each agent.
        """
        logger.info(f"Executing team of {len(agents)} agents (parallel={parallel})")

        # Create team in registry if available
        if self.team_registry:
            team_name = f"team-{task[:20].replace(' ', '-')}"
            try:
                self.team_registry.create_team(name=team_name, description=task)
                for agent_id in agents:
                    self.team_registry.add_agent(team_name, agent_id)
                logger.info(f"Created team: {team_name}")
            except Exception as e:
                logger.warning(f"Failed to create team in registry: {e}")

        results = []

        if parallel:
            # Execute agents in parallel using ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=len(agents)) as executor:
                futures = [
                    executor.submit(
                        self.execute_agent, agent_id, task, context, None, event_callback
                    )
                    for agent_id in agents
                ]
                results = [future.result() for future in futures]
        else:
            # Execute agents sequentially
            for agent_id in agents:
                result = self.execute_agent(agent_id, task, context, None, event_callback)
                results.append(result)

        logger.info(f"Team execution completed: {len(results)} results")
        return results

    def get_agent_info(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a registered agent.

        Args:
            agent_id: Agent identifier.

        Returns:
            Agent configuration dictionary, or None if not found.
        """
        return self.registered_agents.get(agent_id)

    def list_agents(self) -> List[str]:
        """List all registered agent IDs.

        Returns:
            List of agent IDs.
        """
        return list(self.registered_agents.keys())


# Global coordinator instance
_coordinator_instance: Optional[HarnessCoordinator] = None
_coordinator_lock = threading.Lock()


def get_harness_coordinator(config: Optional[Dict[str, Any]] = None) -> HarnessCoordinator:
    """Get the global HarnessCoordinator instance.

    Args:
        config: 应用配置 dict，首次调用时传入

    Returns:
        Global HarnessCoordinator instance.
    """
    global _coordinator_instance
    if _coordinator_instance is None:
        with _coordinator_lock:
            # Double-check locking pattern
            if _coordinator_instance is None:
                _coordinator_instance = HarnessCoordinator(config=config)
    return _coordinator_instance


# Agent 类型关键词（用于 MCP 权限批量配置）
MEDICAL_KEYWORDS = [
    "surgery", "expert", "medicine", "doctor",
    "cardiology", "neurology", "pediatrics", "oncology",
    "gynecology", "orthopedics", "psychiatry", "radiology",
    "中医", "针灸", "推拿", "护理", "全科", "肿瘤", "康复",
    "内科", "外科", "妇科", "儿科", "眼科", "耳鼻喉", "口腔", "皮肤"
]

TECHNICAL_KEYWORDS = [
    "developer", "devops", "fullstack", "qa",
    "backend", "frontend", "engineer", "architect",
    "全栈", "运维", "测试", "技术"
]


def get_agent_type_from_id(agent_id: str) -> str:
    """判断 Agent 类型。

    Args:
        agent_id: Agent 名称或 ID

    Returns:
        'medical' | 'technical' | 'business'
    """
    agent_lower = agent_id.lower()

    if any(kw in agent_lower for kw in MEDICAL_KEYWORDS):
        return 'medical'
    elif any(kw in agent_lower for kw in TECHNICAL_KEYWORDS):
        return 'technical'
    else:
        return 'business'


def get_agents_by_type(agent_type: str) -> List[str]:
    """获取某类型的所有已注册 Agent ID。

    Args:
        agent_type: 'medical' | 'technical' | 'business'

    Returns:
        该类型的 Agent ID 列表
    """
    coordinator = get_harness_coordinator()
    all_agents = coordinator.list_agents()

    return [
        agent_id for agent_id in all_agents
        if get_agent_type_from_id(agent_id) == agent_type
    ]


def clear_registry_cache() -> None:
    """清除 ToolRegistry 缓存，使配置变更生效。

    由 PUT /api/admin/agents/{id}/mcp-tools 调用。
    """
    global _coordinator_instance
    if _coordinator_instance:
        _coordinator_instance._cached_full_registry = None
        _coordinator_instance._mcp_patterns_cache = None
        _coordinator_instance._mcp_patterns_cache_loaded_at = 0.0
        _coordinator_instance._refresh_registered_agent_tools()
        logger.info(
            "ToolRegistry and MCP permission caches cleared; registered agent tools refreshed"
        )
