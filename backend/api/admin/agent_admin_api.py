"""Agent 管理 API

提供 Agent CRUD、同步、启停、MCP 权限、类型列表等管理端点。
"""

import json
import logging
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session

from database import get_db
from api.deps import get_admin_user, resolve_request_locale
from models import User, AgentConfig, AgentMcpPermission
from services.catalog_localization_service import catalog_localization_service
from utils.locale_utils import SupportedLocale
from utils.error_handler import safe_error_response
from utils.time_utils import utcnow_naive
from api.admin.admin_helpers import get_file_manager, paginate
from api.admin.admin_schemas import AgentCreateRequest, AgentUpdateRequest, AgentGenerateRequest, AgentMcpPermissionsUpdateRequest


logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin-agents"])


def _localized_admin_agent(
    agent: AgentConfig,
    locale: SupportedLocale,
    content: str | None = None,
) -> dict:
    return catalog_localization_service.localize_item(
        data=agent.to_dict(content),
        entity_type='agent',
        key=agent.agent_id,
        source_name=agent.name,
        is_system=agent.is_system,
        locale=locale,
        include_labels=True,
    )


@router.get('/agents')
def list_agents(
    request: Request,
    db_session: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    is_enabled: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    source: Optional[str] = Query(default=None),
    is_system: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    locale: Optional[str] = Query(default=None),
):
    """获取Agent列表（支持筛选、搜索、分页）"""
    request_locale = resolve_request_locale(request, locale, admin)
    try:
        query = db_session.query(AgentConfig)

        if is_enabled is not None:
            if is_enabled.lower() in ('true', '1', 'yes'):
                query = query.filter_by(is_enabled=True)
            elif is_enabled.lower() in ('false', '0', 'no'):
                query = query.filter_by(is_enabled=False)

        if source is not None:
            query = query.filter_by(source=source)

        if is_system is not None:
            if is_system.lower() in ('true', '1', 'yes'):
                query = query.filter_by(is_system=True)
            elif is_system.lower() in ('false', '0', 'no'):
                query = query.filter_by(is_system=False)

        if category is not None:
            from services.agent_category_service import apply_category_filter
            query = apply_category_filter(query, category, db=db_session)

        if search and search.strip():
            search_pattern = f'%{search.strip()}%'
            search_conditions = [
                AgentConfig.agent_id.ilike(search_pattern),
                AgentConfig.name.ilike(search_pattern),
                AgentConfig.description.ilike(search_pattern),
            ]
            label_keys = catalog_localization_service.matching_keys(
                'agent', request_locale, search
            )
            if label_keys:
                search_conditions.append(AgentConfig.agent_id.in_(label_keys))
            query = query.filter(or_(*search_conditions))

        query = query.order_by(AgentConfig.priority.asc(), AgentConfig.agent_id.asc())
        pagination = paginate(query, page, per_page)

        return {
            'agents': [
                _localized_admin_agent(a, request_locale)
                for a in pagination['items']
            ],
            'total': pagination['total'], 'page': pagination['page'],
            'per_page': pagination['per_page'], 'pages': pagination['pages']
        }

    except HTTPException:
        raise
    except Exception:
        logger.exception('Failed to list agents')
        raise HTTPException(status_code=500, detail={'error': 'Failed to list agents', 'message': 'An internal error occurred'})


@router.get('/agents/{agent_id}')
def get_agent(
    agent_id: str,
    request: Request,
    db_session: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
    locale: Optional[str] = Query(default=None),
):
    """获取Agent详情（包含文件内容）"""
    request_locale = resolve_request_locale(request, locale, admin)
    try:
        fm = get_file_manager()
        if not fm.validate_agent_id(agent_id):
            raise HTTPException(status_code=400, detail={'error': 'Invalid agent_id', 'message': f'agent_id format is invalid: {agent_id}'})

        agent = db_session.query(AgentConfig).filter_by(agent_id=agent_id).first()
        if not agent:
            raise HTTPException(status_code=404, detail={'error': 'Agent not found', 'message': f'Agent {agent_id} does not exist in database'})

        content = None
        if agent.file_exists:
            try:
                _metadata, markdown_content = fm.read_agent_file(agent_id)
                content = markdown_content
            except (FileNotFoundError, IOError) as e:
                logger.warning(f'Agent file read failed: {agent_id}, {e}')

        return {'agent': _localized_admin_agent(agent, request_locale, content)}

    except HTTPException:
        raise
    except Exception:
        logger.exception(f'Failed to get agent: {agent_id}')
        raise HTTPException(status_code=500, detail={'error': 'Failed to get agent', 'message': 'An internal error occurred'})


