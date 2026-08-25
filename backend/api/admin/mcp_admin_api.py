"""MCP / Skills / Graphify 管理子路由

从 admin_api.py 拆出的 MCP 服务器 CRUD + 预置服务 + Graphify + Skills + Tools 端点。
路径前缀由上层 admin_api.py 的 router 统一设置为 /api/admin。
"""
import logging
import os
import time as _time
from pathlib import Path
from typing import Optional, List, Dict, Any, Any as _Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from api.deps import get_admin_user, resolve_request_locale, audit_log
from catalog.tool_descriptions import localize_tool_description
from models import SystemConfig, User


logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin"])


def _reject_database_managed_mcp_credentials(name: str, env: Optional[Dict[str, str]]) -> None:
    if name == 'exa' and env and 'EXA_API_KEY' in env:
        raise HTTPException(
            status_code=400,
            detail={
                'error': 'Database-managed credential',
                'message': 'EXA_API_KEY must be configured in System Settings',
            },
        )


def _is_system_credential_configured(db_session: Session, key: Optional[str]) -> bool:
    if not key:
        return True
    setting = db_session.query(SystemConfig).filter_by(key=key).first()
    return bool(setting and setting.value and setting.value.strip())


def _require_mcp_credential_when_enabling(
    name: str,
    disabled: Optional[bool],
    db_session: Session,
) -> None:
    if disabled is not False:
        return
    from services.mcp.mcp_config import PRESET_MCP_SERVERS

    credential_key = PRESET_MCP_SERVERS.get(name, {}).get('credential_setting_key')
    if credential_key and not _is_system_credential_configured(db_session, credential_key):
        raise HTTPException(
            status_code=400,
            detail={
                'code': 'MCP_CREDENTIAL_NOT_CONFIGURED',
                'error': 'Credential not configured',
                'message': f'{credential_key} must be configured in System Settings before enabling {name}',
                'credential_setting_key': credential_key,
            },
        )


# ==================== Pydantic Models ====================

class McpServerCreateRequest(BaseModel):
    """创建 MCP 服务器请求"""
    name: str = Field(..., min_length=1, description="服务器名称")
    transport: Optional[str] = Field(default="stdio", description="传输类型")
    command: Optional[str] = Field(default=None, description="命令")
    args: Optional[List[str]] = Field(default=[], description="参数列表")
    url: Optional[str] = Field(default=None, description="URL")
    env: Optional[Dict[str, str]] = Field(default={}, description="环境变量")
    disabled: Optional[bool] = Field(default=True, description="是否禁用")


class McpServerUpdateRequest(BaseModel):
    """更新 MCP 服务器请求"""
    transport: Optional[str] = Field(default=None, description="传输类型")
    command: Optional[str] = Field(default=None, description="命令")
    args: Optional[List[str]] = Field(default=None, description="参数列表")
    url: Optional[str] = Field(default=None, description="URL")
    env: Optional[Dict[str, str]] = Field(default=None, description="环境变量")
    disabled: Optional[bool] = Field(default=None, description="是否禁用")


# ==================== 模块级缓存 ====================

_TOOLS_CACHE: Dict[str, _Any] = {"registry": None, "ts": 0.0}
_SKILLS_CACHE: Dict[str, _Any] = {"manager": None, "ts": 0.0}
_CACHE_TTL = 60  # 秒


def _get_tools_registry_cached():
    """带 TTL 缓存的 HarnessToolRegistry 单例"""
    now = _time.time()
    if _TOOLS_CACHE["registry"] is None or now - _TOOLS_CACHE["ts"] > _CACHE_TTL:
        from services.harness.harness_adapter import HarnessToolRegistry
        from config import config as app_config
        _TOOLS_CACHE["registry"] = HarnessToolRegistry(
            workspace_dir=app_config.get('WORKSPACE_DIR', 'data/workspace')
        )
        _TOOLS_CACHE["ts"] = now
    return _TOOLS_CACHE["registry"]


