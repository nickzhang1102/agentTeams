"""
OpenHarness 适配层

封装 OpenHarness 核心功能，提供统一的适配接口
"""
from typing import Dict, List, Any, Optional
import logging
import asyncio

logger = logging.getLogger(__name__)


class HarnessToolRegistry:
    """OpenHarness 工具注册适配器"""

    def __init__(self, workspace_dir: str, config: Optional[Dict] = None):
        """
        初始化工具注册

        Args:
            workspace_dir: 工作空间目录
            config: 配置字典
        """
        self.workspace_dir = workspace_dir
        self.config = config or {}

        # 延迟导入 OpenHarness（避免未安装时报错）
        try:
            from openharness.tools import ToolRegistry as OHToolRegistry
            self.oh_registry = OHToolRegistry()
            logger.info("OpenHarness ToolRegistry initialized")
        except ImportError as e:
            logger.error(f"Failed to import OpenHarness: {e}")
            raise

        # 配置启用的工具并注册
        self._register_tools()

    def _register_tools(self):
        """动态注册所有 OpenHarness 工具"""
        import pkgutil
        import openharness.tools

        registered_count = 0
        total_modules = 0

        # 动态发现所有工具模块
        for importer, modname, ispkg in pkgutil.iter_modules(openharness.tools.__path__):
            if not modname.endswith('_tool') or modname == 'base':
                continue

            total_modules += 1

            try:
                # 动态导入模块
                module_path = f'openharness.tools.{modname}'
                module = __import__(module_path, fromlist=[''])

                # 推断工具类名（模块名转换为驼峰）
                # 例如：bash_tool -> BashTool, file_read_tool -> FileReadTool
                class_name = ''.join(
                    word.capitalize()
                    for word in modname[:-5].split('_')  # 去掉 '_tool' 后缀
                ) + 'Tool'

                # 获取工具类
                tool_class = getattr(module, class_name)

                # 实例化并注册工具
                tool_instance = tool_class()
                self.oh_registry.register(tool_instance)

                registered_count += 1
                logger.debug(f"Registered tool: {tool_instance.name} ({class_name})")

            except ImportError as e:
                logger.warning(f"Failed to import tool module {modname}: {e}")
            except AttributeError as e:
                logger.debug(f"Tool class {class_name} not found in {module_path}: {e}")
            except TypeError as e:
                # 某些工具需要依赖参数（如 MCP 工具需要 manager）
                logger.debug(f"Tool {modname} requires dependencies, skipping: {e}")
            except RuntimeError as e:
                # 工具运行时初始化错误
                logger.debug(f"Tool {modname} initialization failed: {e}")

        logger.info(f"Registered {registered_count}/{total_modules} tools from OpenHarness")

        # 注册自定义工具覆盖默认实现
        self._register_custom_tools()

    def _register_custom_tools(self):
        """注册自定义工具，覆盖 OpenHarness 默认实现"""
        try:
            from custom_web_search_tool import ExaWebSearchTool
            tool = ExaWebSearchTool()
            self.oh_registry.register(tool)
            logger.info(f"Registered custom tool: {tool.name} (ExaWebSearchTool, overrides default DuckDuckGo)")
        except ImportError as e:
            logger.warning(f"Custom web_search tool not available: {e}")
        except Exception as e:
            logger.warning(f"Failed to register custom web_search tool: {e}")

        # 注册 MCP 工具
        self._register_mcp_tools()

        # 注册知识图谱搜索工具
        self._register_knowledge_search_tool()

    def _register_knowledge_search_tool(self) -> None:
        """注册知识图谱搜索工具"""
        try:
            from custom_knowledge_search_tool import KnowledgeSearchTool
            tool = KnowledgeSearchTool()
            self.oh_registry.register(tool)
            logger.info(f"Registered custom tool: {tool.name} (KnowledgeSearchTool)")
        except ImportError as e:
            logger.warning(f"KnowledgeSearchTool not available: {e}")
        except Exception as e:
            logger.warning(f"Failed to register knowledge_search tool: {e}")

    def _register_mcp_tools(self) -> None:
        """注册 MCP 工具到 ToolRegistry。

        从 MCP manager 获取工具列表，使用 McpToolAdapter 包装后注册。
        注册所有 MCP 工具，具体 Agent 权限由 _get_agent_tools() 控制。
        """
        try:
            from services.mcp.mcp_manager import is_mcp_initialized, get_mcp_manager
            from openharness.tools.mcp_tool import McpToolAdapter

            if not is_mcp_initialized():
                logger.warning("MCP not initialized, skipping MCP tool registration")
                return

            manager = get_mcp_manager()
            mcp_tools = manager.list_tools()

            registered_count = 0
            for tool_info in mcp_tools:
                adapter = McpToolAdapter(manager, tool_info)
                self.oh_registry.register(adapter)
                registered_count += 1
                logger.debug(f"Registered MCP tool: {adapter.name}")

            logger.info(f"Registered {registered_count} MCP tools from {len(mcp_tools)} available")

        except ImportError as e:
            logger.warning(f"MCP tool registration failed (import): {e}")
        except Exception as e:
            logger.error(f"MCP tool registration error: {e}")

    def list_tools(self) -> List[Dict]:
        """
        列出可用工具

        Returns:
            工具列表，每个工具包含 name、description、input_schema
        """
        try:
            # 使用 to_api_schema() 方法获取所有工具 schema
            return self.oh_registry.to_api_schema()
        except AttributeError as e:
            logger.error(f"ToolRegistry API schema method failed: {e}")
            return []
        except RuntimeError as e:
            logger.error(f"ToolRegistry runtime error: {e}")
            return []

    def get_tool_schema(self, tool_name: str) -> Optional[Dict]:
        """
        获取单个工具的 schema

        Args:
            tool_name: 工具名称

        Returns:
            工具 schema 字典，如果不存在返回 None
        """
        try:
            tool = self.oh_registry.get(tool_name)
            if tool:
                return tool.to_api_schema()
            return None
        except AttributeError as e:
            logger.error(f"Tool {tool_name} API schema method failed: {e}")
            return None
        except RuntimeError as e:
            logger.error(f"Tool {tool_name} runtime error: {e}")
            return None

    def execute_tool(
        self,
        tool_name: str,
        params: Dict[str, Any],
        timeout: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict:
        """
        执行工具

        Args:
            tool_name: 工具名称
            params: 工具参数
            timeout: 超时时间（秒），None 表示不限时

        Returns:
            执行结果，包含 success、result、error、metadata
        """
        from utils.async_utils import safe_async_run

        try:
            tool = self.oh_registry.get(tool_name)
            if not tool:
                return {
                    'success': False,
                    'error': f"Tool '{tool_name}' not found"
                }

            # 从工具的 input_model 创建参数实例
            if hasattr(tool, 'input_model'):
                input_model = tool.input_model(**params)
            else:
                raise ValueError(f"Tool '{tool_name}' has no input_model")

            # 准备执行上下文
            from openharness.tools.base import ToolExecutionContext
            from pathlib import Path

            exec_metadata = dict(metadata) if metadata else {}
            if timeout:
                exec_metadata['timeout'] = timeout
            context = ToolExecutionContext(
                cwd=Path(self.workspace_dir),
                metadata=exec_metadata
            )

            # 执行工具（带真实超时）
            if timeout and timeout > 0:
                from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
                with ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(
                        safe_async_run,
                        tool.execute(input_model, context)
                    )
                    try:
                        result = future.result(timeout=timeout)
                    except FutureTimeout:
                        logger.error(f"Tool '{tool_name}' execution timed out after {timeout}s")
                        return {
                            'success': False,
                            'error': f"工具执行超时（{timeout}秒）",
                            'metadata': {'tool': tool_name, 'is_error': True, 'timeout': True}
                        }
            else:
                result = safe_async_run(tool.execute(input_model, context))

            return {
                'success': not result.is_error,
                'result': result.output,
                'error': result.output if result.is_error else None,
                'metadata': {
                    'tool': tool_name,
                    'is_error': result.is_error,
                    **result.metadata
                }
            }
        except ImportError as e:
            logger.error(f"Failed to import tool dependencies: {e}")
            return {'success': False, 'error': f"Tool dependencies not available: {e}"}
        except ValueError as e:
            logger.error(f"Invalid parameters for tool {tool_name}: {e}")
            return {'success': False, 'error': f"Invalid parameters: {e}"}
        except Exception as e:
            logger.exception(f"Unexpected error executing tool {tool_name}")
            return {'success': False, 'error': f"Execution failed: {e}"}


# 全局实例
_harness_registry = None


def get_harness_tool_registry(
    workspace_dir: str,
    config: Optional[Dict] = None
) -> HarnessToolRegistry:
    """
    获取全局工具注册实例

    Args:
        workspace_dir: 工作空间目录
        config: 配置

    Returns:
        HarnessToolRegistry 实例
    """
    global _harness_registry
    if _harness_registry is None:
        _harness_registry = HarnessToolRegistry(workspace_dir, config)
    return _harness_registry
