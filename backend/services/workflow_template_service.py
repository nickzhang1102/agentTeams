"""
工作流模板服务层

提供工作流模板的 CRUD、权限校验和 Agent 列表解析功能。
"""
import logging
from typing import Optional, List, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import or_

from models import WorkflowTemplate, AgentPack, AgentConfig
from schemas.leader import normalize_category_key
from services.catalog_localization_service import catalog_localization_service
from utils.locale_utils import SupportedLocale

logger = logging.getLogger(__name__)


class WorkflowTemplateService:
    """工作流模板服务"""

    def __init__(self, db: Session):
        self.db = db

    def serialize_templates(
        self,
        templates: List[WorkflowTemplate],
        locale: SupportedLocale,
    ) -> List[dict]:
        """Serialize templates and nested Agents with two bulk lookups."""
        pack_ids = {template.pack_id for template in templates if template.pack_id}
        packs = (
            self.db.query(AgentPack).filter(AgentPack.id.in_(pack_ids)).all()
            if pack_ids else []
        )
        pack_map = {pack.id: pack for pack in packs}

        raw_agents_by_template = {}
        agent_ids = set()
        for template in templates:
            pack = pack_map.get(template.pack_id)
            raw_agents = (pack.agents if pack and pack.agents else template.agents) or []
            raw_agents_by_template[template.id] = raw_agents
            agent_ids.update(
                item.get('agent_id') for item in raw_agents if item.get('agent_id')
            )

        agents = (
            self.db.query(AgentConfig).filter(AgentConfig.agent_id.in_(agent_ids)).all()
            if agent_ids else []
        )
        agent_map = {agent.agent_id: agent for agent in agents}

        result = []
        for template in templates:
            data = template.to_dict()
            data['resolved_agents'] = [
                self._serialize_resolved_agent(item, index, agent_map, locale)
                for index, item in enumerate(raw_agents_by_template[template.id])
            ]
            result.append(catalog_localization_service.localize_item(
                data=data,
                entity_type='workflow_template',
                key=template.catalog_key,
                source_name=template.name,
                is_system=template.is_system,
                locale=locale,
            ))
        return result

    @staticmethod
    def _serialize_resolved_agent(
        item: dict,
        index: int,
        agent_map: dict[str, AgentConfig],
        locale: SupportedLocale,
    ) -> dict:
        agent_id = item.get('agent_id', '')
        agent = agent_map.get(agent_id)
        source_name = agent.name if agent and agent.name else agent_id
        data = {
            'agent_id': agent_id,
            'role': item.get('role', ''),
            'order': item.get('order', index + 1),
            'name': source_name,
        }
        return catalog_localization_service.localize_item(
            data=data,
            entity_type='agent',
            key=agent_id,
            source_name=source_name,
            is_system=agent.is_system if agent else True,
            locale=locale,
        )

    def serialize_template(
        self,
        template: WorkflowTemplate,
        locale: SupportedLocale,
    ) -> dict:
        return self.serialize_templates([template], locale)[0]

    def create_template(
        self,
        name: str,
        user_id: int,
        description: Optional[str] = None,
        category: str = 'custom',
        pack_id: Optional[int] = None,
        agents: Optional[list] = None,
        skip_assessment: bool = False,
        assessment_threshold: int = 60,
        system_prompt_addition: Optional[str] = None,
        is_system: bool = False,
    ) -> WorkflowTemplate:
        # 系统模板应用层查重（DB unique constraint 对 NULL creator_id 无效）
        if is_system:
            existing = self.db.query(WorkflowTemplate).filter_by(name=name, is_system=True).first()
            if existing:
                raise ValueError(f'系统预设模板 "{name}" 已存在')

        template = WorkflowTemplate(
            name=name,
            description=description,
            category=category,
            is_system=is_system,
            creator_id=None if is_system else user_id,
            pack_id=pack_id,
            agents=agents,
            skip_assessment=skip_assessment,
            assessment_threshold=assessment_threshold,
            system_prompt_addition=system_prompt_addition,
        )
        self.db.add(template)
        self.db.commit()
        self.db.refresh(template)
        return template

    def list_templates(
        self,
        user_id: int,
        category: Optional[str] = None,
        is_system: Optional[bool] = None,
        skip_assessment: Optional[bool] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> Tuple[List[WorkflowTemplate], int]:
        query = self.db.query(WorkflowTemplate).filter(
            or_(
                WorkflowTemplate.is_system == True,
                WorkflowTemplate.creator_id == user_id,
            )
        )
        if category:
            query = query.filter(WorkflowTemplate.category == category)
        if is_system is not None:
            query = query.filter(WorkflowTemplate.is_system == is_system)
        if skip_assessment is not None:
            query = query.filter(WorkflowTemplate.skip_assessment == skip_assessment)

        total = query.count()
        templates = (
            query
            .order_by(WorkflowTemplate.is_system.desc(), WorkflowTemplate.usage_count.desc(), WorkflowTemplate.id.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )
        return templates, total

    def get_template(self, template_id: int, user_id: Optional[int] = None) -> Optional[WorkflowTemplate]:
        template = self.db.get(WorkflowTemplate, template_id)
        if not template:
            return None
        if user_id is not None and not template.is_system and template.creator_id != user_id:
            return None
        return template

    def update_template(
        self,
        template_id: int,
        user_id: int,
        is_admin: bool = False,
        **kwargs,
    ) -> WorkflowTemplate:
        template = self.db.get(WorkflowTemplate, template_id)
        if not template:
            raise ValueError('模板不存在')
        if template.is_system:
            raise PermissionError('系统预设模板不可修改')
        if not is_admin and template.creator_id != user_id:
            raise PermissionError('无权修改此模板')

        for key in ('name', 'description', 'category', 'pack_id', 'agents',
                     'skip_assessment', 'assessment_threshold', 'system_prompt_addition'):
            if key in kwargs and kwargs[key] is not None:
                setattr(template, key, kwargs[key])

        # 允许显式清空的可空字段（用户传 null 时生效）
        NULLABLE_FIELDS = ('description', 'system_prompt_addition', 'pack_id', 'agents')
        for key in NULLABLE_FIELDS:
            if key in kwargs and kwargs[key] is None:
                setattr(template, key, None)

        self.db.commit()
        self.db.refresh(template)
        return template

    def delete_template(self, template_id: int, user_id: int, is_admin: bool = False) -> bool:
        template = self.db.get(WorkflowTemplate, template_id)
        if not template:
            raise ValueError('模板不存在')
        if template.is_system:
            raise PermissionError('系统预设模板不可删除')
        if not is_admin and template.creator_id != user_id:
            raise PermissionError('无权删除此模板')

        self.db.delete(template)
        self.db.commit()
        return True

    def resolve_agent_ids(self, template: WorkflowTemplate) -> List[str]:
        """从模板解析 agent_id 列表。优先 pack_id，否则直接用 agents 字段。"""
        if template.pack_id:
            pack = self.db.get(AgentPack, template.pack_id)
            if pack and pack.agents:
                return [a.get('agent_id', '') for a in pack.agents if a.get('agent_id')]
        if template.agents:
            return [a.get('agent_id', '') for a in template.agents if a.get('agent_id')]
        return []

    def resolve_case_category(self, template: WorkflowTemplate) -> str:
        """解析模板启动的案例分类。优先模板分类，custom/未知时回退到引用的组合包分类。"""
        template_category = normalize_category_key(template.category)
        if template_category != 'other':
            return template_category

        if template.pack_id:
            pack = self.db.get(AgentPack, template.pack_id)
            if pack:
                pack_category = normalize_category_key(pack.category)
                if pack_category != 'other':
                    return pack_category

        return 'other'

    def validate_agents(self, agent_ids: List[str]) -> List[str]:
        """校验 agent_id 列表是否全部存在且已启用。返回无效列表。

        复用 AgentPackService.validate_agents 的逻辑。
        """
        from services.agent_pack_service import AgentPackService
        return AgentPackService(self.db).validate_agents(
            [{'agent_id': aid} for aid in agent_ids]
        )
