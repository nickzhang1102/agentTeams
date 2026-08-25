"""
FastAPI MCP API 路由模块

实现 MCP 服务器管理 API：
- GET /servers - 获取所有 MCP 服务器配置
- POST /servers/{server_name}/connect - 连接服务器
- POST /servers/{server_name}/disconnect - 断开服务器
- GET /tools - 获取所有 MCP 工具
- GET /resources - 获取所有 MCP 资源
- GET /resources/{resource_uri} - 获取资源内容
- GET /connections - 获取所有连接状态
"""
import logging
from typing import Optional, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import get_current_user, get_admin_user
from services.mcp.mcp_config import get_mcp_config
from services.mcp.mcp_client import get_mcp_client

logger = logging.getLogger(__name__)

# 创建 MCP 路由
router = APIRouter(prefix="/api/mcp", tags=["mcp"])


class ServersResponse(BaseModel):
    success: bool
    servers: list


class ConnectResponse(BaseModel):
    success: bool
    message: Optional[str] = None
    tools_count: Optional[int] = None
    resources_count: Optional[int] = None


class DisconnectResponse(BaseModel):
    success: bool
    message: str


class ToolsResponse(BaseModel):
    success: bool
    tools: list


class ResourcesResponse(BaseModel):
    success: bool
    resources: list


class ResourceContentResponse(BaseModel):
    success: bool
    content: Optional[Any] = None
    mime_type: Optional[str] = None


class ConnectionsResponse(BaseModel):
    success: bool
    connections: list


@router.get("/servers", response_model=ServersResponse)
async def get_servers(
    admin = Depends(get_admin_user)
):
    """获取所有 MCP 服务器配置（含 env/headers 凭证，仅管理员可用）"""
    try:
        config = get_mcp_config()
        servers = config.list_servers()

        # 添加连接状态
        client = get_mcp_client()
        connections = {c["server_name"]: c for c in client.list_connections()}

        for server in servers:
            server["connected"] = server["name"] in connections

        return {
            "success": True,
            "servers": servers
        }
    except Exception as e:
        logger.error(f"Get MCP servers failed: {e}", exc_info=True)
        return {
            "success": False,
            "servers": []
        }


@router.post("/servers/{server_name}/connect", response_model=ConnectResponse)
async def connect_server(
    server_name: str,
    user = Depends(get_admin_user)
):
    """连接到 MCP 服务器"""
    try:
        config = get_mcp_config()
        server = config.get_server(server_name)

        if not server:
            raise HTTPException(
                status_code=404,
                detail={"success": False, "error": f"Server not found: {server_name}"}
            )

        if server.disabled:
            raise HTTPException(
                status_code=400,
                detail={"success": False, "error": f"Server is disabled: {server_name}"}
            )

        client = get_mcp_client()

        if server.transport == "stdio":
            success = client.connect_stdio(
                server_name,
                server.command,
                server.args,
                server.env
            )
        elif server.transport == "sse":
            success = await client.connect_sse(server_name, server.url, headers=server.headers)
        else:
            raise HTTPException(
                status_code=400,
                detail={"success": False, "error": f"Unknown transport: {server.transport}"}
            )

        if success:
            return {
                "success": True,
                "message": f"Connected to {server_name}",
                "tools_count": len([t for t in client.tools.values() if t.server_name == server_name]),
                "resources_count": len([r for r in client.resources.values() if r.server_name == server_name])
            }
        else:
            raise HTTPException(
                status_code=500,
                detail={"success": False, "error": f"Failed to connect to {server_name}"}
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Connect to MCP server failed: {e}", exc_info=True)
        return {
            "success": False,
            "message": str(e)
        }


@router.post("/servers/{server_name}/disconnect", response_model=DisconnectResponse)
async def disconnect_server(
    server_name: str,
    user = Depends(get_admin_user)
):
    """断开与 MCP 服务器的连接"""
    try:
        client = get_mcp_client()
        client.disconnect(server_name)

        return {
            "success": True,
            "message": f"Disconnected from {server_name}"
        }
    except Exception as e:
        logger.error(f"Disconnect from MCP server failed: {e}", exc_info=True)
        return {
            "success": False,
            "message": str(e)
        }


@router.get("/tools", response_model=ToolsResponse)
async def get_tools(
    user = Depends(get_current_user)
):
    """获取所有 MCP 工具"""
    try:
        client = get_mcp_client()
        tools = client.list_tools()

        return {
            "success": True,
            "tools": tools
        }
    except Exception as e:
        logger.error(f"Get MCP tools failed: {e}", exc_info=True)
        return {
            "success": False,
            "tools": []
        }


@router.get("/resources", response_model=ResourcesResponse)
async def get_resources(
    user = Depends(get_current_user)
):
    """获取所有 MCP 资源"""
    try:
        client = get_mcp_client()
        resources = client.list_resources()

        return {
            "success": True,
            "resources": resources
        }
    except Exception as e:
        logger.error(f"Get MCP resources failed: {e}", exc_info=True)
        return {
            "success": False,
            "resources": []
        }


@router.get("/resources/{resource_uri:path}", response_model=ResourceContentResponse)
async def get_resource_content(
    resource_uri: str,
    user = Depends(get_admin_user)
):
    """获取 MCP 资源内容"""
    try:
        client = get_mcp_client()
        result = await client.get_resource_async(resource_uri)

        if result.get("success"):
            return result
        else:
            raise HTTPException(
                status_code=404,
                detail=result
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get MCP resource content failed: {e}", exc_info=True)
        return {
            "success": False,
            "content": None,
            "mime_type": None
        }


@router.get("/connections", response_model=ConnectionsResponse)
async def get_connections(
    user = Depends(get_current_user)
):
    """获取所有 MCP 连接状态"""
    try:
        client = get_mcp_client()
        connections = client.list_connections()

        return {
            "success": True,
            "connections": connections
        }
    except Exception as e:
        logger.error(f"Get MCP connections failed: {e}", exc_info=True)
        return {
            "success": False,
            "connections": []
        }