def _get_skills_manager_cached():
    """带 TTL 缓存的 skills manager 单例"""
    now = _time.time()
    if _SKILLS_CACHE["manager"] is None or now - _SKILLS_CACHE["ts"] > _CACHE_TTL:
        from services.skills_manager import get_skills_manager
        _SKILLS_CACHE["manager"] = get_skills_manager()
        _SKILLS_CACHE["ts"] = now
    return _SKILLS_CACHE["manager"]


# ==================== MCP 服务器管理 API ====================

@router.get('/openharness/mcp-servers')
def get_openharness_mcp_servers(admin: User = Depends(get_admin_user)):
    """获取 MCP 服务器配置列表"""
    try:
        servers = []
        try:
            from services.mcp.mcp_config import get_mcp_config
            mcp_mgr = get_mcp_config()
            servers = mcp_mgr.list_servers()
        except Exception as e:
            logger.warning(f'Failed to list MCP servers: {e}')

        return {
            'servers': servers,
            'total': len(servers),
        }

    except Exception:
        logger.exception('Failed to fetch MCP servers')
        raise HTTPException(
            status_code=500,
            detail={'error': 'Failed to fetch MCP servers', 'message': 'An internal error occurred'}
        )


@router.post('/openharness/mcp-servers')
def create_openharness_mcp_server(
    request: McpServerCreateRequest,
    admin: User = Depends(get_admin_user),
    db_session: Session = Depends(get_db),
):
    """新增 MCP 服务器配置"""
    try:
        from services.mcp.mcp_config import McpServerConfig, get_mcp_config
        mcp_mgr = get_mcp_config()

        name = request.name.strip()
        _reject_database_managed_mcp_credentials(name, request.env)
        _require_mcp_credential_when_enabling(name, request.disabled, db_session)
        if mcp_mgr.get_server(name):
            raise HTTPException(
                status_code=409,
                detail={'error': 'Server exists', 'message': f'MCP server {name} already exists'}
            )

        server = McpServerConfig(
            name=name,
            transport=request.transport or 'stdio',
            command=request.command,
            args=request.args or [],
            url=request.url,
            env=request.env or {},
            disabled=request.disabled if request.disabled is not None else True,
        )

        mcp_mgr.add_server(server)
        if not mcp_mgr.save_config():
            raise HTTPException(
                status_code=500,
                detail={'error': 'Save failed', 'message': 'Failed to save MCP config'}
            )

        # 凭证值不落审计详情
        audit_log(
            user_id=admin.id,
            action='admin.mcp_server.create',
            resource_type='mcp_server',
            details={'name': name, 'transport': server.transport},
            db_session=db_session,
        )
        db_session.commit()

        return {'server': server.to_dict()}

    except HTTPException:
        raise
    except Exception:
        logger.exception('Failed to create MCP server')
        raise HTTPException(
            status_code=500,
            detail={'error': 'Failed to create MCP server', 'message': 'An internal error occurred'}
        )


@router.put('/openharness/mcp-servers/{name}')
def update_openharness_mcp_server(
    name: str,
    request: McpServerUpdateRequest,
    admin: User = Depends(get_admin_user),
    db_session: Session = Depends(get_db),
):
    """更新 MCP 服务器配置"""
    try:
        from services.mcp.mcp_config import get_mcp_config
        mcp_mgr = get_mcp_config()

        server = mcp_mgr.get_server(name)
        if not server:
            raise HTTPException(
                status_code=404,
                detail={'error': 'Server not found', 'message': f'MCP server {name} does not exist'}
            )

        _reject_database_managed_mcp_credentials(name, request.env)
        _require_mcp_credential_when_enabling(name, request.disabled, db_session)

        if request.transport is not None:
            server.transport = request.transport
        if request.command is not None:
            server.command = request.command
        if request.args is not None:
            server.args = request.args
        if request.url is not None:
            server.url = request.url
        if request.env is not None:
            server.env = request.env
        if request.disabled is not None:
            server.disabled = request.disabled

        if not mcp_mgr.save_config():
            raise HTTPException(
                status_code=500,
                detail={'error': 'Save failed', 'message': 'Failed to save MCP config'}
            )

        audit_log(
            user_id=admin.id,
            action='admin.mcp_server.update',
            resource_type='mcp_server',
            details={'name': name},
            db_session=db_session,
        )
        db_session.commit()

        return {'server': server.to_dict()}

    except HTTPException:
        raise
    except Exception:
        logger.exception(f'Failed to update MCP server: {name}')
        raise HTTPException(
            status_code=500,
            detail={'error': 'Failed to update MCP server', 'message': 'An internal error occurred'}
        )


