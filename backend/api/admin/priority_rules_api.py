"""优先级规则 API

提供 Agent 优先级规则 CRUD 和 seed 预置。
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from api.deps import get_admin_user
from models import User, AgentPriorityRule
from utils.time_utils import utcnow_naive
from api.admin.admin_helpers import paginate
from api.admin.admin_schemas import PriorityRuleCreateRequest, PriorityRuleUpdateRequest
from api.admin.priority_rules_seed import DEFAULT_PRIORITY_RULES


logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin-priority-rules"])


@router.get('/priority-rules')
def list_priority_rules(
    db_session: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    agent_id: Optional[str] = Query(default=None),
    trigger_scene: Optional[str] = Query(default=None),
    trigger_risk_level: Optional[str] = Query(default=None),
    is_active: Optional[str] = Query(default=None),
):
    """获取 Agent 优先级规则列表（支持分页和筛选）"""
    try:
        query = db_session.query(AgentPriorityRule)

        if agent_id:
            query = query.filter(AgentPriorityRule.agent_id.ilike(f'%{agent_id.strip()}%'))
        if trigger_scene:
            query = query.filter(AgentPriorityRule.trigger_scene == trigger_scene.strip())
        if trigger_risk_level:
            query = query.filter(AgentPriorityRule.trigger_risk_level == trigger_risk_level.strip())
        if is_active is not None:
            if is_active.lower() in ('true', '1', 'yes'):
                query = query.filter_by(is_active=True)
            elif is_active.lower() in ('false', '0', 'no'):
                query = query.filter_by(is_active=False)

        query = query.order_by(AgentPriorityRule.rule_priority.desc(), AgentPriorityRule.created_at.desc())
        pagination = paginate(query, page, per_page)

        return {
            'rules': [r.to_dict() for r in pagination['items']],
            'total': pagination['total'], 'page': pagination['page'],
            'per_page': pagination['per_page'], 'pages': pagination['pages']
        }

    except Exception:
        logger.exception('Failed to list priority rules')
        raise HTTPException(status_code=500, detail={'error': 'Failed to list priority rules', 'message': 'An internal error occurred'})


@router.post('/priority-rules')
def create_priority_rule(
    request: PriorityRuleCreateRequest,
    db_session: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """创建 Agent 优先级规则"""
    try:
        rule = AgentPriorityRule(
            trigger_scene=request.trigger_scene, trigger_risk_level=request.trigger_risk_level,
            trigger_category=request.trigger_category, agent_id=request.agent_id,
            priority=request.priority, rule_priority=request.rule_priority or 0,
            description=request.description,
            is_active=request.is_active if request.is_active is not None else True
        )
        db_session.add(rule)

        try:
            db_session.commit()
        except Exception:
            db_session.rollback()
            logger.exception('Failed to create priority rule')
            raise HTTPException(status_code=500, detail={'error': 'Database error', 'message': 'Failed to create priority rule'})

        logger.info(f'Priority rule created: id={rule.id}, agent={request.agent_id}, priority={request.priority}')
        return {'rule': rule.to_dict()}

    except HTTPException:
        raise
    except Exception:
        db_session.rollback()
        logger.exception('Failed to create priority rule')
        raise HTTPException(status_code=500, detail={'error': 'Failed to create priority rule', 'message': 'An internal error occurred'})


@router.put('/priority-rules/{rule_id}')
def update_priority_rule(
    rule_id: int,
    request: PriorityRuleUpdateRequest,
    db_session: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """更新 Agent 优先级规则"""
    try:
        rule = db_session.get(AgentPriorityRule, rule_id)
        if not rule:
            raise HTTPException(status_code=404, detail={'error': 'Not found', 'message': f'Priority rule {rule_id} does not exist'})

        if request.trigger_scene is not None: rule.trigger_scene = request.trigger_scene
        if request.trigger_risk_level is not None: rule.trigger_risk_level = request.trigger_risk_level
        if request.trigger_category is not None: rule.trigger_category = request.trigger_category
        if request.agent_id is not None: rule.agent_id = request.agent_id.strip()
        if request.priority is not None: rule.priority = request.priority
        if request.rule_priority is not None: rule.rule_priority = request.rule_priority
        if request.description is not None: rule.description = request.description
        if request.is_active is not None: rule.is_active = request.is_active

        rule.updated_at = utcnow_naive()

        try:
            db_session.commit()
        except Exception:
            db_session.rollback()
            logger.exception(f'Failed to update priority rule: {rule_id}')
            raise HTTPException(status_code=500, detail={'error': 'Database error', 'message': 'Failed to update priority rule'})

        logger.info(f'Priority rule updated: id={rule_id}')
        return {'rule': rule.to_dict()}

    except HTTPException:
        raise
    except Exception:
        db_session.rollback()
        logger.exception(f'Failed to update priority rule: {rule_id}')
        raise HTTPException(status_code=500, detail={'error': 'Failed to update priority rule', 'message': 'An internal error occurred'})


@router.delete('/priority-rules/{rule_id}')
def delete_priority_rule(rule_id: int, db_session: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    """删除 Agent 优先级规则"""
    try:
        rule = db_session.get(AgentPriorityRule, rule_id)
        if not rule:
            raise HTTPException(status_code=404, detail={'error': 'Not found', 'message': f'Priority rule {rule_id} does not exist'})

        db_session.delete(rule)
        try:
            db_session.commit()
        except Exception:
            db_session.rollback()
            logger.exception(f'Failed to delete priority rule: {rule_id}')
            raise HTTPException(status_code=500, detail={'error': 'Database error', 'message': 'Failed to delete priority rule'})

        logger.info(f'Priority rule deleted: id={rule_id}')
        return {'message': f'Priority rule {rule_id} deleted'}

    except HTTPException:
        raise
    except Exception:
        db_session.rollback()
        logger.exception(f'Failed to delete priority rule: {rule_id}')
        raise HTTPException(status_code=500, detail={'error': 'Failed to delete priority rule', 'message': 'An internal error occurred'})


@router.post('/priority-rules/seed')
def seed_priority_rules(db_session: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    """预置默认 Agent 优先级规则"""
    try:
        seeded = 0
        seeded_rules = []

        for rule_config in DEFAULT_PRIORITY_RULES:
            existing = db_session.query(AgentPriorityRule).filter_by(
                trigger_scene=rule_config['trigger_scene'],
                trigger_risk_level=rule_config['trigger_risk_level'],
                trigger_category=rule_config['trigger_category'],
                agent_id=rule_config['agent_id']
            ).first()

            if existing:
                continue

            rule = AgentPriorityRule(
                trigger_scene=rule_config['trigger_scene'],
                trigger_risk_level=rule_config['trigger_risk_level'],
                trigger_category=rule_config['trigger_category'],
                agent_id=rule_config['agent_id'],
                priority=rule_config['priority'],
                rule_priority=rule_config['rule_priority'],
                description=rule_config['description'],
                is_active=True
            )
            db_session.add(rule)
            seeded += 1
            seeded_rules.append(rule)

        try:
            db_session.commit()
        except Exception:
            db_session.rollback()
            logger.exception('Failed to seed priority rules')
            raise HTTPException(status_code=500, detail={'error': 'Database error', 'message': 'Failed to seed priority rules'})

        logger.info(f'Priority rules seeded: {seeded} new rules')
        return {'seeded': seeded, 'rules': [r.to_dict() for r in seeded_rules]}

    except HTTPException:
        raise
    except Exception:
        db_session.rollback()
        logger.exception('Failed to seed priority rules')
        raise HTTPException(status_code=500, detail={'error': 'Failed to seed priority rules', 'message': 'An internal error occurred'})

