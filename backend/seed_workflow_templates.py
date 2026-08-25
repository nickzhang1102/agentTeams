#!/usr/bin/env python3
"""种子数据脚本：初始化系统预设 WorkflowTemplate

幂等执行：按 catalog key 更新字段，不存在则新建。
前置依赖：seed_agent_packs.py（引用已有 AgentPack）。
"""
import os
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import SessionLocal
from models import WorkflowTemplate, AgentPack

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SYSTEM_TEMPLATES = [
    # ==================== medical（医疗专家）====================
    {
        "key": "quick-medical-diagnosis",
        "name": "快速医疗诊断",
        "description": "跳过评估，直接启动多学科医疗诊断团队，适合症状明确的快速分析",
        "category": "medical",
        "pack_key": "medical-diagnosis-team",
        "skip_assessment": True,
        "assessment_threshold": 80,
        "system_prompt_addition": None,
    },
    {
        "key": "quick-cardiovascular-evaluation",
        "name": "快速心血管评估",
        "description": "跳过评估，直接启动心血管评估团队，适合胸痛、心悸等明确心脏症状",
        "category": "medical",
        "pack_key": "cardiovascular-evaluation-team",
        "skip_assessment": True,
        "assessment_threshold": 80,
        "system_prompt_addition": None,
    },
    {
        "key": "standard-surgical-evaluation",
        "name": "标准外科评估",
        "description": "完整评估流程的外科手术团队，适合需要详细术前评估的复杂病例",
        "category": "medical",
        "pack_key": "surgical-evaluation-team",
        "skip_assessment": False,
        "assessment_threshold": 60,
        "system_prompt_addition": None,
    },
    {
        "key": "standard-oncology-mdt",
        "name": "标准肿瘤MDT",
        "description": "完整评估流程的肿瘤多学科会诊，适合复杂肿瘤病例的综合诊疗决策",
        "category": "medical",
        "pack_key": "oncology-mdt-team",
        "skip_assessment": False,
        "assessment_threshold": 60,
        "system_prompt_addition": None,
    },
    # ==================== business（商业角色）====================
    {
        "key": "quick-strategic-analysis",
        "name": "快速战略分析",
        "description": "跳过评估，直接启动战略分析团队，适合有明确分析方向的商业决策",
        "category": "business",
        "pack_key": "strategic-analysis-team",
        "skip_assessment": True,
        "assessment_threshold": 75,
        "system_prompt_addition": None,
    },
    {
        "key": "quick-marketing-growth",
        "name": "快速营销增长",
        "description": "跳过评估，直接启动营销增长团队，适合有明确 GTM 方向的营销决策",
        "category": "business",
        "pack_key": "marketing-growth-team",
        "skip_assessment": True,
        "assessment_threshold": 75,
        "system_prompt_addition": None,
    },
    {
        "key": "standard-product-development",
        "name": "标准产品研发",
        "description": "完整评估流程的产品研发团队，适合需要需求讨论的产品规划",
        "category": "business",
        "pack_key": "product-development-team",
        "skip_assessment": False,
        "assessment_threshold": 60,
        "system_prompt_addition": None,
    },
    {
        "key": "standard-ai-transformation",
        "name": "标准AI技术转型",
        "description": "完整评估流程的 AI 技术转型团队，适合企业级 AI 战略规划与落地",
        "category": "business",
        "pack_key": "ai-transformation-team",
        "skip_assessment": False,
        "assessment_threshold": 60,
        "system_prompt_addition": None,
    },
    # ==================== finance（期货公司）====================
    {
        "key": "quick-futures-investment-research",
        "name": "期货快速投资研究",
        "description": "跳过评估，直接启动期货投资研究团队，适合有明确标的或方向的投资分析",
        "category": "finance",
        "pack_key": "futures-investment-research-team",
        "skip_assessment": True,
        "assessment_threshold": 75,
        "system_prompt_addition": None,
    },
    {
        "key": "quick-futures-quant-strategy",
        "name": "期货快速量化策略",
        "description": "跳过评估，直接启动量化策略团队，适合有明确策略方向的量化开发",
        "category": "finance",
        "pack_key": "futures-quant-strategy-team",
        "skip_assessment": True,
        "assessment_threshold": 75,
        "system_prompt_addition": None,
    },
    {
        "key": "standard-futures-asset-allocation",
        "name": "期货标准大类资产配置",
        "description": "完整评估流程的大类资产配置团队，适合跨市场、跨品种的配置决策",
        "category": "finance",
        "pack_key": "futures-asset-allocation-team",
        "skip_assessment": False,
        "assessment_threshold": 60,
        "system_prompt_addition": None,
    },
    # ==================== securities（证券公司）====================
    {
        "key": "quick-securities-sector-rotation",
        "name": "证券快速行业轮动",
        "description": "跳过评估，直接启动行业轮动配置团队，适合有明确行业方向的配置决策",
        "category": "securities",
        "pack_key": "securities-sector-rotation-team",
        "skip_assessment": True,
        "assessment_threshold": 75,
        "system_prompt_addition": None,
    },
    {
        "key": "quick-securities-consumer-research",
        "name": "证券快速消费研究",
        "description": "跳过评估，直接启动消费行业研究团队，适合消费赛道的景气度分析",
        "category": "securities",
        "pack_key": "securities-consumer-research-team",
        "skip_assessment": True,
        "assessment_threshold": 75,
        "system_prompt_addition": None,
    },
    {
        "key": "standard-securities-fixed-income-research",
        "name": "证券标准固收研究",
        "description": "完整评估流程的固收研究团队，适合利率走势研判和信用风险分析",
        "category": "securities",
        "pack_key": "securities-fixed-income-research-team",
        "skip_assessment": False,
        "assessment_threshold": 60,
        "system_prompt_addition": None,
    },
    {
        "key": "standard-securities-new-energy-research",
        "name": "证券标准新能源研究",
        "description": "完整评估流程的新能源产业链团队，适合新能源全产业链的深度研究",
        "category": "securities",
        "pack_key": "securities-new-energy-chain-team",
        "skip_assessment": False,
        "assessment_threshold": 60,
        "system_prompt_addition": None,
    },
]


