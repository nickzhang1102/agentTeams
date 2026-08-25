"""
FastAPI Tools API 路由模块

实现工具查询 API：
- GET / - 获取所有工具列表
- GET /{tool_name} - 获取单个工具详情
- POST /execute - 执行工具（受限）
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import get_current_user, get_admin_user
from services.tools_registry import get_tools_registry

logger = logging.getLogger(__name__)

# 创建 Tools 路由
router = APIRouter(prefix="/api/tools", tags=["tools"])

# 敏感工具列表 - 这些工具需要特别注意权限控制
SENSITIVE_TOOLS = {
    'file_write': '文件写入可能修改系统文件',
}


class ToolsListResponse(BaseModel):
    success: bool
    tools: list


class ToolDetailResponse(BaseModel):
    success: bool
    tool: Optional[dict] = None


class ExecuteRequest(BaseModel):
    tool_name: str = Field(..., min_length=1)
    tool_input: dict = Field(default_factory=dict)


class ExecuteResponse(BaseModel):
    success: bool
    result: Optional[str] = None
    error: Optional[str] = None


@router.get("", response_model=ToolsListResponse)
async def get_tools(
    user = Depends(get_current_user)
):
    """获取所有可用的工具列表"""
    try:
        registry = get_tools_registry()
        tools = registry.list_tools()
        return {
            "success": True,
            "tools": tools
        }
    except Exception as e:
        logger.error(f"Get tools failed: {e}", exc_info=True)
        return {
            "success": False,
            "tools": []
        }


@router.get("/{tool_name}", response_model=ToolDetailResponse)
async def get_tool(
    tool_name: str,
    user = Depends(get_current_user)
):
    """获取单个工具的详细信息"""
    try:
        registry = get_tools_registry()

        if tool_name not in registry.tools:
            return {
                "success": False,
                "tool": None
            }

        tool = registry.tools[tool_name]
        return {
            "success": True,
            "tool": {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema
            }
        }
    except Exception as e:
        logger.error(f"Get tool failed: {e}", exc_info=True)
        return {
            "success": False,
            "tool": None
        }


@router.post("/execute", response_model=ExecuteResponse)
async def execute_tool(
    request: ExecuteRequest,
    admin = Depends(get_admin_user)
):
    """
    手动执行工具（仅供管理员测试使用）

    注意：此端点可触发 file_read/file_write 等文件类工具，
    必须限制为管理员；工具调用主要通过 Claude 服务进行。
    """
    try:
        registry = get_tools_registry()

        # 检查工具是否存在
        if request.tool_name not in registry.tools:
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": f"Tool not found: {request.tool_name}"
                }
            )

        # 记录敏感工具的执行（审计日志）
        if request.tool_name in SENSITIVE_TOOLS:
            logger.info(f"Executing sensitive tool: {request.tool_name}, input: {request.tool_input}")

        result = registry.execute_tool(request.tool_name, request.tool_input)

        return {
            "success": result.get("success", False),
            "result": result.get("result"),
            "error": result.get("error")
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Execute tool failed: {e}", exc_info=True)
        return {
            "success": False,
            "result": None,
            "error": str(e)
        }