@router.delete('/openharness/mcp-servers/{name}')
def delete_openharness_mcp_server(
    name: str,
    admin: User = Depends(get_admin_user),
    db_session: Session = Depends(get_db),
):
    """删除 MCP 服务器配置"""
    try:
        from services.mcp.mcp_config import get_mcp_config
        mcp_mgr = get_mcp_config()

        if not mcp_mgr.get_server(name):
            raise HTTPException(
                status_code=404,
                detail={'error': 'Server not found', 'message': f'MCP server {name} does not exist'}
            )

        mcp_mgr.remove_server(name)
        if not mcp_mgr.save_config():
            raise HTTPException(
                status_code=500,
                detail={'error': 'Save failed', 'message': 'Failed to save MCP config'}
            )

        audit_log(
            user_id=admin.id,
            action='admin.mcp_server.delete',
            resource_type='mcp_server',
            details={'name': name},
            db_session=db_session,
        )
        db_session.commit()

        return {'message': f'MCP server {name} deleted'}

    except HTTPException:
        raise
    except Exception:
        logger.exception(f'Failed to delete MCP server: {name}')
        raise HTTPException(
            status_code=500,
            detail={'error': 'Failed to delete MCP server', 'message': 'An internal error occurred'}
        )


# ==================== 预置 MCP 服务 ====================

@router.get('/openharness/mcp-presets')
def get_openharness_mcp_presets(
    admin: User = Depends(get_admin_user),
    db_session: Session = Depends(get_db),
):
    """获取预置 MCP 服务模板列表"""
    try:
        from services.mcp.mcp_config import PRESET_MCP_SERVERS, get_mcp_config

        mcp_mgr = get_mcp_config()
        existing_servers = {s.name: s for s in mcp_mgr.servers.values()}

        presets = []
        for name, template in PRESET_MCP_SERVERS.items():
            existing = existing_servers.get(name)
            is_configured = existing is not None
            is_enabled = existing and not existing.disabled
            credential_key = template.get('credential_setting_key')

            presets.append({
                'name': name,
                'description': template.get('description', ''),
                'transport': template['transport'],
                'category': template.get('category', ''),
                'is_configured': is_configured,
                'is_enabled': is_enabled,
                'credential_setting_key': credential_key,
                'credential_configured': _is_system_credential_configured(
                    db_session, credential_key
                ),
                'activation_requires_restart': True,
            })

        return {
            'presets': presets,
            'total': len(presets),
        }

    except Exception:
        logger.exception('Failed to fetch MCP presets')
        raise HTTPException(
            status_code=500,
            detail={'error': 'Failed to fetch MCP presets', 'message': 'An internal error occurred'}
        )


@router.post('/openharness/mcp-presets/{name}/enable')
def enable_openharness_mcp_preset(
    name: str,
    admin: User = Depends(get_admin_user),
    db_session: Session = Depends(get_db),
):
    """一键启用预置 MCP 服务"""
    try:
        from services.mcp.mcp_config import PRESET_MCP_SERVERS, McpServerConfig, get_mcp_config

        if name not in PRESET_MCP_SERVERS:
            raise HTTPException(
                status_code=404,
                detail={'error': 'Preset not found', 'message': f'Preset MCP service {name} does not exist'}
            )

        template = PRESET_MCP_SERVERS[name]
        credential_key = template.get('credential_setting_key')
        if not _is_system_credential_configured(db_session, credential_key):
            raise HTTPException(
                status_code=400,
                detail={
                    'code': 'MCP_CREDENTIAL_NOT_CONFIGURED',
                    'error': 'Credential not configured',
                    'message': f'{credential_key} must be configured in System Settings before enabling {name}',
                    'credential_setting_key': credential_key,
                },
            )

        mcp_mgr = get_mcp_config()

        existing = mcp_mgr.get_server(name)
        if existing:
            if existing.disabled:
                existing.disabled = False
                if not mcp_mgr.save_config():
                    raise HTTPException(
                        status_code=500,
                        detail={'error': 'Save failed', 'message': 'Failed to save MCP config'}
                    )
            return {
                'success': True,
                'already_configured': True,
                'restart_required': True,
                'message': f'MCP server {name} is configured; restart the backend to activate it'
            }

        server = McpServerConfig(
            name=name,
            transport=template['transport'],
            command=template.get('command'),
            args=template.get('args', []),
            url=template.get('url'),
            env=template.get('env', {}),
            disabled=False,
        )

        mcp_mgr.add_server(server)
        if not mcp_mgr.save_config():
            raise HTTPException(
                status_code=500,
                detail={'error': 'Save failed', 'message': 'Failed to save MCP config'}
            )

        return {
            'success': True,
            'already_configured': False,
            'restart_required': True,
            'server': server.to_dict(),
        }

    except HTTPException:
        raise
    except Exception:
        logger.exception(f'Failed to enable MCP preset: {name}')
        raise HTTPException(
            status_code=500,
            detail={'error': 'Failed to enable MCP preset', 'message': 'An internal error occurred'}
        )


