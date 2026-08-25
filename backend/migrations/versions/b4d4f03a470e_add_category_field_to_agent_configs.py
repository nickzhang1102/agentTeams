"""add_category_field_to_agent_configs

Revision ID: b4d4f03a470e
Revises: 84d2e0baf569
Create Date: 2026-06-22 14:24:57.304726

"""
from alembic import op
import sqlalchemy as sa

from migrations.safe_ops import SafeOperations

# 内联权威映射表，避免迁移脚本依赖 service 层（service 重构后迁移不应 break）
AGENT_CATEGORY_MAP = {
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
    'critic-munger': 'business',
    # finance
    'cro-taleb': 'finance', 'cio-dalio': 'finance',
    'discipline-supervisor': 'finance', 'compliance-gensler': 'finance',
    'wealth-morgan': 'finance', 'branch-manager': 'finance',
    'research-manager': 'finance', 'asset-management': 'finance',
    'quant-simons': 'finance', 'international-leung': 'finance',
    'digital-banking': 'finance', 'fund-operations': 'finance',
    'risk-subsidiary-manager': 'finance',
}

# revision identifiers, used by Alembic.
revision = 'b4d4f03a470e'
down_revision = '84d2e0baf569'
branch_labels = None
depends_on = None


def upgrade():
    safe_op = SafeOperations(op)
    # 1. 新增 category 列
    safe_op.add_column('agent_configs', sa.Column('category', sa.String(length=50), nullable=True))
    safe_op.create_index(op.f('ix_agent_configs_category'), 'agent_configs', ['category'], unique=False)

    # 2. 批量回填系统 Agent 的 category（CASE WHEN 单条语句，避免循环 UPDATE）
    conn = op.get_bind()
    if not AGENT_CATEGORY_MAP:
        return

    # 构建 CASE WHEN 表达式
    cases = " ".join(
        f"WHEN agent_id = :aid_{i} THEN :cat_{i}"
        for i in range(len(AGENT_CATEGORY_MAP))
    )
    params = {}
    aid_conditions = []
    for i, (agent_id, category) in enumerate(AGENT_CATEGORY_MAP.items()):
        params[f"aid_{i}"] = agent_id
        params[f"cat_{i}"] = category
        aid_conditions.append(f":aid_{i}")

    aid_list = ", ".join(aid_conditions)
    sql = sa.text(
        f"UPDATE agent_configs SET category = CASE {cases} END "
        f"WHERE agent_id IN ({aid_list}) AND is_system = true"
    )
    conn.execute(sql, params)


def downgrade():
    op.drop_index(op.f('ix_agent_configs_category'), table_name='agent_configs')
    op.drop_column('agent_configs', 'category')
