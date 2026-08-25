"""
Agent Pack 服务层

提供 Agent 组合包的 CRUD、权限校验、Agent 引用验证和克隆功能。
"""
import logging
from typing import Optional, List

from sqlalchemy.orm import Session
from sqlalchemy import or_, func

from models import AgentPack, AgentConfig
from services.catalog_localization_service import catalog_localization_service
from utils.locale_utils import SupportedLocale

logger = logging.getLogger(__name__)


class AgentPackService:
    """Agent 组合包服务"""

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def serialize_pack(pack: AgentPack, locale: SupportedLocale) -> dict:
        return catalog_localization_service.localize_item(
            data=pack.to_dict(),
            entity_type='agent_pack',
            key=pack.catalog_key,
            source_name=pack.name,
            is_system=pack.is_system,
            locale=locale,
        )

    def validate_agents(self, agents: List[dict]) -> List[str]:
        """校验 agents 中每个 agent_id 是否存在且已启用。

        Returns:
            无效 agent_id 列表（空列表 = 全部有效）
        """
        ids = [item.get('agent_id', '') for item in agents if item.get('agent_id')]
        if not ids:
            return []
        configs = {
            c.agent_id: c
            for c in self.db.query(AgentConfig).filter(AgentConfig.agent_id.in_(ids)).all()
        }
        return [aid for aid in ids if aid not in configs or not configs[aid].is_enabled]

    def create_pack(
        self,
        name: str,
        agents: list[dict],
        user_id: int,
        description: Optional[str] = None,
        category: str = 'custom',
        tags: Optional[list] = None,
        is_system: bool = False,
    ) -> AgentPack:
        """创建组合包。"""
        # 系统 Pack 应用层查重（DB unique constraint 对 NULL creator_id 无效）
        if is_system:
            existing = self.db.query(AgentPack).filter_by(name=name, is_system=True).first()
            if existing:
                raise ValueError(f'系统预设组合包 "{name}" 已存在')

        pack = AgentPack(
            name=name,
            description=description,
            category=category,
            is_system=is_system,
            creator_id=None if is_system else user_id,
            agents=agents,
            tags=tags or [],
        )
        self.db.add(pack)
        self.db.commit()
        self.db.refresh(pack)
        return pack

    def list_packs(
        self,
        user_id: int,
        category: Optional[str] = None,
        is_system: Optional[bool] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[List[AgentPack], int]:
        """列出组合包：系统预设 + 当前用户自建。"""
        query = self.db.query(AgentPack).filter(
            or_(
                AgentPack.is_system == True,
                AgentPack.creator_id == user_id,
            )
        )

        if category:
            query = query.filter(AgentPack.category == category)
        if is_system is not None:
            query = query.filter(AgentPack.is_system == is_system)

        total = query.count()
        packs = (
            query
            .order_by(AgentPack.is_system.desc(), AgentPack.usage_count.desc(), AgentPack.id.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )
        return packs, total

    def get_pack(self, pack_id: int, user_id: Optional[int] = None) -> Optional[AgentPack]:
        """获取单个组合包。仅返回系统预设或当前用户自建的 Pack。"""
        pack = self.db.get(AgentPack, pack_id)
        if not pack:
            return None
        if user_id is not None and not pack.is_system and pack.creator_id != user_id:
            return None
        return pack

    def update_pack(
        self,
        pack_id: int,
        user_id: int,
        is_admin: bool = False,
        **kwargs,
    ) -> AgentPack:
        """更新组合包。系统 Pack 禁止修改，非创建者禁止修改。"""
        pack = self.db.get(AgentPack, pack_id)
        if not pack:
            raise ValueError('组合包不存在')
        if pack.is_system:
            raise PermissionError('系统预设组合包不可修改')
        if not is_admin and pack.creator_id != user_id:
            raise PermissionError('无权修改此组合包')

        NULLABLE_FIELDS = ('description', 'tags')

        for key in ('name', 'description', 'category', 'agents', 'tags'):
            if key in kwargs:
                if kwargs[key] is None and key in NULLABLE_FIELDS:
                    setattr(pack, key, None)  # 显式清空
                elif kwargs[key] is not None:
                    setattr(pack, key, kwargs[key])

        self.db.commit()
        self.db.refresh(pack)
        return pack

    def delete_pack(self, pack_id: int, user_id: int, is_admin: bool = False) -> bool:
        """删除组合包。系统 Pack 禁止删除，非创建者禁止删除。"""
        pack = self.db.get(AgentPack, pack_id)
        if not pack:
            raise ValueError('组合包不存在')
        if pack.is_system:
            raise PermissionError('系统预设组合包不可删除')
        if not is_admin and pack.creator_id != user_id:
            raise PermissionError('无权删除此组合包')

        self.db.delete(pack)
        self.db.commit()
        return True

    def clone_pack(self, pack_id: int, user_id: int) -> AgentPack:
        """克隆组合包为用户自建副本。仅允许克隆系统 Pack 或自己的 Pack。"""
        source = self.db.get(AgentPack, pack_id)
        if not source:
            raise ValueError('组合包不存在')
        if not source.is_system and source.creator_id != user_id:
            raise PermissionError('仅允许克隆系统预设组合包或自己的组合包')

        # 避免 name+creator_id 唯一约束冲突：追加序号
        base_name = f"{source.name}（副本）"
        name = base_name
        counter = 1
        while self.db.query(func.count()).filter(
            AgentPack.name == name,
            AgentPack.creator_id == user_id,
        ).scalar() > 0:
            counter += 1
            name = f"{base_name}{counter}"

        clone = AgentPack(
            name=name,
            description=source.description,
            category=source.category,
            is_system=False,
            creator_id=user_id,
            agents=source.agents,
            tags=source.tags or [],
        )
        self.db.add(clone)
        self.db.commit()
        self.db.refresh(clone)
        return clone