# ==================== Graphify MCP 服务 API ====================

@router.get('/mcp/graphify/status')
def get_graphify_status(admin: User = Depends(get_admin_user)):
    """获取 graphify MCP 服务状态"""
    try:
        from services.mcp.mcp_config import get_mcp_config
        from config import Config

        mcp_mgr = get_mcp_config()
        server = mcp_mgr.get_server('graphify')

        graph_path = Config.get_user_graph_path(admin.id)
        graph_exists = os.path.exists(graph_path)

        stats = {}
        if graph_exists:
            try:
                import json as _json
                data = _json.loads(Path(graph_path).read_text(encoding='utf-8'))
                stats = {
                    'nodes': len(data.get('nodes', [])),
                    'edges': len(data.get('links', data.get('edges', []))),
                }
            except Exception:
                stats = {'error': 'Failed to parse graph.json'}

        return {
            'configured': server is not None,
            'enabled': server is not None and not server.disabled,
            'graph_exists': graph_exists,
            'graph_path': graph_path,
            'graph_stats': stats,
            'tools': [
                'query_graph',
                'get_node',
                'get_neighbors',
                'get_community',
                'god_nodes',
                'graph_stats',
                'shortest_path',
            ]
        }

    except Exception:
        logger.exception('Failed to get graphify status')
        raise HTTPException(
            status_code=500,
            detail={'error': 'Failed to get graphify status', 'message': 'An internal error occurred'}
        )


@router.post('/mcp/graphify/enable')
def enable_graphify(admin: User = Depends(get_admin_user)):
    """启用 graphify MCP 服务"""
    try:
        from config import Config
        from services.mcp.mcp_config import McpServerConfig, get_mcp_config, PRESET_MCP_SERVERS

        graph_path = Config.get_user_graph_path(admin.id)
        if not os.path.exists(graph_path):
            raise HTTPException(
                status_code=400,
                detail={'success': False, 'error': f'Graph file not found: {graph_path}. Run graphify extract first.'}
            )

        mcp_mgr = get_mcp_config()
        server = mcp_mgr.get_server('graphify')

        if server:
            server.disabled = False
            server.args = ["-m", "graphify.serve", graph_path]
            mcp_mgr.save_config()

            return {
                'success': True,
                'message': 'graphify MCP enabled. Restart app to apply.',
                'restart_required': True
            }
        else:
            preset = PRESET_MCP_SERVERS.get('graphify')
            if preset:
                config = McpServerConfig(
                    name='graphify',
                    transport='stdio',
                    command='python',
                    args=["-m", "graphify.serve", graph_path],
                    env={},
                    disabled=False
                )
                mcp_mgr.add_server(config)
                mcp_mgr.save_config()

                return {
                    'success': True,
                    'message': 'graphify MCP configured and enabled. Restart app to apply.',
                    'restart_required': True
                }
            else:
                raise HTTPException(
                    status_code=500,
                    detail={'success': False, 'error': 'preset not found'}
                )

    except HTTPException:
        raise
    except Exception:
        logger.exception('Failed to enable graphify')
        raise HTTPException(
            status_code=500,
            detail={'error': 'Failed to enable graphify', 'message': 'An internal error occurred'}
        )


