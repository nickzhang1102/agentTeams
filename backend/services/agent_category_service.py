"""Agent 分类服务

替代硬编码 agent_categories.py，从 DB 动态生成分类数据。
"""

import logging
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from models import AgentConfig
from services.catalog_localization_service import catalog_localization_service
from utils.locale_utils import SupportedLocale

logger = logging.getLogger(__name__)

# 硬编码兜底元数据（name/icon/color），确保即使无 Agent 也显示分类
CATEGORY_META: dict[str, dict] = {
    'medical':  {'name': '医疗专家', 'icon': '🩺', 'color': '#e74c3c'},
    'business': {'name': '商业角色', 'icon': '💼', 'color': '#3498db'},
    'finance':  {'name': '期货公司', 'icon': '📈', 'color': '#2ecc71'},
    'securities': {'name': '证券公司', 'icon': '📊', 'color': '#9b59b6'},
}

# 已知 agent_id → category 映射表（用于 sync 回填和迁移脚本）
# 来源：agent_categories.py + agent_categories.json
# 注意：这是唯一权威来源，迁移脚本通过 import 引用此常量
AGENT_CATEGORY_MAP: dict[str, str] = {
    # medical - 内科
    'cardiology-expert': 'medical', 'respirology-expert': 'medical',
    'gastroenterology-expert': 'medical', 'endocrinology-expert': 'medical',
    'nephrology-expert': 'medical', 'hematology-expert': 'medical',
    'infectious-disease-expert': 'medical', 'rheumatology-expert': 'medical',
    'neurology-expert': 'medical',
    # medical - 外科
    'general-surgery-expert': 'medical', 'hepatobiliary-surgery-expert': 'medical',
    'gastrointestinal-surgery-expert': 'medical', 'breast-surgery-expert': 'medical',
    'thyroid-surgery-expert': 'medical', 'thoracic-surgery-expert': 'medical',
    'cardiac-surgery-expert': 'medical', 'neurosurgery-expert': 'medical',
    'urology-expert': 'medical', 'orthopedics-expert': 'medical',
    'plastic-surgery-expert': 'medical', 'transplant-surgery-expert': 'medical',
    # medical - 专科
    'allergy-expert': 'medical',
    'gynecology-expert': 'medical', 'reproductive-medicine-expert': 'medical',
    'obstetrics-expert': 'medical', 'pediatrics-expert': 'medical',
    'ophthalmology-expert': 'medical', 'ent-expert': 'medical',
    'dentist-expert': 'medical', 'dermatology-expert': 'medical',
    'psychiatry-expert': 'medical', 'rehabilitation-expert': 'medical',
    'pain-management-expert': 'medical', 'geriatrics-expert': 'medical',
    # medical - 其他
    'oncology-expert': 'medical', 'radiotherapy-expert': 'medical',
    'pathology-expert': 'medical', 'radiology-expert': 'medical',
    'laboratory-expert': 'medical', 'nutrition-expert': 'medical',
    'tcm-expert': 'medical', 'acupuncture-expert': 'medical',
    'tuina-expert': 'medical', 'nursing-expert': 'medical',
    'general-practice-expert': 'medical',
    # business
    'ceo-bezos': 'business', 'cto-vogels': 'business',
    'cfo-campbell': 'business', 'caio-ai': 'business',
    'product-norman': 'business', 'ui-duarte': 'business',
    'interaction-cooper': 'business', 'fullstack-dhh': 'business',
    'devops-hightower': 'business', 'qa-bach': 'business',
    'operations-pg': 'business', 'marketing-godin': 'business',
    'sales-ross': 'business', 'research-thompson': 'business',
    'critic-munger': 'business', 'editor': 'business',
    # finance
    'cio-dalio': 'finance', 'cro-taleb': 'finance',
    'quant-simons': 'finance', 'asset-management': 'finance',
    'macro-analyst': 'finance', 'agriculture-analyst': 'finance',
    'metals-analyst': 'finance', 'chemical-analyst': 'finance',
    'black-analyst': 'finance', 'financial-analyst': 'finance',
    'market-analyst': 'finance',
    # securities - 宏观策略层
    'chief-economist': 'securities', 'chief-strategist': 'securities',
    'fixed-income-strategist': 'securities',
    # securities - 行业分析师层
    'food-beverage-analyst': 'securities', 'pharma-biotech-analyst': 'securities',
    'home-appliance-analyst': 'securities', 'textile-apparel-analyst': 'securities',
    'retail-analyst': 'securities', 'social-service-analyst': 'securities',
    'agribusiness-analyst': 'securities',
    'electronics-analyst': 'securities', 'computer-analyst': 'securities',
    'telecom-analyst': 'securities', 'media-analyst': 'securities',
    'machinery-analyst': 'securities', 'auto-analyst': 'securities',
    'power-equipment-analyst': 'securities', 'defense-analyst': 'securities',
    'light-industry-analyst': 'securities',
    'nonferrous-metals-analyst': 'securities', 'steel-analyst': 'securities',
    'basic-chemicals-analyst': 'securities', 'coal-analyst': 'securities',
    'construction-materials-analyst': 'securities', 'oil-gas-analyst': 'securities',
    'banking-analyst': 'securities', 'nonbank-finance-analyst': 'securities',
    'real-estate-analyst': 'securities',
    'utilities-analyst': 'securities', 'transport-analyst': 'securities',
    # securities - 金融工程层
    'fin-engineer-analyst': 'securities', 'derivatives-analyst': 'securities',
    'asset-allocation-analyst': 'securities',
    # securities - 主题/ESG层
    'esg-analyst': 'securities', 'thematic-analyst': 'securities',
}