def seed_workflow_templates():
    """创建/更新系统预设 WorkflowTemplate（幂等 upsert）"""
    db = SessionLocal()
    try:
        created = 0
        updated = 0
        missing_packs = []

        for tpl_data in SYSTEM_TEMPLATES:
            existing = db.query(WorkflowTemplate).filter_by(
                catalog_key=tpl_data["key"],
                is_system=True,
            ).first()

            if not existing:
                existing = db.query(WorkflowTemplate).filter_by(
                    name=tpl_data["name"],
                    is_system=True,
                ).first()
                if existing:
                    logger.warning(
                        "按旧名称收编 WorkflowTemplate: name=%s key=%s",
                        tpl_data["name"],
                        tpl_data["key"],
                    )
                    existing.catalog_key = tpl_data["key"]

            # 查找引用的 AgentPack
            pack = db.query(AgentPack).filter_by(
                catalog_key=tpl_data["pack_key"],
                is_system=True,
            ).first()

            if not pack:
                missing_packs.append(tpl_data["pack_key"])
                logger.warning(f"AgentPack 不存在: {tpl_data['pack_key']}，跳过模板: {tpl_data['name']}")
                continue

            if existing:
                existing.name = tpl_data["name"]
                existing.description = tpl_data["description"]
                existing.category = tpl_data["category"]
                existing.pack_id = pack.id
                existing.skip_assessment = tpl_data["skip_assessment"]
                existing.assessment_threshold = tpl_data["assessment_threshold"]
                existing.system_prompt_addition = tpl_data["system_prompt_addition"]
                updated += 1
                logger.info(f"更新: {tpl_data['name']} (pack: {tpl_data['pack_key']})")
            else:
                template = WorkflowTemplate(
                    catalog_key=tpl_data["key"],
                    name=tpl_data["name"],
                    description=tpl_data["description"],
                    category=tpl_data["category"],
                    is_system=True,
                    creator_id=None,
                    pack_id=pack.id,
                    agents=None,
                    skip_assessment=tpl_data["skip_assessment"],
                    assessment_threshold=tpl_data["assessment_threshold"],
                    system_prompt_addition=tpl_data["system_prompt_addition"],
                )
                db.add(template)
                created += 1
                logger.info(f"创建: {tpl_data['name']} (pack: {tpl_data['pack_key']}, fast: {tpl_data['skip_assessment']})")

        db.commit()

        if missing_packs:
            logger.warning(f"缺失 AgentPack: {', '.join(missing_packs)}，请先运行 seed_agent_packs.py")

        logger.info(f"完成: 创建 {created}, 更新 {updated}")

    except Exception as e:
        db.rollback()
        logger.error(f"Seed 失败: {e}")
        raise
    finally:
        db.close()


if __name__ == '__main__':
    try:
        seed_workflow_templates()
    except Exception as e:
        logger.error(f"种子数据脚本异常，跳过: {e}")
