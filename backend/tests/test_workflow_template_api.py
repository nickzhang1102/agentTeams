"""Workflow Template API 测试

测试工作流模板的 CRUD、权限控制和 apply 功能。
"""
import pytest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import User, AgentConfig, AgentPack, WorkflowTemplate


# ==================== fixture ====================

@pytest.fixture
def sample_agents_for_template(client, admin_auth_header):
    """创建测试用 Agent"""
    from tests.conftest import TestSessionLocal
    session = TestSessionLocal()
    try:
        agents = []
        for aid, enabled in [
            ('tmpl-agent-a', True),
            ('tmpl-agent-b', True),
            ('tmpl-agent-c', False),
        ]:
            agent = AgentConfig(
                agent_id=aid,
                name=f'Agent {aid}',
                description=f'Test agent {aid}',
                model='inherit',
                is_enabled=enabled,
                file_exists=True,
            )
            session.add(agent)
            agents.append(aid)
        session.commit()
        return agents
    finally:
        session.close()


@pytest.fixture
def sample_pack_for_template(client, sample_agents_for_template):
    """创建测试用 AgentPack"""
    from tests.conftest import TestSessionLocal
    session = TestSessionLocal()
    try:
        pack = AgentPack(
            name='模板测试包',
            description='用于模板测试',
            category='business',
            is_system=True,
            creator_id=None,
            agents=[
                {'agent_id': 'tmpl-agent-a', 'role': '主分析', 'order': 1},
                {'agent_id': 'tmpl-agent-b', 'role': '辅助', 'order': 2},
            ],
            tags=['test'],
        )
        session.add(pack)
        session.commit()
        session.refresh(pack)
        return pack.id
    finally:
        session.close()


@pytest.fixture
def normal_user(client, auth_header):
    """获取普通用户信息"""
    resp = client.get('/api/auth/me', headers=auth_header)
    data = resp.json()
    return {'id': data['id'], 'username': data['username']}


@pytest.fixture
def other_user(client):
    """创建另一个普通用户"""
    from tests.conftest import TestSessionLocal
    session = TestSessionLocal()
    try:
        user = User(username='other_tmpl_user', email='other_tmpl@test.com', is_admin=False)
        user.set_password('Test1234!')
        session.add(user)
        session.commit()
        session.refresh(user)
        return {'id': user.id, 'username': user.username}
    finally:
        session.close()


@pytest.fixture
def system_template(client, sample_agents_for_template):
    """创建系统预设模板"""
    from tests.conftest import TestSessionLocal
    session = TestSessionLocal()
    try:
        tmpl = WorkflowTemplate(
            name='系统医疗模板',
            description='系统预设',
            category='medical',
            is_system=True,
            creator_id=None,
            agents=[{'agent_id': 'tmpl-agent-a', 'role': '主导', 'order': 1}],
            skip_assessment=False,
            assessment_threshold=60,
        )
        session.add(tmpl)
        session.commit()
        session.refresh(tmpl)
        return tmpl.id
    finally:
        session.close()


@pytest.fixture
def user_template(client, sample_agents_for_template, normal_user):
    """创建用户自建模板"""
    from tests.conftest import TestSessionLocal
    session = TestSessionLocal()
    try:
        tmpl = WorkflowTemplate(
            name='我的模板',
            description='用户自建',
            category='custom',
            is_system=False,
            creator_id=normal_user['id'],
            agents=[{'agent_id': 'tmpl-agent-a', 'role': '分析', 'order': 1}],
            skip_assessment=True,
            assessment_threshold=50,
        )
        session.add(tmpl)
        session.commit()
        session.refresh(tmpl)
        return tmpl.id
    finally:
        session.close()


@pytest.fixture
def other_user_template(client, sample_agents_for_template, other_user):
    """创建其他用户的模板"""
    from tests.conftest import TestSessionLocal
    session = TestSessionLocal()
    try:
        tmpl = WorkflowTemplate(
            name='别人的模板',
            category='custom',
            is_system=False,
            creator_id=other_user['id'],
            agents=[{'agent_id': 'tmpl-agent-a', 'role': '分析', 'order': 1}],
        )
        session.add(tmpl)
        session.commit()
        session.refresh(tmpl)
        return tmpl.id
    finally:
        session.close()


# ==================== 创建 ====================

