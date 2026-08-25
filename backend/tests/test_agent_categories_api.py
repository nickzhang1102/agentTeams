"""Agent 分类 API 测试

测试：
- GET /api/agents/categories 端点
- GET /api/user/agents?category= 筛选
- GET /api/admin/agents?category= 筛选
- 无效 category 返回 400
"""
import pytest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import AgentConfig


@pytest.fixture
def categorized_agents(client, admin_auth_header):
    """创建带 category 的测试 Agent"""
    from tests.conftest import TestSessionLocal
    session = TestSessionLocal()
    try:
        agents = [
            AgentConfig(agent_id='cat-med-1', name='医学A', category='medical',
                        is_enabled=True, is_system=True, source='file'),
            AgentConfig(agent_id='cat-med-2', name='医学B', category='medical',
                        is_enabled=True, is_system=True, source='file'),
            AgentConfig(agent_id='cat-biz-1', name='商业A', category='business',
                        is_enabled=True, is_system=True, source='file'),
            AgentConfig(agent_id='cat-fin-1', name='金融A', category='finance',
                        is_enabled=False, is_system=True, source='file'),
        ]
        session.add_all(agents)
        session.commit()
    finally:
        session.close()


# ==================== GET /api/agents/categories ====================

def test_categories_endpoint_success(client, auth_header, categorized_agents):
    """分类端点应返回分类列表含 count"""
    response = client.get('/api/agents/categories', headers=auth_header)
    assert response.status_code == 200
    data = response.json()
    assert 'categories' in data
    cats = data['categories']

    all_cat = next(c for c in cats if c['key'] == 'all')
    assert all_cat['count'] >= 3  # 至少 3 enabled

    med_cat = next(c for c in cats if c['key'] == 'medical')
    assert med_cat['count'] >= 2  # DB 中已有 medical agents

    biz_cat = next(c for c in cats if c['key'] == 'business')
    assert biz_cat['count'] >= 1


def test_categories_endpoint_requires_auth(client):
    """未登录应返回 401"""
    response = client.get('/api/agents/categories')
    assert response.status_code in (401, 403)


# ==================== GET /api/user/agents?category= ====================

def test_user_agents_filter_by_category(client, auth_header, categorized_agents):
    """用户端 category 筛选应只返回对应分类"""
    response = client.get('/api/user/agents?category=medical', headers=auth_header)
    assert response.status_code == 200
    data = response.json()
    # DB 中已有大量 medical agents + 我们的 2 个
    assert data['total'] >= 2
    for agent in data['agents']:
        assert agent['category'] == 'medical'


def test_user_agents_filter_business(client, auth_header, categorized_agents):
    """business 筛选"""
    response = client.get('/api/user/agents?category=business', headers=auth_header)
    assert response.status_code == 200
    data = response.json()
    # DB 中已有 business agents + 我们的 1 个
    assert data['total'] >= 1
    for agent in data['agents']:
        assert agent['category'] == 'business'


def test_user_agents_invalid_category_returns_400(client, auth_header):
    """无效 category 应返回 400"""
    response = client.get('/api/user/agents?category=invalid_cat', headers=auth_header)
    assert response.status_code == 400


# ==================== GET /api/admin/agents?category= ====================

def test_admin_agents_filter_by_category(client, admin_auth_header, categorized_agents):
    """管理端 category 筛选"""
    response = client.get('/api/admin/agents?category=medical', headers=admin_auth_header)
    assert response.status_code == 200
    data = response.json()
    # DB 中已有大量 medical agents + 我们的 2 个
    assert data['total'] >= 2


def test_admin_agents_filter_finance(client, admin_auth_header, categorized_agents):
    """管理端筛选 finance（含 disabled）"""
    response = client.get('/api/admin/agents?category=finance', headers=admin_auth_header)
    assert response.status_code == 200
    data = response.json()
    # DB 中已有 finance agents + 我们的 1 个（disabled）
    assert data['total'] >= 1


def test_admin_agents_invalid_category_returns_400(client, admin_auth_header):
    """管理端无效 category 应返回 400"""
    response = client.get('/api/admin/agents?category=xyz', headers=admin_auth_header)
    assert response.status_code == 400


# ==================== category in to_dict ====================

def test_agent_to_dict_includes_category(client, auth_header, categorized_agents):
    """Agent to_dict 应包含 category 字段"""
    response = client.get('/api/user/agents?category=medical', headers=auth_header)
    data = response.json()
    agent = data['agents'][0]
    assert 'category' in agent
    assert agent['category'] == 'medical'


# ==================== _uncategorized 筛选 ====================

def test_user_agents_filter_uncategorized(client, auth_header, categorized_agents):
    """_uncategorized 筛选应返回 category 为 NULL 的 Agent"""
    response = client.get('/api/user/agents?category=_uncategorized', headers=auth_header)
    assert response.status_code == 200
    data = response.json()
    for agent in data['agents']:
        assert agent['category'] is None


def test_admin_agents_filter_uncategorized(client, admin_auth_header, categorized_agents):
    """管理端 _uncategorized 筛选"""
    response = client.get('/api/admin/agents?category=_uncategorized', headers=admin_auth_header)
    assert response.status_code == 200
