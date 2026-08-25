"""系统设置 API

提供系统配置 CRUD 和 OpenHarness 运行状态/配置管理。
"""

import logging
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from api.deps import get_admin_user, audit_log
from models import User, SystemConfig
from utils.time_utils import utcnow_naive
from api.admin.admin_schemas import SettingUpdateRequest, OpenHarnessConfigUpdateRequest
from api.admin.openharness_config import (
    OPENHARNESS_CONFIG_SCHEMA, RESTART_REQUIRED_KEYS, get_openharness_config_value,
)


logger = logging.getLogger(__name__)

MANAGED_LLM_SETTING_KEYS = {
    'LLM_API_KEY', 'LLM_BASE_URL', 'LLM_MODEL', 'LLM_MAX_TOKENS',
    'GRAPHIFY_LLM_API_KEY', 'GRAPHIFY_LLM_BASE_URL', 'GRAPHIFY_LLM_MODEL',
}

router = APIRouter(tags=["admin-settings"])


@router.get('/settings')
def get_settings(db_session: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    """获取所有系统设置"""
    try:
        settings = (
            db_session.query(SystemConfig)
            .filter(~SystemConfig.key.in_(MANAGED_LLM_SETTING_KEYS))
            .order_by(SystemConfig.key.asc())
            .all()
        )
        return {'settings': [s.to_dict() for s in settings]}

    except Exception:
        logger.exception('Failed to fetch settings')
        raise HTTPException(status_code=500, detail={'error': 'Failed to fetch settings', 'message': 'An internal error occurred'})


@router.put('/settings/{key}')
def update_setting(key: str, request: SettingUpdateRequest, db_session: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    """更新系统设置"""
    try:
        setting = db_session.query(SystemConfig).filter_by(key=key).first()
        if not setting:
            raise HTTPException(status_code=404, detail={'error': 'Setting not found', 'message': f'Setting {key} does not exist'})

        if key in MANAGED_LLM_SETTING_KEYS:
            raise HTTPException(
                status_code=400,
                detail={'error': 'Managed setting', 'message': 'LLM configuration must be changed in LLM Models'},
            )

        if setting.is_secret and str(request.value) == '':
            return {'setting': setting.to_dict()}

        setting.value = str(request.value)
        setting.updated_at = utcnow_naive()

        # 敏感值不落审计详情，仅记录键名
        audit_log(
            user_id=admin.id,
            action='admin.setting.update',
            resource_type='system_config',
            details={'key': key},
            db_session=db_session,
        )

        try:
            db_session.commit()
        except Exception:
            db_session.rollback()
            logger.exception(f'Failed to update setting: {key}')
            raise HTTPException(status_code=500, detail={'error': 'Database error', 'message': 'Failed to update setting'})

        logger.info(f'Setting updated: {key}')
        return {'setting': setting.to_dict()}

    except HTTPException:
        raise
    except Exception:
        db_session.rollback()
        logger.exception(f'Failed to update setting: {key}')
        raise HTTPException(status_code=500, detail={'error': 'Failed to update setting', 'message': 'An internal error occurred'})


@router.get('/openharness/status')
def get_openharness_status(db_session: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    """获取 OpenHarness 运行状态和配置概览"""
    try:
        from config import Config

        version = Config.OPENHARNESS_VERSION

        config_data = {}
        for key, (desc, default, group) in OPENHARNESS_CONFIG_SCHEMA.items():
            entry = get_openharness_config_value(key, db_session)
            entry['description'] = desc
            entry['default'] = default
            entry['group'] = group
            entry['requires_restart'] = key in RESTART_REQUIRED_KEYS
            config_data[key] = entry

        tools_count = agents_count = skills_count = mcp_servers_count = 0

        try:
            from services.harness.harness_adapter import HarnessToolRegistry
            from config import config as app_config
            registry = HarnessToolRegistry(workspace_dir=app_config.get('WORKSPACE_DIR', 'data/workspace'))
            tools_count = len(registry.list_tools())
        except Exception:
            pass

        try:
            from services.harness.harness_coordinator import get_harness_coordinator
            coordinator = get_harness_coordinator()
            agents_count = len(coordinator.registered_agents)
        except Exception:
            pass

        try:
            from skills_manager import get_skills_manager
            manager = get_skills_manager()
            skills_count = len(manager.skills)
        except Exception:
            pass

        try:
            from services.mcp.mcp_config import get_mcp_config
            mcp_mgr = get_mcp_config()
            mcp_servers_count = len(mcp_mgr.servers)
        except Exception:
            pass

        return {
            'version': version,
            'enabled': config_data.get('OPENHARNESS_ENABLED', {}).get('value') == 'true',
            'config': config_data,
            'tools_count': tools_count, 'agents_count': agents_count,
            'skills_count': skills_count, 'mcp_servers_count': mcp_servers_count,
        }

    except Exception:
        logger.exception('Failed to fetch OpenHarness status')
        raise HTTPException(status_code=500, detail={'error': 'Failed to fetch OpenHarness status', 'message': 'An internal error occurred'})


@router.put('/openharness/config')
def update_openharness_config(
    request: OpenHarnessConfigUpdateRequest,
    db_session: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """批量更新 OpenHarness 配置项"""
    try:
        configs = request.configs

        allowed_keys = set(OPENHARNESS_CONFIG_SCHEMA.keys())
        invalid_keys = set(configs.keys()) - allowed_keys
        if invalid_keys:
            raise HTTPException(status_code=400, detail={'error': 'Invalid config keys', 'message': f'Unknown keys: {", ".join(invalid_keys)}'})

        path_keys = {'WORKSPACE_DIR'}
        for key in path_keys:
            if key in configs:
                value = str(configs[key]).strip()
                if not value:
                    raise HTTPException(status_code=400, detail={'error': 'Bad request', 'message': f'{key} 路径不能为空'})
                if '..' in value:
                    raise HTTPException(status_code=400, detail={'error': 'Bad request', 'message': f'{key} 路径不合法：禁止路径遍历'})

        updated = 0
        restart_required = False
        for key, value in configs.items():
            value_str = str(value)
            setting = db_session.query(SystemConfig).filter_by(key=key).first()
            if setting:
                setting.value = value_str
                setting.updated_at = utcnow_naive()
            else:
                desc = OPENHARNESS_CONFIG_SCHEMA.get(key, ('', '', ''))[0]
                db_session.add(SystemConfig(key=key, value=value_str, description=desc))
            updated += 1
            if key in RESTART_REQUIRED_KEYS:
                restart_required = True

        audit_log(
            user_id=admin.id,
            action='admin.openharness_config.update',
            resource_type='system_config',
            details={'keys': sorted(configs.keys())},
            db_session=db_session,
        )

        try:
            db_session.commit()
        except Exception:
            db_session.rollback()
            logger.exception('Failed to save OpenHarness config')
            raise HTTPException(status_code=500, detail={'error': 'Database error', 'message': 'Failed to save config'})

        logger.info(f'OpenHarness config updated: {updated} keys')
        return {
            'updated': updated, 'restart_required': restart_required,
            'message': '配置已保存' + ('，部分配置需重启服务生效' if restart_required else '，配置已即时生效')
        }

    except HTTPException:
        raise
    except Exception:
        db_session.rollback()
        logger.exception('Failed to update OpenHarness config')
        raise HTTPException(status_code=500, detail={'error': 'Failed to update config', 'message': 'An internal error occurred'})