# 有效 category 值域（静态兜底，运行时优先从 DB 读取）
_VALID_CATEGORIES_FALLBACK = set(CATEGORY_META.keys())


def _get_valid_categories(db: Session) -> set[str]:
    """从 DB 动态获取有效分类集合，DB 为空时回退到 CATEGORY_META。"""
    from models import AgentCategory
    rows = db.query(AgentCategory.key).all()
    if rows:
        return {r[0] for r in rows}
    return _VALID_CATEGORIES_FALLBACK


def apply_category_filter(query, category: str | None, db: Session | None = None):
    """统一的分类筛选逻辑，供 agent_api 和 agent_admin_api 复用。

    Args:
        query: SQLAlchemy Query 对象
        category: 分类键值（None 表示不筛选）
        db: 数据库会话（用于动态获取有效分类）

    Returns:
        筛选后的 Query 对象

    Raises:
        HTTPException: category 不在有效域内时
    """
    if not category:
        return query
    valid_categories = _get_valid_categories(db) if db else _VALID_CATEGORIES_FALLBACK
    if category == '_uncategorized':
        return query.filter(or_(
            ~AgentConfig.category.in_(valid_categories),
            AgentConfig.category.is_(None)
        ))
    if category not in valid_categories:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"Invalid category: {category}")
    return query.filter(AgentConfig.category == category)


