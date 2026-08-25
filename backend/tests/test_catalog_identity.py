from catalog.labels import CATALOG_TRANSLATIONS
from migrations.versions import a4b5c6d7e8f9_add_catalog_keys as migration
from models import AgentPack, WorkflowTemplate
from seed_agent_packs import SYSTEM_PACKS, seed_agent_packs
from seed_workflow_templates import SYSTEM_TEMPLATES, seed_workflow_templates


def test_seed_keys_match_catalog_resources():
    pack_keys = {item['key'] for item in SYSTEM_PACKS}
    template_keys = {item['key'] for item in SYSTEM_TEMPLATES}

    assert pack_keys == set(CATALOG_TRANSLATIONS['agent_pack'])
    assert template_keys == set(CATALOG_TRANSLATIONS['workflow_template'])
    assert all('pack_key' in item and 'pack_name' not in item for item in SYSTEM_TEMPLATES)


def test_seed_is_idempotent_and_relationships_use_catalog_keys(db_session, monkeypatch):
    from tests.conftest import TestSessionLocal
    import seed_agent_packs as pack_seed_module
    import seed_workflow_templates as template_seed_module

    monkeypatch.setattr(pack_seed_module, 'SessionLocal', TestSessionLocal)
    monkeypatch.setattr(template_seed_module, 'SessionLocal', TestSessionLocal)

    seed_agent_packs()
    seed_workflow_templates()
    seed_agent_packs()
    seed_workflow_templates()

    db_session.expire_all()
    assert db_session.query(AgentPack).count() == len(SYSTEM_PACKS)
    assert db_session.query(WorkflowTemplate).count() == len(SYSTEM_TEMPLATES)

    template = db_session.query(WorkflowTemplate).filter_by(
        catalog_key='quick-medical-diagnosis'
    ).one()
    assert template.pack.catalog_key == 'medical-diagnosis-team'

    pack = template.pack
    pack.name = '改名后的组合包'
    template.name = '改名后的模板'
    db_session.commit()

    seed_agent_packs()
    seed_workflow_templates()
    db_session.expire_all()

    assert db_session.query(AgentPack).count() == len(SYSTEM_PACKS)
    assert db_session.query(WorkflowTemplate).count() == len(SYSTEM_TEMPLATES)
    assert db_session.query(AgentPack).filter_by(
        catalog_key='medical-diagnosis-team'
    ).one().name == '医疗诊断团队'
    assert db_session.query(WorkflowTemplate).filter_by(
        catalog_key='quick-medical-diagnosis'
    ).one().name == '快速医疗诊断'


def test_custom_models_generate_distinct_catalog_keys(db_session):
    packs = [
        AgentPack(name='用户包 A', is_system=False, creator_id=None, agents=[]),
        AgentPack(name='用户包 B', is_system=False, creator_id=None, agents=[]),
    ]
    templates = [
        WorkflowTemplate(name='用户模板 A', is_system=False, creator_id=None),
        WorkflowTemplate(name='用户模板 B', is_system=False, creator_id=None),
    ]
    db_session.add_all([*packs, *templates])
    db_session.commit()

    assert all(pack.catalog_key.startswith('pack-') for pack in packs)
    assert all(template.catalog_key.startswith('template-') for template in templates)
    assert len({item.catalog_key for item in [*packs, *templates]}) == 4


def test_catalog_key_migration_backfills_before_constraints(monkeypatch):
    added = []
    constraints = []
    altered = []
    executions = []

    class RecordingSafeOperations:
        def __init__(self, operations):
            self.operations = operations

        def add_column(self, table_name, column):
            added.append((table_name, column.name, column.nullable))

        def create_unique_constraint(self, name, table_name, columns):
            constraints.append((name, table_name, columns))

    class RecordingConnection:
        def execute(self, statement, params=None):
            executions.append((str(statement), params))

    monkeypatch.setattr(migration, 'SafeOperations', RecordingSafeOperations)
    monkeypatch.setattr(migration.op, 'get_bind', lambda: RecordingConnection())
    monkeypatch.setattr(
        migration.op,
        'alter_column',
        lambda table_name, column_name, **kwargs: altered.append(
            (table_name, column_name, kwargs['nullable'])
        ),
    )

    migration.upgrade()

    assert added == [
        ('agent_packs', 'catalog_key', True),
        ('workflow_templates', 'catalog_key', True),
    ]
    assert len(executions) == len(migration.PACK_KEYS) + len(migration.TEMPLATE_KEYS) + 2
    assert altered == [
        ('agent_packs', 'catalog_key', False),
        ('workflow_templates', 'catalog_key', False),
    ]
    assert constraints == [
        ('uq_agent_pack_catalog_key', 'agent_packs', ['catalog_key']),
        (
            'uq_workflow_template_catalog_key',
            'workflow_templates',
            ['catalog_key'],
        ),
    ]