def test_create_template_with_agents(client, auth_header, sample_agents_for_template):
    """创建模板（直接 agents）→ 201"""
    resp = client.post('/api/workflow-templates', headers=auth_header, json={
        'name': '测试模板A',
        'category': 'business',
        'agents': [
            {'agent_id': 'tmpl-agent-a', 'role': '主分析', 'order': 1},
            {'agent_id': 'tmpl-agent-b', 'role': '辅助', 'order': 2},
        ],
        'skip_assessment': True,
        'assessment_threshold': 70,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data['name'] == '测试模板A'
    assert data['is_system'] is False
    assert len(data['agents']) == 2
    assert data['skip_assessment'] is True
    assert data['assessment_threshold'] == 70


def test_create_template_with_pack(client, auth_header, sample_pack_for_template):
    """创建模板（引用 pack_id）→ 201"""
    resp = client.post('/api/workflow-templates', headers=auth_header, json={
        'name': '测试模板B',
        'pack_id': sample_pack_for_template,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data['pack_id'] == sample_pack_for_template


def test_create_template_pack_and_agents_conflict(client, auth_header, sample_pack_for_template, sample_agents_for_template):
    """pack_id 和 agents 同时指定 → 400"""
    resp = client.post('/api/workflow-templates', headers=auth_header, json={
        'name': '冲突模板',
        'pack_id': sample_pack_for_template,
        'agents': [{'agent_id': 'tmpl-agent-a', 'role': '分析', 'order': 1}],
    })
    assert resp.status_code == 400
    assert '不能同时指定' in resp.json()['detail']['error']


def test_create_template_skip_without_agents(client, auth_header):
    """快速模式无 agents → 400"""
    resp = client.post('/api/workflow-templates', headers=auth_header, json={
        'name': '空快速模板',
        'skip_assessment': True,
    })
    assert resp.status_code == 400
    assert '必须指定' in resp.json()['detail']['error']


def test_create_template_with_disabled_agent(client, auth_header, sample_agents_for_template):
    """引用禁用 Agent → 400"""
    resp = client.post('/api/workflow-templates', headers=auth_header, json={
        'name': '禁用Agent模板',
        'agents': [{'agent_id': 'tmpl-agent-c', 'role': '分析', 'order': 1}],
    })
    assert resp.status_code == 400
    assert '无效或已禁用' in resp.json()['detail']['error']


# ==================== 列表 ====================

def test_list_templates(client, auth_header, system_template, user_template):
    """列表返回系统预设 + 用户自建"""
    resp = client.get('/api/workflow-templates', headers=auth_header)
    assert resp.status_code == 200
    data = resp.json()
    assert data['total'] >= 2
    names = [t['name'] for t in data['items']]
    assert '系统医疗模板' in names


def test_list_templates_filter_category(client, auth_header, system_template, user_template):
    """分类筛选"""
    resp = client.get('/api/workflow-templates?category=medical', headers=auth_header)
    assert resp.status_code == 200
    for item in resp.json()['items']:
        assert item['category'] == 'medical'


def test_list_templates_hide_other_users(client, auth_header, other_user_template):
    """不返回其他用户的模板"""
    resp = client.get('/api/workflow-templates', headers=auth_header)
    names = [t['name'] for t in resp.json()['items']]
    assert '别人的模板' not in names


@pytest.fixture
def fast_system_template(client, sample_agents_for_template):
    """创建快速模式系统模板"""
    from tests.conftest import TestSessionLocal
    session = TestSessionLocal()
    try:
        tmpl = WorkflowTemplate(
            name='快速医疗模板',
            description='快速模式',
            category='medical',
            is_system=True,
            creator_id=None,
            agents=[{'agent_id': 'tmpl-agent-a', 'role': '主导', 'order': 1}],
            skip_assessment=True,
            assessment_threshold=80,
        )
        session.add(tmpl)
        session.commit()
        session.refresh(tmpl)
        return tmpl.id
    finally:
        session.close()


def test_list_templates_filter_skip_assessment_true(client, auth_header, system_template, fast_system_template):
    """skip_assessment=true 只返回快速模式模板"""
    resp = client.get('/api/workflow-templates?skip_assessment=true&is_system=true', headers=auth_header)
    assert resp.status_code == 200
    items = resp.json()['items']
    assert len(items) >= 1
    for item in items:
        assert item['skip_assessment'] is True


def test_list_templates_filter_skip_assessment_false(client, auth_header, system_template, fast_system_template):
    """skip_assessment=false 只返回非快速模式模板"""
    resp = client.get('/api/workflow-templates?skip_assessment=false&is_system=true', headers=auth_header)
    assert resp.status_code == 200
    items = resp.json()['items']
    assert len(items) >= 1
    for item in items:
        assert item['skip_assessment'] is False


def test_list_templates_no_filter_returns_all(client, auth_header, system_template, fast_system_template):
    """不传 skip_assessment 返回全部"""
    resp = client.get('/api/workflow-templates?is_system=true', headers=auth_header)
    assert resp.status_code == 200
    items = resp.json()['items']
    skip_values = {item['skip_assessment'] for item in items}
    assert len(skip_values) >= 2  # 应包含 true 和 false


# ==================== 详情 ====================

def test_get_template(client, auth_header, user_template):
    """获取自建模板详情 → 200"""
    resp = client.get(f'/api/workflow-templates/{user_template}', headers=auth_header)
    assert resp.status_code == 200
    assert resp.json()['name'] == '我的模板'


def test_get_system_template(client, auth_header, system_template):
    """获取系统模板详情 → 200"""
    resp = client.get(f'/api/workflow-templates/{system_template}', headers=auth_header)
    assert resp.status_code == 200
    assert resp.json()['is_system'] is True


def test_get_other_user_template_404(client, auth_header, other_user_template):
    """获取他人模板 → 404"""
    resp = client.get(f'/api/workflow-templates/{other_user_template}', headers=auth_header)
    assert resp.status_code == 404


def test_get_nonexistent_template_404(client, auth_header):
    """模板不存在 → 404"""
    resp = client.get('/api/workflow-templates/99999', headers=auth_header)
    assert resp.status_code == 404


# ==================== 更新 ====================

def test_update_user_template(client, auth_header, user_template):
    """更新自建模板 → 200"""
    resp = client.put(f'/api/workflow-templates/{user_template}', headers=auth_header, json={
        'name': '改名后的模板',
        'assessment_threshold': 80,
    })
    assert resp.status_code == 200
    assert resp.json()['name'] == '改名后的模板'
    assert resp.json()['assessment_threshold'] == 80


def test_update_system_template_403(client, auth_header, system_template):
    """系统模板禁止修改 → 403"""
    resp = client.put(f'/api/workflow-templates/{system_template}', headers=auth_header, json={
        'name': '尝试改名',
    })
    assert resp.status_code == 403
    assert '不可修改' in resp.json()['detail']['error']


def test_update_other_user_template_403(client, auth_header, other_user_template):
    """他人模板禁止修改 → 403"""
    resp = client.put(f'/api/workflow-templates/{other_user_template}', headers=auth_header, json={
        'name': '尝试改名',
    })
    assert resp.status_code == 403


# ==================== 删除 ====================

def test_delete_user_template(client, auth_header, user_template):
    """删除自建模板 → 204"""
    resp = client.delete(f'/api/workflow-templates/{user_template}', headers=auth_header)
    assert resp.status_code == 204


def test_delete_system_template_403(client, auth_header, system_template):
    """系统模板禁止删除 → 403"""
    resp = client.delete(f'/api/workflow-templates/{system_template}', headers=auth_header)
    assert resp.status_code == 403
    assert '不可删除' in resp.json()['detail']['error']


def test_delete_other_user_template_403(client, auth_header, other_user_template):
    """他人模板禁止删除 → 403"""
    resp = client.delete(f'/api/workflow-templates/{other_user_template}', headers=auth_header)
    assert resp.status_code == 403


# ==================== apply ====================

def test_apply_template_skip_assessment(client, auth_header, user_template):
    """apply 快速模式模板 → SSE 流（至少不报 404/403/400）"""
    # 需要有效的 conversation_id
    from tests.conftest import TestSessionLocal
    from models import Conversation
    session = TestSessionLocal()
    try:
        user = session.query(User).filter_by(username='testuser').first()
        conv = Conversation(title='apply测试', user_id=user.id)
        session.add(conv)
        session.commit()
        session.refresh(conv)
        conv_id = conv.id
    finally:
        session.close()

    resp = client.post(f'/api/workflow-templates/{user_template}/apply', headers=auth_header, json={
        'conversation_id': conv_id,
        'message': '测试 apply',
    })
    # apply 会触发 LLM 调用：测试环境无真实 LLM 时返回 500
    # 期望 200（SSE 流）或 500（LLM 调用失败），但不应返回 404/403/400
    assert resp.status_code in (200, 500, 503), (
        f"预期 200（SSE 流）、500 或 503（LLM 不可用），实际 {resp.status_code}"
    )


def test_apply_template_sets_conversation_category_from_template(client, auth_header, fast_system_template):
    """快速模式团队方案应把方案分类写入仍为 other 的案例。"""
    from tests.conftest import TestSessionLocal
    from models import Conversation

    session = TestSessionLocal()
    try:
        user = session.query(User).filter_by(username='testuser').first()
        conv = Conversation(title='医疗方案分类测试', user_id=user.id)
        session.add(conv)
        session.commit()
        session.refresh(conv)
        conv_id = conv.id
    finally:
        session.close()

    resp = client.post(f'/api/workflow-templates/{fast_system_template}/apply', headers=auth_header, json={
        'conversation_id': conv_id,
        'message': '测试医疗快速方案',
    })
    assert resp.status_code in (200, 500, 503)

    session = TestSessionLocal()
    try:
        refreshed = session.get(Conversation, conv_id)
        assert refreshed.category == 'medical'
    finally:
        session.close()


def test_apply_template_uses_pack_category_when_template_category_custom(client, auth_header, sample_pack_for_template):
    """模板分类为 custom 时，应回退到引用的团队包分类。"""
    from tests.conftest import TestSessionLocal
    from models import Conversation, WorkflowTemplate

    session = TestSessionLocal()
    try:
        user = session.query(User).filter_by(username='testuser').first()
        tmpl = WorkflowTemplate(
            name='自定义分类但引用商业包',
            category='custom',
            is_system=False,
            creator_id=user.id,
            pack_id=sample_pack_for_template,
            skip_assessment=True,
        )
        conv = Conversation(title='商业包分类测试', user_id=user.id)
        session.add_all([tmpl, conv])
        session.commit()
        session.refresh(tmpl)
        session.refresh(conv)
        tmpl_id = tmpl.id
        conv_id = conv.id
    finally:
        session.close()

    resp = client.post(f'/api/workflow-templates/{tmpl_id}/apply', headers=auth_header, json={
        'conversation_id': conv_id,
        'message': '测试商业包快速方案',
    })
    assert resp.status_code in (200, 500, 503)

    session = TestSessionLocal()
    try:
        refreshed = session.get(Conversation, conv_id)
        assert refreshed.category == 'business'
    finally:
        session.close()


def test_apply_nonexistent_template_404(client, auth_header):
    """apply 不存在的模板 → 404"""
    resp = client.post('/api/workflow-templates/99999/apply', headers=auth_header, json={
        'conversation_id': 1,
        'message': 'test',
    })
    assert resp.status_code == 404


def test_apply_system_template(client, auth_header, system_template):
    """apply 系统模板 → 不报权限错误"""
    from tests.conftest import TestSessionLocal
    from models import Conversation
    session = TestSessionLocal()
    try:
        user = session.query(User).filter_by(username='testuser').first()
        conv = Conversation(title='apply系统测试', user_id=user.id)
        session.add(conv)
        session.commit()
        session.refresh(conv)
        conv_id = conv.id
    finally:
        session.close()

    resp = client.post(f'/api/workflow-templates/{system_template}/apply', headers=auth_header, json={
        'conversation_id': conv_id,
        'message': '测试系统模板 apply',
    })
    # apply 会触发 LLM 调用：测试环境无真实 LLM 时返回 500
    # 期望 200（SSE 流）或 500（LLM 不可用），但不应返回 404/403/400
    assert resp.status_code in (200, 500, 503), (
        f"预期 200（SSE 流）、500 或 503（LLM 不可用），实际 {resp.status_code}"
    )


# ==================== 更新 — 可空字段清空 ====================

def test_update_clear_description(client, auth_header, user_template):
    """将 description 设为 null → 应清空该字段"""
    # 先确认当前有 description
    resp = client.get(f'/api/workflow-templates/{user_template}', headers=auth_header)
    assert resp.status_code == 200

    # 发送 null 清空
    resp = client.put(f'/api/workflow-templates/{user_template}', headers=auth_header, json={
        'description': None,
    })
    assert resp.status_code == 200
    assert resp.json()['description'] is None


def test_update_clear_pack_id(client, auth_header, user_template):
    """将 pack_id 设为 null → 应清空该字段"""
    resp = client.put(f'/api/workflow-templates/{user_template}', headers=auth_header, json={
        'pack_id': None,
    })
    assert resp.status_code == 200
    assert resp.json()['pack_id'] is None


def test_update_clear_system_prompt_addition(client, auth_header):
    """先设置 system_prompt_addition，再清空为 null"""
    # 创建带 system_prompt_addition 的模板
    from tests.conftest import TestSessionLocal
    session = TestSessionLocal()
    try:
        user = session.query(User).filter_by(username='testuser').first()
        from models import WorkflowTemplate
        tmpl = WorkflowTemplate(
            name='带附加提示的模板',
            description='test',
            category='custom',
            is_system=False,
            creator_id=user.id,
            agents=[{'agent_id': 'tmpl-agent-a', 'role': '分析', 'order': 1}],
            system_prompt_addition='额外的系统提示',
        )
        session.add(tmpl)
        session.commit()
        session.refresh(tmpl)
        tmpl_id = tmpl.id
    finally:
        session.close()

    # 确认有值
    resp = client.get(f'/api/workflow-templates/{tmpl_id}', headers=auth_header)
    assert resp.status_code == 200
    assert resp.json()['system_prompt_addition'] == '额外的系统提示'

    # 清空
    resp = client.put(f'/api/workflow-templates/{tmpl_id}', headers=auth_header, json={
        'system_prompt_addition': None,
    })
    assert resp.status_code == 200
    assert resp.json()['system_prompt_addition'] is None
