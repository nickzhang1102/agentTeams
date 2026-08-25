"""
Custom Web Search Tool - 包装旧 WebSearchHandler 为 OpenHarness Tool

优先级：Exa > Tavily（移除 DuckDuckGo）
"""
import logging
from pydantic import BaseModel, Field
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult

logger = logging.getLogger(__name__)


class WebSearchInput(BaseModel):
    """Web 搜索输入"""
    query: str = Field(..., description="搜索查询")


class ExaWebSearchTool(BaseTool):
    """Web 搜索工具（Exa/Tavily，移除 DuckDuckGo）"""

    def __init__(self):
        super().__init__()
        self.name = "web_search"
        self.description = "Search the web using Exa or Tavily API"
        self.input_model = WebSearchInput

        # 导入旧 WebSearchHandler
        from services.tools_registry import WebSearchHandler
        self.handler = WebSearchHandler()

    async def execute(
        self,
        input_data,
        context: ToolExecutionContext
    ) -> ToolResult:
        """执行搜索"""
        try:
            # 提取 query 参数
            query = input_data.query if hasattr(input_data, 'query') else str(input_data)

            result = self.handler.execute(query=query)

            if result.get("success"):
                return ToolResult(
                    output=result.get("result", ""),
                    is_error=False,
                    metadata={
                        "citations": result.get("citations", []),
                        "evidence_items": result.get("evidence_items", []),
                    }
                )
            else:
                error_msg = result.get("error", "Search failed")
                return ToolResult(
                    output=f"web_search failed: {error_msg}",
                    is_error=True
                )
        except Exception as e:
            logger.error(f"ExaWebSearchTool exception: {e}", exc_info=True)
            return ToolResult(
                output=f"web_search failed: {str(e)}",
                is_error=True
            )