# ==================== OpenHarness 工具/技能列表 ====================

@router.get('/openharness/tools')
def get_openharness_tools(
    request: Request,
    locale: str | None = Query(default=None),
    admin: User = Depends(get_admin_user),
):
    """获取 OpenHarness 工具列表"""
    resolved_locale = resolve_request_locale(request, locale, admin)

    try:
        tools = []
        try:
            registry = _get_tools_registry_cached()
            tool_list = registry.list_tools()
            for t in tool_list:
                name = t.get('name', '')
                if any(k in name for k in ['file', 'glob', 'grep', 'edit', 'write', 'read', 'notebook']):
                    category = 'filesystem'
                elif any(k in name for k in ['bash', 'cron', 'sleep', 'task', 'team']):
                    category = 'system'
                elif any(k in name for k in ['web', 'fetch', 'search', 'exa']):
                    category = 'network'
                elif any(k in name for k in ['mcp', 'lsp']):
                    category = 'integration'
                elif any(k in name for k in ['agent', 'skill', 'send_message', 'ask_user']):
                    category = 'agent'
                else:
                    category = 'utility'

                tools.append(localize_tool_description({
                    'name': name,
                    'description': t.get('description', ''),
                    'category': category,
                    'enabled': True,
                }, resolved_locale))
        except Exception as e:
            logger.warning(f'Failed to list OpenHarness tools: {e}')

        return {
            'tools': tools,
            'total': len(tools),
        }

    except Exception:
        logger.exception('Failed to fetch OpenHarness tools')
        raise HTTPException(
            status_code=500,
            detail={'error': 'Failed to fetch tools', 'message': 'An internal error occurred'}
        )


@router.get('/openharness/skills')
def get_openharness_skills(admin: User = Depends(get_admin_user)):
    """获取 Skills 列表"""
    try:
        skills = []
        try:
            manager = _get_skills_manager_cached()
            for s in manager.list_skills():
                skills.append({
                    'id': s['id'],
                    'name': s['name'],
                    'description': s['description'],
                    'enabled_tools': s.get('enabled_tools', []),
                    'source': 'backend',
                    'active': s['id'] in manager.active_skills,
                })
        except Exception as e:
            logger.warning(f'Failed to list backend skills: {e}')

        try:
            from openharness.skills.loader import load_skill_registry
            oh_registry = load_skill_registry()
            for skill_def in oh_registry.list_skills():
                if not any(s['id'] == skill_def.name for s in skills):
                    skills.append({
                        'id': skill_def.name,
                        'name': skill_def.name,
                        'description': skill_def.description or '',
                        'enabled_tools': [],
                        'source': 'openharness',
                        'active': False,
                    })
        except Exception:
            pass

        return {
            'skills': skills,
            'total': len(skills),
        }

    except Exception:
        logger.exception('Failed to fetch OpenHarness skills')
        raise HTTPException(
            status_code=500,
            detail={'error': 'Failed to fetch skills', 'message': 'An internal error occurred'}
        )


@router.put('/openharness/skills/{skill_id}/toggle')
def toggle_openharness_skill(skill_id: str, admin: User = Depends(get_admin_user)):
    """切换 Skill 启用/禁用"""
    try:
        from services.skills_manager import get_skills_manager
        manager = get_skills_manager()

        if skill_id not in manager.skills:
            raise HTTPException(
                status_code=404,
                detail={'error': 'Skill not found', 'message': f'Skill {skill_id} does not exist'}
            )

        if skill_id in manager.active_skills:
            manager.deactivate_skill(skill_id)
            active = False
        else:
            manager.activate_skill(skill_id)
            active = True

        return {
            'skill_id': skill_id,
            'active': active,
        }

    except HTTPException:
        raise
    except Exception:
        logger.exception(f'Failed to toggle skill: {skill_id}')
        raise HTTPException(
            status_code=500,
            detail={'error': 'Failed to toggle skill', 'message': 'An internal error occurred'}
        )