@router.post('/agents', status_code=201)
def create_agent(
    request: AgentCreateRequest,
    db_session: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """创建Agent（写入文件 + 创建数据库记录）"""
    try:
        fm = get_file_manager()
        if not fm.validate_agent_id(request.agent_id):
            raise HTTPException(status_code=400, detail={'error': 'Invalid agent_id', 'message': f'agent_id format is invalid: {request.agent_id}'})

        existing = db_session.query(AgentConfig).filter_by(agent_id=request.agent_id).first()
        if existing:
            raise HTTPException(status_code=409, detail={'error': 'Agent already exists', 'message': f'Agent {request.agent_id} already exists'})

        metadata = {'name': request.name, 'description': request.description or '', 'model': request.model or 'inherit'}
        try:
            file_path = fm.create_agent_file(request.agent_id, metadata, request.content or '')
        except IOError as e:
            raise HTTPException(status_code=409, detail=safe_error_response(e, '文件创建失败'))

        agent = AgentConfig(
            agent_id=request.agent_id, name=request.name,
            description=request.description or '', model=request.model or 'inherit',
            file_path=str(file_path), file_exists=True, is_enabled=True,
            source='db', is_system=False, created_by=admin.id,
            content=request.content or '',
            role=request.role, persona=request.persona,
            expertise=request.expertise, approach=request.approach,
            capabilities=request.capabilities or [],
            skill_level=request.skill_level,
            tags=request.tags or [],
            preferred_contexts=request.preferred_contexts or [],
            portrait_url=request.portrait_url,
        )
        db_session.add(agent)

        try:
            db_session.commit()
        except Exception:
            db_session.rollback()
            logger.exception(f'Failed to create agent in database: {request.agent_id}')
            try:
                fm.delete_agent_file(request.agent_id)
            except Exception:
                logger.warning(f'Failed to rollback agent file: {request.agent_id}')
            raise HTTPException(status_code=500, detail={'error': 'Database error', 'message': 'Failed to create agent record'})

        logger.info(f'Agent created: {request.agent_id}')
        return {'agent': agent.to_dict()}

    except HTTPException:
        raise
    except Exception:
        db_session.rollback()
        logger.exception('Failed to create agent')
        raise HTTPException(status_code=500, detail={'error': 'Failed to create agent', 'message': 'An internal error occurred'})


@router.put('/agents/{agent_id}')
def update_agent(
    agent_id: str,
    request: AgentUpdateRequest,
    db_session: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """更新Agent（写入文件 + 更新数据库记录）"""
    try:
        fm = get_file_manager()
        if not fm.validate_agent_id(agent_id):
            raise HTTPException(status_code=400, detail={'error': 'Invalid agent_id', 'message': f'agent_id format is invalid: {agent_id}'})

        agent = db_session.query(AgentConfig).filter_by(agent_id=agent_id).first()
        if not agent:
            raise HTTPException(status_code=404, detail={'error': 'Agent not found', 'message': f'Agent {agent_id} does not exist'})

        # 系统 Agent 禁止修改核心字段
        if agent.is_system:
            raise HTTPException(status_code=403, detail={'error': 'Forbidden', 'message': f'System agent {agent_id} cannot be modified. Use toggle to enable/disable.'})

        if request.name is not None:
            agent.name = request.name
        if request.description is not None:
            agent.description = request.description
        if request.model is not None:
            agent.model = request.model
        # 更新新增字段
        if request.role is not None: agent.role = request.role
        if request.persona is not None: agent.persona = request.persona
        if request.expertise is not None: agent.expertise = request.expertise
        if request.approach is not None: agent.approach = request.approach
        if request.capabilities is not None: agent.capabilities = request.capabilities
        if request.skill_level is not None: agent.skill_level = request.skill_level
        if request.tags is not None: agent.tags = request.tags
        if request.preferred_contexts is not None: agent.preferred_contexts = request.preferred_contexts
        if request.portrait_url is not None: agent.portrait_url = request.portrait_url
        agent.updated_at = utcnow_naive()

        if request.content is not None:
            # DB Agent：直接更新 content 字段
            agent.content = request.content
            # 同时写入文件（如文件存在）
            if agent.file_exists:
                try:
                    fm.update_agent_file(agent_id, {'name': agent.name, 'description': agent.description, 'model': agent.model}, request.content)
                except (FileNotFoundError, IOError) as e:
                    logger.warning(f'Agent file update failed: {agent_id}, {e}')
                    agent.file_exists = False

        try:
            db_session.commit()
        except Exception:
            db_session.rollback()
            logger.exception(f'Failed to update agent: {agent_id}')
            raise HTTPException(status_code=500, detail={'error': 'Database error', 'message': 'Failed to update agent record'})

        logger.info(f'Agent updated: {agent_id}')
        return {'agent': agent.to_dict()}

    except HTTPException:
        raise
    except Exception:
        db_session.rollback()
        logger.exception(f'Failed to update agent: {agent_id}')
        raise HTTPException(status_code=500, detail={'error': 'Failed to update agent', 'message': 'An internal error occurred'})


@router.delete('/agents/{agent_id}')
def delete_agent(
    agent_id: str,
    db_session: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
    soft: bool = Query(default=True, description="是否软删除"),
):
    """删除Agent"""
    try:
        fm = get_file_manager()
        if not fm.validate_agent_id(agent_id):
            raise HTTPException(status_code=400, detail={'error': 'Invalid agent_id', 'message': f'agent_id format is invalid: {agent_id}'})

        agent = db_session.query(AgentConfig).filter_by(agent_id=agent_id).first()
        if not agent:
            raise HTTPException(status_code=404, detail={'error': 'Agent not found', 'message': f'Agent {agent_id} does not exist'})

        # 系统 Agent 禁止删除
        if agent.is_system:
            raise HTTPException(status_code=403, detail={'error': 'Forbidden', 'message': f'System agent {agent_id} cannot be deleted'})

        if soft:
            agent.is_enabled = False
            agent.file_exists = False
            agent.source = 'deleted'
            agent.updated_at = utcnow_naive()
            try:
                db_session.commit()
            except Exception:
                db_session.rollback()
                logger.exception(f'Failed to soft-delete agent: {agent_id}')
                raise HTTPException(status_code=500, detail={'error': 'Database error', 'message': 'Failed to soft-delete agent'})
            logger.info(f'Agent soft-deleted: {agent_id}')
            return {'message': f'Agent {agent_id} soft-deleted'}
        else:
            try:
                fm.delete_agent_file(agent_id)
            except (FileNotFoundError, IOError) as e:
                logger.warning(f'Agent file deletion skipped: {agent_id}, {e}')

            db_session.delete(agent)
            try:
                db_session.commit()
            except Exception:
                db_session.rollback()
                logger.exception(f'Failed to hard-delete agent: {agent_id}')
                raise HTTPException(status_code=500, detail={'error': 'Database error', 'message': 'Failed to hard-delete agent'})
            logger.info(f'Agent hard-deleted: {agent_id}')
            return {'message': f'Agent {agent_id} hard-deleted'}

    except HTTPException:
        raise
    except Exception:
        db_session.rollback()
        logger.exception(f'Failed to delete agent: {agent_id}')
        raise HTTPException(status_code=500, detail={'error': 'Failed to delete agent', 'message': 'An internal error occurred'})


@router.post('/agents/{agent_id}/toggle')
def toggle_agent(agent_id: str, db_session: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    """切换Agent启用/禁用状态"""
    try:
        fm = get_file_manager()
        if not fm.validate_agent_id(agent_id):
            raise HTTPException(status_code=400, detail={'error': 'Invalid agent_id', 'message': f'agent_id format is invalid: {agent_id}'})

        agent = db_session.query(AgentConfig).filter_by(agent_id=agent_id).first()
        if not agent:
            raise HTTPException(status_code=404, detail={'error': 'Agent not found', 'message': f'Agent {agent_id} does not exist'})

        agent.is_enabled = not agent.is_enabled
        agent.updated_at = utcnow_naive()

        try:
            db_session.commit()
        except Exception:
            db_session.rollback()
            logger.exception(f'Failed to toggle agent: {agent_id}')
            raise HTTPException(status_code=500, detail={'error': 'Database error', 'message': 'Failed to toggle agent'})

        logger.info(f'Agent toggled: {agent_id} -> is_enabled={agent.is_enabled}')
        return {'agent': agent.to_dict()}

    except HTTPException:
        raise
    except Exception:
        db_session.rollback()
        logger.exception(f'Failed to toggle agent: {agent_id}')
        raise HTTPException(status_code=500, detail={'error': 'Failed to toggle agent', 'message': 'An internal error occurred'})


@router.post('/agents/sync')
def sync_agents(db_session: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    """从文件系统同步Agent到数据库"""
    try:
        fm = get_file_manager()
        agents_dir = fm.agents_dir

        from services.agent_category_service import AgentCategoryService
        category_service = AgentCategoryService()

        file_agents = {}
        if agents_dir.exists():
            for md_file in agents_dir.glob('*.md'):
                agent_id = md_file.stem
                if not fm.validate_agent_id(agent_id):
                    logger.warning(f'Skipping invalid agent_id from file: {agent_id}')
                    continue
                try:
                    with open(md_file, 'r', encoding='utf-8') as f:
                        file_content = f.read()
                    metadata, _ = fm._parse_file_content(file_content)
                    file_agents[agent_id] = (metadata, str(md_file), file_content)
                except Exception as e:
                    logger.warning(f'Failed to parse agent file {md_file}: {e}')

        db_agents = {a.agent_id: a for a in db_session.query(AgentConfig).all()}
        created = updated = removed = 0

        for agent_id, (metadata, file_path, file_content) in file_agents.items():
            name = metadata.get('name', agent_id)
            description = metadata.get('description', '')
            model = metadata.get('model', 'inherit')

            # 从 frontmatter 提取能力声明
            capabilities = metadata.get('capabilities', [])
            if not isinstance(capabilities, list):
                capabilities = []
            tags = metadata.get('tags', [])
            if not isinstance(tags, list):
                tags = []
            preferred_contexts = metadata.get('preferred_contexts', [])
            if not isinstance(preferred_contexts, list):
                preferred_contexts = []
            skill_level = metadata.get('skill_level', 3)
            if not isinstance(skill_level, int):
                skill_level = 3

            # 从 markdown 正文提取角色信息
            sections = _extract_md_sections(file_content)
            role = sections.get('role', '')
            persona = sections.get('persona', '')
            expertise = sections.get('expertise', '')
            approach = sections.get('approach', '')

            if agent_id in db_agents:
                agent = db_agents[agent_id]
                # 跳过已软删除的 Agent（source='deleted'），避免 sync 恢复
                if agent.source == 'deleted':
                    continue
                changed = False
                if agent.name != name: agent.name = name; changed = True
                if agent.description != description: agent.description = description; changed = True
                if agent.model != model: agent.model = model; changed = True
                if not agent.file_exists: agent.file_exists = True; changed = True
                if agent.file_path != file_path: agent.file_path = file_path; changed = True
                # 新字段同步
                if agent.source != 'file': agent.source = 'file'; changed = True
                if not agent.is_system: agent.is_system = True; changed = True
                if agent.content != file_content: agent.content = file_content; changed = True
                if agent.role != role: agent.role = role; changed = True
                if agent.persona != persona: agent.persona = persona; changed = True
                if agent.expertise != expertise: agent.expertise = expertise; changed = True
                if agent.approach != approach: agent.approach = approach; changed = True
                if agent.capabilities != capabilities: agent.capabilities = capabilities; changed = True
                if agent.skill_level != skill_level: agent.skill_level = skill_level; changed = True
                if agent.tags != tags: agent.tags = tags; changed = True
                if agent.preferred_contexts != preferred_contexts: agent.preferred_contexts = preferred_contexts; changed = True
                # category 赋值
                cat = category_service.get_category_for_agent(agent_id)
                if cat and agent.category != cat: agent.category = cat; changed = True
                if changed:
                    agent.updated_at = utcnow_naive()
                    updated += 1
            else:
                agent = AgentConfig(
                    agent_id=agent_id, name=name, description=description,
                    model=model, file_path=file_path, file_exists=True, is_enabled=True,
                    source='file', is_system=True,
                    content=file_content,
                    category=category_service.get_category_for_agent(agent_id),
                    role=role, persona=persona, expertise=expertise, approach=approach,
                    capabilities=capabilities, skill_level=skill_level,
                    tags=tags, preferred_contexts=preferred_contexts,
                )
                db_session.add(agent)
                created += 1

        for agent_id, agent in db_agents.items():
            if agent_id not in file_agents and agent.file_exists:
                agent.file_exists = False
                agent.updated_at = utcnow_naive()
                removed += 1

        try:
            db_session.commit()
        except Exception:
            db_session.rollback()
            logger.exception('Failed to sync agents')
            raise HTTPException(status_code=500, detail={'error': 'Database error', 'message': 'Failed to commit sync results'})

        synced = created + updated + removed
        logger.info(f'Agent sync completed: created={created}, updated={updated}, removed={removed}')
        return {'synced': synced, 'created': created, 'updated': updated, 'removed': removed}

    except HTTPException:
        raise
    except Exception:
        db_session.rollback()
        logger.exception('Failed to sync agents')
        raise HTTPException(status_code=500, detail={'error': 'Failed to sync agents', 'message': 'An internal error occurred'})


@router.post('/agents/backfill-capabilities')
def backfill_capabilities(
    background_tasks: BackgroundTasks,
    db_session: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """批量为 Agent 补全能力声明（后台异步执行，返回 task_id 查询进度）"""
    try:
        from models import BackfillTask

        # 扫描 capabilities 为空的 Agent
        agents = db_session.query(AgentConfig).filter(
            AgentConfig.capabilities.is_(None) | (AgentConfig.capabilities == [])
        ).all()

        if not agents:
            return {'task_id': None, 'total': 0, 'message': 'No agents need backfill'}

        import uuid
        task_id = str(uuid.uuid4())[:8]
        task = BackfillTask(task_id=task_id, status='running', total=len(agents))
        db_session.add(task)
        db_session.commit()

        agent_ids = [a.agent_id for a in agents]
        background_tasks.add_task(_run_backfill, task_id, agent_ids)

        return {'task_id': task_id, 'total': len(agents)}
    except Exception:
        logger.exception('Failed to start backfill')
        raise HTTPException(status_code=500, detail={'error': 'Failed to start backfill'})


@router.get('/agents/backfill-capabilities/{task_id}')
def get_backfill_status(
    task_id: str,
    admin: User = Depends(get_admin_user),
    db_session: Session = Depends(get_db),
):
    """查询 backfill 任务进度"""
    from models import BackfillTask
    task = db_session.query(BackfillTask).filter_by(task_id=task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail={'error': 'Task not found'})
    return task.to_dict()


def _run_backfill(task_id: str, agent_ids: list[str]):
    """后台执行能力补全（独立 DB session，不阻塞请求线程）"""
    from config import Config
    from database import SessionLocal
    from models import BackfillTask
    from services.llm_service import create_llm_service

    db = SessionLocal()
    task = db.query(BackfillTask).filter_by(task_id=task_id).first()
    if not task:
        db.close()
        return

    try:
        llm_service = create_llm_service(
            db_session=db,
            agents_dir=Config.AGENTS_DIR,
            workspace_dir=Config.WORKSPACE_DIR,
        )

        system_prompt = """你是一个 Agent 能力分析器。根据 Agent 的名称、描述和内容，生成结构化的能力声明。

输出格式（严格 JSON，不要其他文字）：
{
  "capabilities": ["能力1", "能力2", "能力3"],
  "tags": ["标签1", "标签2"],
  "skill_level": 4,
  "preferred_contexts": ["场景1", "场景2"]
}

规则：
- capabilities: 3-5 个核心能力，用中文，简短精确
- tags: 2-4 个分类标签
- skill_level: 1-5 整数（1=入门，3=专业，5=顶级专家）
- preferred_contexts: 2-3 个最擅长的应用场景"""

        decoder = json.JSONDecoder()

        for agent_id in agent_ids:
            agent = db.query(AgentConfig).filter_by(agent_id=agent_id).first()
            if not agent:
                task.skipped += 1
                task.processed += 1
                continue

            try:
                content_snippet = (agent.content or '')[:1000]
                user_prompt = f"Agent 名称：{agent.name or agent.agent_id}\n"
                if agent.description:
                    user_prompt += f"描述：{agent.description}\n"
                if content_snippet:
                    user_prompt += f"内容摘要：{content_snippet}\n"

                result = llm_service.call_sync(
                    message=user_prompt,
                    system_prompt=system_prompt,
                    max_tokens=512,
                )

                text = result.strip()
                # 健壮 JSON 提取：从首个 '{' 开始精确解码
                start = text.find('{')
                if start < 0:
                    raise ValueError("LLM output contains no JSON object")
                data, _ = decoder.raw_decode(text, start)

                agent.capabilities = data.get('capabilities', [])
                agent.tags = data.get('tags', [])
                agent.skill_level = data.get('skill_level', 3)
                agent.preferred_contexts = data.get('preferred_contexts', [])
                agent.updated_at = utcnow_naive()
                task.updated += 1

            except Exception as e:
                logger.warning(f'Backfill failed for {agent_id}: {e}')
                task.skipped += 1

            task.processed += 1
            # 每处理一个 agent 就持久化进度
            db.commit()

        task.status = 'completed'
        task.completed_at = utcnow_naive()
        db.commit()
        logger.info(f'Backfill {task_id} completed: processed={task.processed}, updated={task.updated}, skipped={task.skipped}')

    except Exception:
        db.rollback()
        logger.exception(f'Backfill {task_id} failed')
        try:
            task = db.query(BackfillTask).filter_by(task_id=task_id).first()
            if task:
                task.status = 'failed'
                task.completed_at = utcnow_naive()
                db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()


def _extract_md_sections(content: str) -> dict:
    """从 markdown 正文中提取角色相关章节内容。

    匹配 ## Role / ## 角色 / ## Persona / ## 人设 等中英文标题，
    返回各章节的纯文本内容（不含标题行）。
    """
    import re
    sections = {}
    # 匹配 ## 标题行及其内容直到下一个 ## 或文件结束
    pattern = r'^##\s+(.+?)\s*\n(.*?)(?=^##\s|\Z)'
    for match in re.finditer(pattern, content, re.MULTILINE | re.DOTALL):
        title = match.group(1).strip().lower()
        body = match.group(2).strip()
        if 'role' in title or '角色' in title:
            sections['role'] = body[:500]
        elif 'persona' in title or '人设' in title:
            sections['persona'] = body[:1000]
        elif 'expertise' in title or 'core principle' in title or '核心' in title or '专长' in title:
            sections['expertise'] = body[:1000]
        elif 'approach' in title or 'decision framework' in title or 'methodology' in title or '工作方式' in title or '方法论' in title:
            sections['approach'] = body[:1000]
    return sections


# ==================== Agent MCP 权限 ====================


@router.post('/agents/generate')
def generate_agent(
    request: AgentGenerateRequest,
    admin: User = Depends(get_admin_user),
    db_session: Session = Depends(get_db),
):
    """AI 生成 Agent 配置（基于现有 agent 模板）"""
    try:
        from config import Config
        from services.agent_category_service import AgentCategoryService

        category_service = AgentCategoryService()

        # 1. 收集同类 agent 作为 few-shot 示例
        agent_type = (request.agent_type or '').strip()
        example_agents = category_service.get_example_agents_for_category(agent_type) if agent_type else []

        # 读取示例 agent 文件内容
        fm = get_file_manager()
        examples_text = ""
        for aid in example_agents:
            try:
                _meta, md = fm.read_agent_file(aid)
                examples_text += f"\n--- 示例 Agent: {aid} ---\n{md[:1500]}\n"
            except Exception:
                continue

        # 2. 构建 prompt（对用户输入做长度截断和换行清理，防止 prompt 注入）
        system_prompt = """你是一个 Agent 配置生成器。你需要根据用户提供的名称，生成一个完整的 Agent 配置文件的 Markdown 正文部分。

输出格式要求：
- 只输出 Markdown 正文，不要包含 YAML frontmatter（--- 包裹的部分）
- 必须包含以下标准段落：## Role, ## Persona, ## Core Expertise
- 可选段落：## Approach, ## Communication Style, ## Output Format, ## 安全提示
- 内容要专业、详实，每个段落至少 3-5 行
- 使用中文
- 不要输出任何额外说明或代码块标记"""

        def _sanitize(text: str, max_len: int = 200) -> str:
            return (text or '').strip().replace('\n', ' ').replace('\r', '')[:max_len]

        safe_name = _sanitize(request.name, 100)
        safe_desc = _sanitize(request.description, 200)

        user_prompt = f"请为以下 Agent 生成配置内容：\n\n名称：{safe_name}"
        if safe_desc:
            user_prompt += f"\n描述：{safe_desc}"
        if examples_text:
            user_prompt += f"\n\n以下是同类 Agent 的参考示例：{examples_text}"

        # 3. 调用 LLM 生成
        from services.llm_service import create_llm_service
        llm_service = create_llm_service(
            db_session=db_session,
            agents_dir=Config.AGENTS_DIR,
            workspace_dir=Config.WORKSPACE_DIR,
        )

        result = llm_service.call_sync(
            message=user_prompt,
            system_prompt=system_prompt,
            max_tokens=4096,
        )

        if not result or not result.strip():
            raise HTTPException(status_code=502, detail={'error': 'Generation failed', 'message': 'LLM returned empty content'})

        # 4. 清理结果（去掉可能的 code fence 包裹）
        content = result.strip()
        if content.startswith('```markdown'):
            content = content[len('```markdown'):].strip()
        elif content.startswith('```md'):
            content = content[len('```md'):].strip()
        elif content.startswith('```'):
            content = content[3:].strip()
        if content.endswith('```'):
            content = content[:-3].strip()

        # 5. 构建 metadata
        metadata = {
            'name': request.name,
            'description': request.description or f'{request.name}专家',
            'model': 'inherit',
            'priority': 50,
        }

        logger.info(f'Agent config generated for: {request.name}')
        return {'success': True, 'content': content, 'metadata': metadata}

    except HTTPException:
        raise
    except Exception:
        logger.exception('Failed to generate agent config')
        raise HTTPException(status_code=500, detail={'error': 'Generation failed', 'message': 'An internal error occurred'})


# ==================== Agent MCP 权限 ====================

@router.get('/agents/{agent_id}/mcp-tools')
def get_agent_mcp_permissions(agent_id: str, db_session: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    """获取 Agent 的 MCP 工具权限配置"""
    try:
        permissions = db_session.query(AgentMcpPermission).filter_by(agent_id=agent_id).all()
        return {
            'agent_id': agent_id,
            'permissions': [{
                'mcp_tool_pattern': p.mcp_tool_pattern, 'enabled': p.enabled,
                'created_at': p.created_at.isoformat() + 'Z' if p.created_at else None,
                'updated_at': p.updated_at.isoformat() + 'Z' if p.updated_at else None
            } for p in permissions]
        }
    except Exception:
        logger.exception(f'Failed to get agent MCP permissions: {agent_id}')
        raise HTTPException(status_code=500, detail={'error': 'Failed to get agent MCP permissions', 'message': 'An internal error occurred'})


@router.put('/agents/{agent_id}/mcp-tools')
def update_agent_mcp_permissions(
    agent_id: str,
    request: AgentMcpPermissionsUpdateRequest,
    db_session: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """更新 Agent 的 MCP 工具权限配置"""
    try:
        from services.harness.harness_coordinator import clear_registry_cache

        # 校验 agent 存在性
        agent = db_session.query(AgentConfig).filter_by(agent_id=agent_id).first()
        if not agent:
            raise HTTPException(status_code=404, detail={'error': 'Agent not found', 'message': f'Agent {agent_id} does not exist'})

        db_session.query(AgentMcpPermission).filter_by(agent_id=agent_id).delete()

        for p in request.permissions:
            pattern = p.get('mcp_tool_pattern', '').strip()
            if not pattern:
                continue
            db_session.add(AgentMcpPermission(agent_id=agent_id, mcp_tool_pattern=pattern, enabled=p.get('enabled', True)))

        db_session.commit()
        clear_registry_cache()

        logger.info(f'Agent MCP permissions updated: {agent_id}, {len(request.permissions)} patterns')
        return {'success': True, 'updated_count': len(request.permissions)}

    except Exception:
        db_session.rollback()
        logger.exception(f'Failed to update agent MCP permissions: {agent_id}')
        raise HTTPException(status_code=500, detail={'error': 'Failed to update agent MCP permissions', 'message': 'An internal error occurred'})


@router.put('/agent-types/{agent_type}/mcp-tools')
def update_agent_type_mcp_permissions(
    agent_type: str,
    request: AgentMcpPermissionsUpdateRequest,
    db_session: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """批量更新某类型所有 Agent 的 MCP 工具权限配置"""
    try:
        from services.harness.harness_coordinator import get_agents_by_type, clear_registry_cache

        valid_types = ['medical', 'technical', 'business']
        if agent_type not in valid_types:
            raise HTTPException(status_code=400, detail={'error': 'Invalid agent type', 'message': f'agent_type must be one of: {valid_types}'})

        affected_agents = get_agents_by_type(agent_type)

        for agent_id in affected_agents:
            db_session.query(AgentMcpPermission).filter_by(agent_id=agent_id).delete()
            for p in request.permissions:
                pattern = p.get('mcp_tool_pattern', '').strip()
                if not pattern:
                    continue
                db_session.add(AgentMcpPermission(agent_id=agent_id, mcp_tool_pattern=pattern, enabled=p.get('enabled', True)))

        db_session.commit()
        clear_registry_cache()

        logger.info(f'Agent type MCP permissions updated: {agent_type}, {len(affected_agents)} agents')
        return {'success': True, 'affected_agents': affected_agents, 'count': len(affected_agents)}

    except HTTPException:
        raise
    except Exception:
        db_session.rollback()
        logger.exception(f'Failed to update agent type MCP permissions: {agent_type}')
        raise HTTPException(status_code=500, detail={'error': 'Failed to update agent type MCP permissions', 'message': 'An internal error occurred'})


@router.get('/agent-types')
def list_agent_types(admin: User = Depends(get_admin_user), db_session: Session = Depends(get_db)):
    """获取 Agent 类型列表及其 Agent 数量（从 DB 分类动态聚合）"""
    try:
        from models import AgentConfig
        from sqlalchemy import func

        rows = (
            db_session.query(AgentConfig.category, func.count(AgentConfig.id))
            .filter(AgentConfig.is_enabled == True)
            .group_by(AgentConfig.category)
            .all()
        )

        types = []
        for cat, cnt in rows:
            key = cat or 'uncategorized'
            types.append({'type': key, 'count': cnt, 'agents': []})

        return {'types': types}

    except Exception:
        logger.exception('Failed to list agent types')
        raise HTTPException(status_code=500, detail={'error': 'Failed to list agent types', 'message': 'An internal error occurred'})

