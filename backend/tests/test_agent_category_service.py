"""AgentCategoryService 测试

测试动态分类服务：
- get_categories 聚合 + 兜底
- get_category_for_agent 映射
- build_category_tree 构建
"""
import pytest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import AgentConfig
from db import Base


@pytest.fixture
def agents_with_category(client, admin_auth_header):
    """创建带 category 的测试 Agent"""
    from tests.conftest import TestSessionLocal
    session = TestSessionLocal()
    try:
        agents = [
            AgentConfig(agent_id='cardio-test', name='心血管', category='medical',
                        is_enabled=True, is_system=True, source='file'),
            AgentConfig(agent_id='pulmo-test', name='呼吸', category='medical',
                        is_enabled=True, is_system=True, source='file'),
            AgentConfig(agent_id='ceo-test', name='CEO', category='business',
                        is_enabled=True, is_system=True, source='file'),
            AgentConfig(agent_id='custom-test', name='自建', category='custom',
                        is_enabled=True, is_system=False, source='db'),
            AgentConfig(agent_id='uncat-test', name='未分类', category=None,
                        is_enabled=True, is_system=False, source='db'),
            AgentConfig(agent_id='disabled-test', name='禁用', category='medical',
                        is_enabled=False, is_system=True, source='file'),
        ]
        session.add_all(agents)
        session.commit()
        return [a.agent_id for a in agents]
    finally:
        session.close()


# ==================== get_categories 测试 ====================

def test_get_categories_returns_all_and_groups(client, agents_with_category):
    """分类聚合应返回 all + 各分类 count"""
    from tests.conftest import TestSessionLocal
    from services.agent_category_service import AgentCategoryService
    db = TestSessionLocal()
    try:
        svc = AgentCategoryService()
        cats = svc.get_categories(db)

        all_cat = next(c for c in cats if c['key'] == 'all')
        # DB 中已有大量 Agent，all count 远大于 5
        assert all_cat['count'] >= 5

        med_cat = next(c for c in cats if c['key'] == 'medical')
        # 至少包含我们的 2 个 + DB 中已有的
        assert med_cat['count'] >= 2

        biz_cat = next(c for c in cats if c['key'] == 'business')
        assert biz_cat['count'] >= 1

        # uncategorized 可能有（取决于 DB 是否有 category=None 的）
        uncat = next((c for c in cats if c['key'] == '_uncategorized'), None)
        if uncat:
            assert uncat['count'] >= 1
    finally:
        db.close()


def test_get_categories_always_includes_meta_categories(client, agents_with_category):
    """即使某分类下 0 个 Agent，也应显示（含 icon）"""
    from tests.conftest import TestSessionLocal
    from services.agent_category_service import AgentCategoryService
    db = TestSessionLocal()
    try:
        svc = AgentCategoryService()
        cats = svc.get_categories(db)

        # 所有 CATEGORY_META 中的分类都应出现
        keys = [c['key'] for c in cats]
        assert 'medical' in keys
        assert 'business' in keys
        assert 'finance' in keys
        assert 'all' in keys

        # DB 中存在的自定义分类也应出现（Finding 07 修复）
        assert 'custom' in keys

        # 每个分类都有 icon
        for cat in cats:
            if cat['key'] not in ('all', '_uncategorized'):
                assert 'icon' in cat
    finally:
        db.close()


# ==================== get_category_for_agent 测试 ====================

def test_get_category_for_known_agent():
    """已知系统 Agent 应返回正确 category"""
    from services.agent_category_service import AgentCategoryService
    svc = AgentCategoryService()
    assert svc.get_category_for_agent('cardiology-expert') == 'medical'
    assert svc.get_category_for_agent('ceo-bezos') == 'business'
    assert svc.get_category_for_agent('cro-taleb') == 'finance'


def test_get_category_for_unknown_agent():
    """未知 agent_id 应返回 None"""
    from services.agent_category_service import AgentCategoryService
    svc = AgentCategoryService()
    assert svc.get_category_for_agent('nonexistent-agent') is None


# ==================== build_category_tree 测试 ====================