class AgentCategoryService:
    """从 DB 动态生成分类数据，替代硬编码配置文件。"""

    def get_categories(self, db: Session, locale: SupportedLocale = 'zh-CN') -> list[dict]:
        """动态聚合 Agent 分类，从 agent_categories 表读元数据。

        返回格式: [{"key": "all", "name": "全部", "count": 74}, ...]
        """
        # DB 聚合 agent 计数
        rows = (
            db.query(AgentConfig.category, func.count(AgentConfig.id))
            .filter(AgentConfig.is_enabled == True)
            .group_by(AgentConfig.category)
            .all()
        )

        counts: dict[Optional[str], int] = {}
        total = 0
        for cat, cnt in rows:
            counts[cat] = cnt
            total += cnt

        result = [self._localize_category(
            {'key': 'all', 'name': '全部', 'count': total}, locale, is_system=True
        )]

        # 从 agent_categories 表读元数据（优先），CATEGORY_META 兜底
        from models import AgentCategory
        db_categories = db.query(AgentCategory).order_by(AgentCategory.sort_order).all()
        if db_categories:
            meta_iter = [
                (c.key, {'name': c.name, 'icon': c.icon or '', 'color': c.color or ''}, c.is_system)
                for c in db_categories
            ]
        else:
            meta_iter = [(key, meta, True) for key, meta in CATEGORY_META.items()]

        known_keys = set()
        for key, meta, is_system in meta_iter:
            item = {
                'key': key,
                'name': meta['name'],
                'icon': meta.get('icon', ''),
                'color': meta.get('color', ''),
                'count': counts.get(key, 0),
            }
            result.append(self._localize_category(item, locale, is_system=is_system))
            known_keys.add(key)

        # 追加 CATEGORY_META 外的自定义分类（管理员手动配置的 category）
        for key, cnt in counts.items():
            if key and key not in known_keys:
                item = {'key': key, 'name': key, 'icon': '📁', 'color': '', 'count': cnt}
                result.append(self._localize_category(item, locale, is_system=False))

        # NULL 归入"未分类"
        null_count = counts.get(None, 0)
        if null_count > 0:
            item = {'key': '_uncategorized', 'name': '未分类', 'count': null_count}
            result.append(self._localize_category(item, locale, is_system=True))

        return result

    @staticmethod
    def _localize_category(
        item: dict,
        locale: SupportedLocale,
        is_system: bool,
    ) -> dict:
        return catalog_localization_service.localize_item(
            data=item,
            entity_type='agent_category',
            key=item['key'],
            source_name=item.get('name'),
            is_system=is_system,
            locale=locale,
        )

    def get_category_for_agent(self, agent_id: str) -> Optional[str]:
        """从映射表反查系统 Agent 的 category。未知返回 None。"""
        return AGENT_CATEGORY_MAP.get(agent_id)

    def get_example_agents_for_category(self, category: str, limit: int = 2) -> list[str]:
        """返回指定分类下的 agent_id 列表（用于 few-shot 示例）。"""
        agents = [aid for aid, cat in AGENT_CATEGORY_MAP.items() if cat == category]
        return agents[:limit]

    def build_category_tree(
        self,
        db: Session,
        locale: SupportedLocale = 'zh-CN',
    ) -> dict:
        """构建 2 级分类树（供 /agents/tree 端点使用）。

        返回格式: {"medical": {"name": "医疗专家", "icon": "🩺", "agents": [...]}}
        """
        agents = (
            db.query(AgentConfig)
            .filter(AgentConfig.is_enabled == True)
            .order_by(AgentConfig.priority.asc(), AgentConfig.agent_id)
            .all()
        )

        by_category: dict[str, list] = {}
        all_agents = []
        for a in agents:
            d = {
                'id': a.agent_id,
                'name': a.name or a.agent_id,
                'description': a.description or '',
                'model': a.model or 'inherit',
                'category': a.category,
                'priority': a.priority,
                'capabilities': a.capabilities or [],
                'tags': a.tags or [],
                'skill_level': a.skill_level,
            }
            d = catalog_localization_service.localize_item(
                data=d,
                entity_type='agent',
                key=a.agent_id,
                source_name=a.name,
                is_system=a.is_system,
                locale=locale,
            )
            all_agents.append(d)
            cat = a.category or '_uncategorized'
            by_category.setdefault(cat, []).append(d)

        tree = {}
        from models import AgentCategory
        db_categories = db.query(AgentCategory).order_by(AgentCategory.sort_order).all()
        if db_categories:
            for c in db_categories:
                item = {
                    'key': c.key,
                    'name': c.name,
                    'icon': c.icon or '',
                    'agents': by_category.get(c.key, []),
                }
                tree[c.key] = self._localize_category(item, locale, c.is_system)
        else:
            for key, meta in CATEGORY_META.items():
                item = {
                    'key': key,
                    'name': meta['name'],
                    'icon': meta['icon'],
                    'agents': by_category.get(key, []),
                }
                tree[key] = self._localize_category(item, locale, True)

        # 未分类 Agent（category IS NULL）
        uncategorized = by_category.get('_uncategorized', [])
        if uncategorized:
            item = {
                'key': '_uncategorized',
                'name': '未分类',
                'icon': '❓',
                'agents': uncategorized,
            }
            tree['_uncategorized'] = self._localize_category(item, locale, True)

        return {'tree': tree, 'agents': all_agents}
