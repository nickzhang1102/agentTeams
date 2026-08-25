import pytest

from models import AgentConfig, AgentPack, User, WorkflowTemplate
from services.workflow_template_service import WorkflowTemplateService


@pytest.fixture
def localized_pack_templates(client, auth_header):
    from tests.conftest import TestSessionLocal

    session = TestSessionLocal()
    try:
        user = session.query(User).filter_by(username='testuser').one()
        session.add_all([
            AgentConfig(
                agent_id='cardiology-expert',
                name='心血管内科专家',
                is_enabled=True,
                is_system=True,
            ),
            AgentConfig(
                agent_id='my-template-agent',
                name='我的模板 Agent',
                is_enabled=True,
                is_system=False,
                created_by=user.id,
            ),
        ])
        session.flush()

        system_pack = AgentPack(
            catalog_key='medical-diagnosis-team',
            name='医疗诊断团队',
            is_system=True,
            agents=[{'agent_id': 'cardiology-expert', 'role': '诊断', 'order': 1}],
        )
        custom_pack = AgentPack(
            name='我的中文组合包',
            is_system=False,
            creator_id=user.id,
            agents=[{'agent_id': 'my-template-agent', 'role': '分析', 'order': 1}],
        )
        session.add_all([system_pack, custom_pack])
        session.flush()

        system_template = WorkflowTemplate(
            catalog_key='quick-medical-diagnosis',
            name='快速医疗诊断',
            is_system=True,
            pack_id=system_pack.id,
            skip_assessment=True,
        )
        custom_template = WorkflowTemplate(
            name='我的中文模板',
            is_system=False,
            creator_id=user.id,
            agents=[{'agent_id': 'my-template-agent', 'role': '分析', 'order': 1}],
        )
        session.add_all([system_template, custom_template])
        session.commit()
        return {
            'system_pack_id': system_pack.id,
            'custom_pack_id': custom_pack.id,
            'system_template_id': system_template.id,
            'custom_template_id': custom_template.id,
        }
    finally:
        session.close()


def test_pack_reads_localize_system_and_preserve_custom(
    client, auth_header, localized_pack_templates
):
    response = client.get('/api/agent-packs?locale=en-US', headers=auth_header)
    assert response.status_code == 200
    items = {item['id']: item for item in response.json()['items']}

    system = items[localized_pack_templates['system_pack_id']]
    assert system['key'] == 'medical-diagnosis-team'
    assert system['name'] == '医疗诊断团队'
    assert system['label'] == 'Medical Diagnosis Team'
    assert system['fallback_locale'] == 'zh-CN'

    custom = items[localized_pack_templates['custom_pack_id']]
    assert custom['key'].startswith('pack-')
    assert custom['label'] == custom['name'] == '我的中文组合包'


def test_template_and_resolved_agents_use_same_locale_snapshot(
    client, auth_header, localized_pack_templates
):
    response = client.get(
        f"/api/workflow-templates/{localized_pack_templates['system_template_id']}"
        '?locale=en-US',
        headers=auth_header,
    )
    assert response.status_code == 200
    template = response.json()

    assert template['key'] == 'quick-medical-diagnosis'
    assert template['name'] == '快速医疗诊断'
    assert template['label'] == 'Quick Medical Diagnosis'
    assert template['pack_id'] == localized_pack_templates['system_pack_id']
    assert template['resolved_agents'][0] == {
        'agent_id': 'cardiology-expert',
        'role': '诊断',
        'order': 1,
        'name': '心血管内科专家',
        'key': 'cardiology-expert',
        'label': 'Cardiology Specialist',
        'fallback_locale': 'zh-CN',
    }


def test_custom_template_and_nested_agent_names_remain_unchanged(
    client, auth_header, localized_pack_templates
):
    template_id = localized_pack_templates['custom_template_id']
    english = client.get(
        f'/api/workflow-templates/{template_id}?locale=en-US', headers=auth_header
    ).json()
    chinese = client.get(
        f'/api/workflow-templates/{template_id}?locale=zh-CN', headers=auth_header
    ).json()

    assert english['key'] == chinese['key']
    assert english['label'] == chinese['label'] == '我的中文模板'
    assert english['resolved_agents'][0]['label'] == '我的模板 Agent'
    assert chinese['resolved_agents'][0]['label'] == '我的模板 Agent'


def test_pack_and_template_reject_invalid_explicit_locale(
    client, auth_header, localized_pack_templates
):
    for path in ('/api/agent-packs', '/api/workflow-templates'):
        response = client.get(path, headers=auth_header, params={'locale': 'fr-FR'})
        assert response.status_code == 400
        assert response.json()['detail']['code'] == 'UNSUPPORTED_LOCALE'


def test_template_apply_inputs_stay_numeric_ids_and_agent_ids(
    localized_pack_templates
):
    from tests.conftest import TestSessionLocal

    session = TestSessionLocal()
    try:
        template = session.get(
            WorkflowTemplate, localized_pack_templates['system_template_id']
        )
        service = WorkflowTemplateService(session)

        assert isinstance(template.id, int)
        assert isinstance(template.pack_id, int)
        assert service.resolve_agent_ids(template) == ['cardiology-expert']
    finally:
        session.close()