def test_build_category_tree_structure(client, agents_with_category):
    """树应包含 medical/business/finance 三个顶层分类"""
    from tests.conftest import TestSessionLocal
    from services.agent_category_service import AgentCategoryService
    db = TestSessionLocal()
    try:
        svc = AgentCategoryService()
        result = svc.build_category_tree(db)

        assert 'tree' in result
        assert 'agents' in result
        assert 'medical' in result['tree']
        assert 'business' in result['tree']
        assert 'finance' in result['tree']
    finally:
        db.close()


def test_build_category_tree_agents_included(client, agents_with_category):
    """树中各分类应包含对应 Agent"""
    from tests.conftest import TestSessionLocal
    from services.agent_category_service import AgentCategoryService
    db = TestSessionLocal()
    try:
        svc = AgentCategoryService()
        result = svc.build_category_tree(db)

        # 验证树结构正确：medical 分类下直接有 agents 列表（扁平结构）
        assert 'medical' in result['tree']
        med_agents = result['tree']['medical']['agents']
        assert len(med_agents) > 0
        # 每个 agent 应有 id、name、category 字段
        agent = med_agents[0]
        assert 'id' in agent
        assert 'name' in agent
        assert agent.get('category') == 'medical'
    finally:
        db.close()


def test_build_category_tree_total_agents(client, agents_with_category):
    """agents 列表应包含所有已启用 Agent"""
    from tests.conftest import TestSessionLocal
    from services.agent_category_service import AgentCategoryService
    db = TestSessionLocal()
    try:
        svc = AgentCategoryService()
        result = svc.build_category_tree(db)
        # DB 中已有大量 enabled agents + 我们创建的 5 个 enabled
        assert len(result['agents']) >= 5
    finally:
        db.close()


def test_build_category_tree_includes_uncategorized(client, agents_with_category):
    """树应包含 _uncategorized 分类（category 为 NULL 的 Agent）"""
    from tests.conftest import TestSessionLocal
    from services.agent_category_service import AgentCategoryService
    db = TestSessionLocal()
    try:
        svc = AgentCategoryService()
        result = svc.build_category_tree(db)

        # uncat-test 的 category=None，应出现在 _uncategorized 中
        uncat = result['tree'].get('_uncategorized')
        assert uncat is not None
        assert uncat['name'] == '未分类'
        agent_ids = [a['id'] for a in uncat['agents']]
        assert 'uncat-test' in agent_ids
    finally:
        db.close()


# ==================== VALID_CATEGORIES 测试 ====================

def test_valid_categories_fallback():
    """_VALID_CATEGORIES_FALLBACK 应包含标准分类（不含 custom，自建 Agent 走 is_system 筛选）"""
    from services.agent_category_service import _VALID_CATEGORIES_FALLBACK
    assert 'medical' in _VALID_CATEGORIES_FALLBACK
    assert 'business' in _VALID_CATEGORIES_FALLBACK
    assert 'finance' in _VALID_CATEGORIES_FALLBACK
    assert 'custom' not in _VALID_CATEGORIES_FALLBACK
    assert 'invalid' not in _VALID_CATEGORIES_FALLBACK


def test_get_valid_categories_from_db(db_session):
    """_get_valid_categories 应优先从 DB 读取分类"""
    from services.agent_category_service import _get_valid_categories
    from models import AgentCategory

    # 插入自定义分类
    db_session.add(AgentCategory(key='custom', name='自建', sort_order=99))
    db_session.commit()

    result = _get_valid_categories(db_session)
    assert 'custom' in result
    # DB 有数据时不应使用 fallback，而是返回 DB 中的实际 key
    assert isinstance(result, set)


def test_get_valid_categories_fallback_when_empty(db_session):
    """DB 为空时 _get_valid_categories 应回退到 CATEGORY_META"""
    from services.agent_category_service import _get_valid_categories, _VALID_CATEGORIES_FALLBACK
    # 清空 agent_categories 表
    from models import AgentCategory
    db_session.query(AgentCategory).delete()
    db_session.commit()

    result = _get_valid_categories(db_session)
    assert result == _VALID_CATEGORIES_FALLBACK
