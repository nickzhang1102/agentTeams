import pytest

from models import AgentConfig, User
from utils.locale_utils import resolve_locale


@pytest.fixture
def localized_agents(client, auth_header):
    from tests.conftest import TestSessionLocal

    session = TestSessionLocal()
    try:
        user = session.query(User).filter_by(username='testuser').one()
        session.add_all([
            AgentConfig(
                agent_id='cardiology-expert',
                name='心血管内科专家',
                description='系统内置',
                category='medical',
                is_system=True,
                is_enabled=True,
                file_exists=True,
            ),
            AgentConfig(
                agent_id='my-catalog-agent',
                name='我的目录 Agent',
                description='用户自建',
                category='custom',
                is_system=False,
                is_enabled=False,
                created_by=user.id,
                file_exists=True,
            ),
        ])
        session.commit()
    finally:
        session.close()


def test_resolve_locale_uses_contract_precedence():
    assert resolve_locale('en-US', 'zh-CN', 'zh-CN') == 'en-US'
    assert resolve_locale(None, 'en-US', 'zh-CN') == 'en-US'
    assert resolve_locale(None, None, 'en-GB,en;q=0.8') == 'en-US'
    assert resolve_locale(None, None, 'fr-FR') == 'zh-CN'

    with pytest.raises(ValueError, match='UNSUPPORTED_LOCALE'):
        resolve_locale('', 'en-US', 'en-US')


def test_agent_reads_localize_system_but_preserve_custom_name(
    client, auth_header, localized_agents
):
    response = client.get('/api/user/agents?locale=en-US', headers=auth_header)
    assert response.status_code == 200
    agents = {item['agent_id']: item for item in response.json()['agents']}

    system = agents['cardiology-expert']
    assert system['key'] == 'cardiology-expert'
    assert system['name'] == '心血管内科专家'
    assert system['label'] == 'Cardiology Specialist'
    assert system['fallback_locale'] == 'zh-CN'
    assert 'labels' not in system

    custom = agents['my-catalog-agent']
    assert custom['key'] == 'my-catalog-agent'
    assert custom['label'] == custom['name'] == '我的目录 Agent'

    chinese = client.get(
        '/api/user/agents/cardiology-expert?locale=zh-CN', headers=auth_header
    ).json()['agent']
    assert chinese['key'] == system['key']
    assert chinese['label'] == '心血管内科专家'
    assert chinese['category'] == system['category']


def test_explicit_locale_overrides_preference_and_invalid_values_fail(
    client, auth_header, localized_agents
):
    from tests.conftest import TestSessionLocal

    session = TestSessionLocal()
    try:
        user = session.query(User).filter_by(username='testuser').one()
        user.preferred_locale = 'zh-CN'
        session.commit()
    finally:
        session.close()

    english = client.get(
        '/api/agents/cardiology-expert?locale=en-US',
        headers={**auth_header, 'Accept-Language': 'zh-CN'},
    )
    assert english.status_code == 200
    assert english.json()['label'] == 'Cardiology Specialist'

    for value in ('fr-FR', ''):
        response = client.get(
            '/api/agents/categories', headers=auth_header, params={'locale': value}
        )
        assert response.status_code == 400
        assert response.json() == {
            'detail': {'code': 'UNSUPPORTED_LOCALE', 'error': '不支持的语言'}
        }


def test_categories_and_tree_share_locale_snapshot(client, auth_header, localized_agents):
    categories = client.get(
        '/api/agents/categories?locale=en-US', headers=auth_header
    ).json()['categories']
    by_key = {item['key']: item for item in categories}
    assert by_key['all']['label'] == 'All'
    assert by_key['medical']['label'] == 'Medical Specialists'
    assert by_key['medical']['name'] == '医疗专家'

    tree = client.get('/api/agents/tree?locale=en-US', headers=auth_header).json()
    assert tree['tree']['medical']['label'] == 'Medical Specialists'
    agent = next(
        item for item in tree['agents'] if item['id'] == 'cardiology-expert'
    )
    assert agent['label'] == 'Cardiology Specialist'


def test_admin_reads_include_labels_and_english_search(
    client, admin_auth_header, localized_agents
):
    detail = client.get(
        '/api/admin/agents/cardiology-expert?locale=en-US',
        headers=admin_auth_header,
    )
    assert detail.status_code == 200
    agent = detail.json()['agent']
    assert agent['label'] == 'Cardiology Specialist'
    assert agent['labels'] == {
        'zh-CN': '心血管内科专家',
        'en-US': 'Cardiology Specialist',
    }

    search = client.get(
        '/api/admin/agents',
        headers=admin_auth_header,
        params={'locale': 'en-US', 'search': 'Cardiology Specialist'},
    )
    assert search.status_code == 200
    assert [item['agent_id'] for item in search.json()['agents']] == [
        'cardiology-expert'
    ]


def test_file_fallback_uses_stable_key_and_resolved_label(
    client, auth_header, tmp_path, monkeypatch
):
    from config import Config

    (tmp_path / 'cardiology-expert.md').write_text(
        '---\nname: 心血管内科专家\ndescription: 系统内置\nmodel: inherit\n---\n',
        encoding='utf-8',
    )
    monkeypatch.setattr(Config, 'AGENTS_DIR', str(tmp_path))

    response = client.get(
        '/api/agents/cardiology-expert?locale=en-US', headers=auth_header
    )
    assert response.status_code == 200
    assert response.json() == {
        'id': 'cardiology-expert',
        'agent_id': 'cardiology-expert',
        'name': '心血管内科专家',
        'description': '系统内置',
        'model': 'inherit',
        'is_system': True,
        'key': 'cardiology-expert',
        'label': 'Cardiology Specialist',
        'fallback_locale': 'zh-CN',
    }
