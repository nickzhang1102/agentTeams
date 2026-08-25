"""
FastAPI Agent 配置 API 路由模块

实现 Agent 配置 API：
- GET / - 获取所有 agents 列表（DB 优先，fallback 文件系统）
- GET /models - 获取可用模型列表
- GET /tree - 获取 Agent 分类树
- GET /categories - 获取分类列表
- GET /{agent_id} - 获取单个 agent 详情
"""
import os
import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.deps import get_current_user, resolve_request_locale
from config import Config
from database import get_db
from models import AgentConfig, LLMModel, User
from services.catalog_localization_service import catalog_localization_service
from utils.locale_utils import SupportedLocale

logger = logging.getLogger(__name__)

# 创建 Agent 配置路由
router = APIRouter(prefix="/api/agents", tags=["agents"])

# 保留字：字面量子路径使用的 ID，避免被 {agent_id} 吞掉
RESERVED_AGENT_IDS = {"models", "tree", "categories", "priority"}


# ==================== 请求/响应模型 ====================

class PriorityUpdateItem(BaseModel):
    agent_id: str = Field(..., max_length=50)
    priority: int = Field(..., ge=0, le=100)


class BatchPriorityRequest(BaseModel):
    items: List[PriorityUpdateItem] = Field(..., min_length=1, max_length=100)


