"""工具日志 API

提供工具调用日志查询、详情、统计。
新增：工具清单、配置管理、调试执行。
"""

import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from database import get_db
from api.deps import get_admin_user, resolve_request_locale
from models import User, ToolCallLog, SystemConfig
from api.admin.admin_helpers import paginate
from catalog.tool_descriptions import localize_tool_description


logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin-tool-logs"])


# ==================== Pydantic 模型 ====================

class ToolConfigUpdate(BaseModel):
    """工具配置更新请求"""
    enabled: Optional[bool] = None
    timeout_seconds: Optional[int] = None


class ToolDebugRequest(BaseModel):
    """工具调试执行请求"""
    params: dict = {}


# ==================== 工具清单 ====================

@router.get('/tools')
def get_tools(
    request: Request,
    locale: str | None = Query(default=None),
    db_session: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """获取 OpenHarness 所有已注册工具清单

    返回每个工具的名称、描述、详细说明、参数 schema、启用状态。
    """
    resolved_locale = resolve_request_locale(request, locale, admin)

    try:
        from services.harness.harness_adapter import HarnessToolRegistry

        # 获取工具注册表
        try:
            registry = HarnessToolRegistry(workspace_dir='data/workspace')
        except Exception as e:
            logger.error(f"Failed to initialize HarnessToolRegistry: {e}")
            raise HTTPException(status_code=500, detail={'error': 'Tool registry initialization failed', 'message': str(e)})

        # 获取所有工具 schema
        tools_schema = registry.list_tools()

        # 批量查询工具启用状态
        enabled_configs = db_session.query(SystemConfig).filter(
            SystemConfig.key.like('tool.enabled.%')
        ).all()
        enabled_map = {c.key.replace('tool.enabled.', ''): c.value.lower() == 'true' for c in enabled_configs}

        # 构建工具列表（增强版，含详细说明 + 中文翻译）
        tools = []
        for schema in tools_schema:
            tool_name = schema.get('name', '')
            # 获取工具实例以提取 docstring
            tool_instance = registry.oh_registry.get(tool_name)
            detailed_description = ''
            if tool_instance and tool_instance.__class__.__doc__:
                detailed_description = tool_instance.__class__.__doc__.strip()

            tool = localize_tool_description({
                'name': tool_name,
                'description': schema.get('description', ''),
                'detailed_description': detailed_description,
                'input_schema': schema.get('input_schema', {}),
                'enabled': enabled_map.get(tool_name, True),  # 默认启用
            }, resolved_locale)
            tools.append(tool)

        return {'tools': tools, 'total': len(tools)}

    except HTTPException:
        raise
    except Exception:
        logger.exception('Failed to fetch tools')
        raise HTTPException(status_code=500, detail={'error': 'Failed to fetch tools', 'message': 'An internal error occurred'})


# ==================== 工具配置 ====================

@router.put('/tools/{tool_name}/config')
def update_tool_config(
    tool_name: str,
    body: ToolConfigUpdate,
    db_session: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """更新工具配置（开关、超时）"""
    try:
        from services.harness.harness_adapter import HarnessToolRegistry

        # 验证工具存在
        try:
            registry = HarnessToolRegistry(workspace_dir='data/workspace')
        except Exception as e:
            raise HTTPException(status_code=500, detail={'error': 'Tool registry initialization failed', 'message': str(e)})

        tool = registry.oh_registry.get(tool_name)
        if not tool:
            raise HTTPException(status_code=404, detail={'error': 'Tool not found', 'message': f'Tool {tool_name} does not exist'})

        # 更新启用状态
        if body.enabled is not None:
            config_key = f'tool.enabled.{tool_name}'
            config = db_session.query(SystemConfig).filter_by(key=config_key).first()
            if config:
                config.value = 'true' if body.enabled else 'false'
            else:
                config = SystemConfig(key=config_key, value='true' if body.enabled else 'false', description=f'{tool_name} 工具启用状态')
                db_session.add(config)

        # 更新超时
        if body.timeout_seconds is not None:
            config_key = 'tool.timeout_seconds'
            config = db_session.query(SystemConfig).filter_by(key=config_key).first()
            if config:
                config.value = str(body.timeout_seconds)
            else:
                config = SystemConfig(key=config_key, value=str(body.timeout_seconds), description='工具调用超时（秒）')
                db_session.add(config)

        db_session.commit()
        return {'success': True}

    except HTTPException:
        raise
    except Exception:
        db_session.rollback()
        logger.exception(f'Failed to update tool config: {tool_name}')
        raise HTTPException(status_code=500, detail={'error': 'Failed to update tool config', 'message': 'An internal error occurred'})


# ==================== 工具调试 ====================

@router.post('/tools/{tool_name}/debug')
def debug_tool(
    tool_name: str,
    body: ToolDebugRequest,
    db_session: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """调试执行工具"""
    try:
        from services.harness.harness_adapter import HarnessToolRegistry

        # 获取工具注册表
        try:
            registry = HarnessToolRegistry(workspace_dir='data/workspace')
        except Exception as e:
            raise HTTPException(status_code=500, detail={'error': 'Tool registry initialization failed', 'message': str(e)})

        # 验证工具存在
        tool = registry.oh_registry.get(tool_name)
        if not tool:
            raise HTTPException(status_code=404, detail={'error': 'Tool not found', 'message': f'Tool {tool_name} does not exist'})

        # 获取超时配置
        timeout_config = db_session.query(SystemConfig).filter_by(key='tool.timeout_seconds').first()
        timeout = int(timeout_config.value) if timeout_config else 300

        # 执行工具
        start_time = time.time()
        try:
            result = registry.execute_tool(tool_name, body.params, timeout=timeout)
            elapsed = time.time() - start_time
            return {
                'result': {
                    'output': result,
                    'status': 'success',
                    'execution_time': round(elapsed, 3),
                }
            }
        except TimeoutError:
            elapsed = time.time() - start_time
            return {
                'result': {
                    'output': None,
                    'status': 'timeout',
                    'execution_time': round(elapsed, 3),
                    'error': f'执行超时（{timeout}秒）',
                }
            }
        except Exception as e:
            elapsed = time.time() - start_time
            return {
                'result': {
                    'output': None,
                    'status': 'error',
                    'execution_time': round(elapsed, 3),
                    'error': str(e),
                }
            }

    except HTTPException:
        raise
    except Exception:
        logger.exception(f'Failed to debug tool: {tool_name}')
        raise HTTPException(status_code=500, detail={'error': 'Failed to debug tool', 'message': 'An internal error occurred'})


@router.get('/tools/logs')
def get_tool_logs(
    db_session: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    agent_id: Optional[str] = Query(default=None),
    tool_name: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
):
    """获取工具调用日志列表（支持筛选和分页）"""
    try:
        query = db_session.query(ToolCallLog)

        if agent_id:
            query = query.filter_by(agent_id=agent_id)
        if tool_name:
            query = query.filter_by(tool_name=tool_name)
        if status:
            query = query.filter_by(status=status)

        query = query.order_by(ToolCallLog.created_at.desc())
        pagination = paginate(query, page, per_page)

        return {
            'logs': [log.to_dict() for log in pagination['items']],
            'total': pagination['total'], 'page': pagination['page'],
            'per_page': pagination['per_page']
        }

    except Exception:
        logger.exception('Failed to fetch tool logs')
        raise HTTPException(status_code=500, detail={'error': 'Failed to fetch tool logs', 'message': 'An internal error occurred'})


@router.get('/tools/logs/{log_id}')
def get_tool_log_detail(log_id: int, db_session: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    """获取工具调用日志详情"""
    try:
        log = db_session.get(ToolCallLog, log_id)
        if not log:
            raise HTTPException(status_code=404, detail={'error': 'Log not found', 'message': f'Tool call log {log_id} does not exist'})

        return {'log': log.to_dict()}

    except HTTPException:
        raise
    except Exception:
        logger.exception(f'Failed to fetch tool log: {log_id}')
        raise HTTPException(status_code=500, detail={'error': 'Failed to fetch tool log', 'message': 'An internal error occurred'})


@router.get('/tools/stats')
def get_tool_stats(db_session: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    """获取工具使用统计"""
    try:
        stats = db_session.query(
            ToolCallLog.tool_name.label('tool_name'),
            func.count(ToolCallLog.id).label('total_calls'),
            func.sum(case((ToolCallLog.status == 'success', 1), else_=0)).label('success_calls'),
            func.coalesce(func.avg(ToolCallLog.execution_time), 0).label('avg_time')
        ).group_by(ToolCallLog.tool_name).order_by(func.count(ToolCallLog.id).desc()).all()

        tool_stats = []
        total_calls = 0
        for row in stats:
            calls = int(row.total_calls)
            success = int(row.success_calls)
            total_calls += calls
            tool_stats.append({
                'tool_name': row.tool_name,
                'total_calls': calls,
                'success_rate': round(success / calls, 4) if calls > 0 else 0.0,
                'avg_time': round(float(row.avg_time), 2)
            })

        return {'tool_stats': tool_stats, 'total_tools': len(tool_stats), 'total_calls': total_calls}

    except Exception:
        logger.exception('Failed to fetch tool stats')
        raise HTTPException(status_code=500, detail={'error': 'Failed to fetch tool stats', 'message': 'An internal error occurred'})
