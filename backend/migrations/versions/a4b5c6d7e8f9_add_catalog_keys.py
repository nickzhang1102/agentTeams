"""add stable catalog keys to packs and workflow templates

Revision ID: a4b5c6d7e8f9
Revises: f3a4b5c6d7e8
Create Date: 2026-07-29 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

from migrations.safe_ops import SafeOperations


revision = 'a4b5c6d7e8f9'
down_revision = 'f3a4b5c6d7e8'
branch_labels = None
depends_on = None


PACK_KEYS = {
    '医疗诊断团队': 'medical-diagnosis-team',
    '外科手术评估团队': 'surgical-evaluation-team',
    '肿瘤MDT团队': 'oncology-mdt-team',
    '心血管评估团队': 'cardiovascular-evaluation-team',
    '战略分析团队': 'strategic-analysis-team',
    '产品研发团队': 'product-development-team',
    '营销增长团队': 'marketing-growth-team',
    'AI技术转型团队': 'ai-transformation-team',
    '期货投资研究团队': 'futures-investment-research-team',
    '期货量化策略团队': 'futures-quant-strategy-team',
    '期货大类资产配置团队': 'futures-asset-allocation-team',
    '证券行业轮动配置团队': 'securities-sector-rotation-team',
    '证券固收研究团队': 'securities-fixed-income-research-team',
    '证券新能源产业链团队': 'securities-new-energy-chain-team',
    '证券消费行业研究团队': 'securities-consumer-research-team',
}

TEMPLATE_KEYS = {
    '快速医疗诊断': 'quick-medical-diagnosis',
    '快速心血管评估': 'quick-cardiovascular-evaluation',
    '标准外科评估': 'standard-surgical-evaluation',
    '标准肿瘤MDT': 'standard-oncology-mdt',
    '快速战略分析': 'quick-strategic-analysis',
    '快速营销增长': 'quick-marketing-growth',
    '标准产品研发': 'standard-product-development',
    '标准AI技术转型': 'standard-ai-transformation',
    '期货快速投资研究': 'quick-futures-investment-research',
    '期货快速量化策略': 'quick-futures-quant-strategy',
    '期货标准大类资产配置': 'standard-futures-asset-allocation',
    '证券快速行业轮动': 'quick-securities-sector-rotation',
    '证券快速消费研究': 'quick-securities-consumer-research',
    '证券标准固收研究': 'standard-securities-fixed-income-research',
    '证券标准新能源研究': 'standard-securities-new-energy-research',
}


def _backfill_known_keys(connection, table_name: str, key_map: dict[str, str]) -> None:
    statement = sa.text(
        f'UPDATE {table_name} SET catalog_key = :catalog_key '
        'WHERE catalog_key IS NULL AND is_system = true AND name = :name'
    )
    for name, catalog_key in key_map.items():
        connection.execute(statement, {'name': name, 'catalog_key': catalog_key})


def upgrade():
    safe = SafeOperations(op)
    safe.add_column('agent_packs', sa.Column('catalog_key', sa.String(length=100), nullable=True))
    safe.add_column(
        'workflow_templates',
        sa.Column('catalog_key', sa.String(length=100), nullable=True),
    )

    connection = op.get_bind()
    _backfill_known_keys(connection, 'agent_packs', PACK_KEYS)
    _backfill_known_keys(connection, 'workflow_templates', TEMPLATE_KEYS)
    connection.execute(sa.text(
        "UPDATE agent_packs SET catalog_key = 'pack-legacy-' || id "
        "WHERE catalog_key IS NULL"
    ))
    connection.execute(sa.text(
        "UPDATE workflow_templates SET catalog_key = 'template-legacy-' || id "
        "WHERE catalog_key IS NULL"
    ))

    op.alter_column('agent_packs', 'catalog_key', existing_type=sa.String(length=100), nullable=False)
    op.alter_column(
        'workflow_templates',
        'catalog_key',
        existing_type=sa.String(length=100),
        nullable=False,
    )
    safe.create_unique_constraint(
        'uq_agent_pack_catalog_key', 'agent_packs', ['catalog_key']
    )
    safe.create_unique_constraint(
        'uq_workflow_template_catalog_key', 'workflow_templates', ['catalog_key']
    )


def downgrade():
    op.drop_constraint(
        'uq_workflow_template_catalog_key', 'workflow_templates', type_='unique'
    )
    op.drop_constraint('uq_agent_pack_catalog_key', 'agent_packs', type_='unique')
    op.drop_column('workflow_templates', 'catalog_key')
    op.drop_column('agent_packs', 'catalog_key')