def parse_agent_file(file_path: str) -> Optional[dict]:
    """
    解析 agent 配置文件（fallback 用，仅当 DB 无数据时）

    Args:
        file_path: agent 文件路径

    Returns:
        dict: agent 信息或 None
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 提取 frontmatter
        frontmatter = {}
        if content.startswith('---'):
            parts = content.split('---', 2)
            if len(parts) >= 3:
                fm_text = parts[1].strip()
                for line in fm_text.split('\n'):
                    if ':' in line:
                        key, value = line.split(':', 1)
                        frontmatter[key.strip()] = value.strip().strip('"')

        # 提取文件名作为 ID
        filename = os.path.basename(file_path)
        agent_id = filename.replace('.md', '')

        return {
            'id': agent_id,
            'agent_id': agent_id,
            'name': frontmatter.get('name', agent_id),
            'description': frontmatter.get('description', ''),
            'model': frontmatter.get('model', 'inherit'),
            'is_system': True,
        }
    except Exception as e:
        logger.error(f"解析 agent 文件失败 {file_path}: {e}")
        return None


def _localize_agent(data: dict, locale: SupportedLocale, include_labels: bool = False) -> dict:
    agent_id = data.get('agent_id') or str(data.get('id', ''))
    return catalog_localization_service.localize_item(
        data=data,
        entity_type='agent',
        key=agent_id,
        source_name=data.get('name'),
        is_system=data.get('is_system', True),
        locale=locale,
        include_labels=include_labels,
    )


@router.get("")
async def get_agents(
    request: Request,
    locale: Optional[str] = Query(default=None),
    user: User = Depends(get_current_user),
    db_session: Session = Depends(get_db),
):
    """获取所有可用的 agents（DB 优先，fallback 文件系统）"""
    request_locale = resolve_request_locale(request, locale, user)
    try:
        # DB 优先：查询所有已启用的 Agent
        db_agents = (
            db_session.query(AgentConfig)
            .filter(AgentConfig.is_enabled == True)
            .order_by(AgentConfig.priority.asc(), AgentConfig.agent_id)
            .all()
        )

        if db_agents:
            return {'agents': [_localize_agent(a.to_dict(), request_locale) for a in db_agents]}

        # Fallback：DB 无数据时读文件系统（首次部署未同步场景）
        agents_dir = Config.AGENTS_DIR or ''
        if not agents_dir or not os.path.exists(agents_dir):
            return {'agents': []}

        agents = []
        for filename in os.listdir(agents_dir):
            if filename.endswith('.md'):
                file_path = os.path.join(agents_dir, filename)
                agent_info = parse_agent_file(file_path)
                if agent_info:
                    agents.append(_localize_agent(agent_info, request_locale))

        agents.sort(key=lambda x: x.get('label', x.get('name', '')))
        return {'agents': agents}

    except Exception as e:
        logger.error(f"获取 agents 失败: {e}")
        return {'agents': []}


# ============================================================
# 字面量子路径必须排在 {agent_id} 之前
# Starlette 路由按声明顺序匹配，无"最具体优先"优化
# ============================================================

@router.get("/models")
async def get_available_models(
    user = Depends(get_current_user),
    db_session: Session = Depends(get_db),
):
    """获取可用的模型列表（从 DB llm_models 表读取）"""
    from services.llm_service import LLMService

    model_specs = LLMService.get_model_specs()
    models = []
    for model_id, spec in model_specs.items():
        models.append({
            'id': model_id,
            'name': model_id,
            'context_limit': spec['context_limit'],
            'max_output_tokens': spec['max_output_tokens'],
        })

    # 按名称排序
    models.sort(key=lambda x: x['name'])

    default_model = (
        db_session.query(LLMModel)
        .filter(LLMModel.is_enabled == True)
        .order_by(LLMModel.is_default.desc(), LLMModel.sort_order, LLMModel.id)
        .first()
    )
    return {
        'models': models,
        'default': default_model.model_id if default_model else None,
    }


@router.get("/tree")
async def get_agent_tree(
    request: Request,
    locale: Optional[str] = Query(default=None),
    user: User = Depends(get_current_user),
    db_session: Session = Depends(get_db),
):
    """获取 Agent 分类树和所有 Agent 信息"""
    request_locale = resolve_request_locale(request, locale, user)
    try:
        from services.agent_category_service import AgentCategoryService
        service = AgentCategoryService()
        return service.build_category_tree(db_session, request_locale)
    except Exception as e:
        logger.error(f"获取 agent tree 失败: {e}")
        return {'tree': {}, 'agents': []}


@router.get("/categories")
async def get_categories(
    request: Request,
    locale: Optional[str] = Query(default=None),
    user: User = Depends(get_current_user),
    db_session: Session = Depends(get_db),
):
    """获取 Agent 分类列表（含动态聚合 count）"""
    request_locale = resolve_request_locale(request, locale, user)
    from services.agent_category_service import AgentCategoryService
    service = AgentCategoryService()
    return {'categories': service.get_categories(db_session, request_locale)}


@router.patch("/priority")
async def update_agent_priority(
    body: BatchPriorityRequest,
    user: User = Depends(get_current_user),
    db_session: Session = Depends(get_db),
):
    """批量更新 Agent 执行优先级（拖拽排序）"""
    agent_ids = [item.agent_id for item in body.items]
    try:
        agents = db_session.query(AgentConfig).filter(
            AgentConfig.agent_id.in_(agent_ids)
        ).all()
        agent_map = {a.agent_id: a for a in agents}

        # 权限校验：非 admin 仅可更新自己创建的非系统 agent
        if not user.is_admin:
            for item in body.items:
                agent = agent_map.get(item.agent_id)
                if agent is None:
                    continue
                if agent.is_system or agent.created_by != user.id:
                    raise HTTPException(
                        status_code=403,
                        detail='只能调整自建 Agent 的顺序'
                    )

        updated = 0
        for item in body.items:
            agent = agent_map.get(item.agent_id)
            if agent and agent.priority != item.priority:
                agent.priority = item.priority
                updated += 1

        if updated > 0:
            db_session.commit()

        return {'updated': updated}
    except HTTPException:
        db_session.rollback()
        raise
    except Exception as e:
        db_session.rollback()
        logger.error(f"批量更新 Agent 优先级失败: {e}")
        raise HTTPException(status_code=500, detail='更新优先级失败')


@router.get("/{agent_id}")
async def get_agent(
    agent_id: str,
    request: Request,
    locale: Optional[str] = Query(default=None),
    user: User = Depends(get_current_user),
    db_session: Session = Depends(get_db),
):
    """获取单个 agent 的详细信息（DB 优先，fallback 文件系统）"""
    request_locale = resolve_request_locale(request, locale, user)
    # 保留字黑名单：防止 {agent_id} 吞掉字面量子路径
    if agent_id in RESERVED_AGENT_IDS:
        raise HTTPException(
            status_code=404,
            detail={'error': f'Agent {agent_id} 不存在'}
        )

    # 安全检查：防止路径遍历
    if '..' in agent_id or '/' in agent_id or '\\' in agent_id:
        raise HTTPException(
            status_code=400,
            detail={'error': '无效的 agent ID'}
        )

    try:
        # DB 优先
        agent = db_session.query(AgentConfig).filter_by(agent_id=agent_id).first()
        if agent and agent.is_enabled:
            return _localize_agent(agent.to_dict(), request_locale)

        # Fallback：读文件系统
        agents_dir = Config.AGENTS_DIR or ''
        if not agents_dir:
            raise HTTPException(
                status_code=404,
                detail={'error': 'Agents 目录未配置'}
            )

        file_path = os.path.join(agents_dir, f"{agent_id}.md")
        if not os.path.exists(file_path):
            raise HTTPException(
                status_code=404,
                detail={'error': f'Agent {agent_id} 不存在'}
            )

        agent_info = parse_agent_file(file_path)
        if not agent_info:
            raise HTTPException(
                status_code=500,
                detail={'error': '解析 agent 失败'}
            )

        return _localize_agent(agent_info, request_locale)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取 agent 失败: {e}")
        raise HTTPException(
            status_code=500,
            detail={'error': '获取 agent 失败'}
        )
