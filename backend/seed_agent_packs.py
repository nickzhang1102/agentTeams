#!/usr/bin/env python3
"""种子数据脚本：初始化系统预设 AgentPack

幂等执行：按 catalog key 更新字段，不存在则新建。
"""
import os
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import SessionLocal
from models import AgentPack

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SYSTEM_PACKS = [
    # ==================== medical（医疗专家）====================
    {
        "key": "medical-diagnosis-team",
        "name": "医疗诊断团队",
        "description": "常见内科疾病的多学科诊断，涵盖全科初评、专科分析和辅助检查",
        "category": "medical",
        "agents": [
            {"agent_id": "general-practice-expert", "role": "初步评估与分诊", "order": 1},
            {"agent_id": "cardiology-expert", "role": "心血管系统评估", "order": 2},
            {"agent_id": "radiology-expert", "role": "影像学诊断", "order": 3},
            {"agent_id": "laboratory-expert", "role": "检验结果分析", "order": 4},
        ],
        "tags": ["diagnosis", "multi-discipline", "internal-medicine"],
    },
    {
        "key": "surgical-evaluation-team",
        "name": "外科手术评估团队",
        "description": "术前多学科评估，覆盖外科、影像、病理和术前检验",
        "category": "medical",
        "agents": [
            {"agent_id": "general-surgery-expert", "role": "外科评估", "order": 1},
            {"agent_id": "radiology-expert", "role": "术前影像", "order": 2},
            {"agent_id": "pathology-expert", "role": "病理分析", "order": 3},
            {"agent_id": "laboratory-expert", "role": "术前检验", "order": 4},
        ],
        "tags": ["surgery", "pre-operative", "assessment"],
    },
    {
        "key": "oncology-mdt-team",
        "name": "肿瘤MDT团队",
        "description": "肿瘤多学科会诊，覆盖内科化疗、放疗、外科手术、影像和病理",
        "category": "medical",
        "agents": [
            {"agent_id": "oncology-expert", "role": "肿瘤内科主导", "order": 1},
            {"agent_id": "radiotherapy-expert", "role": "放疗评估", "order": 2},
            {"agent_id": "general-surgery-expert", "role": "外科手术评估", "order": 3},
            {"agent_id": "radiology-expert", "role": "影像学评估", "order": 4},
            {"agent_id": "pathology-expert", "role": "病理诊断", "order": 5},
        ],
        "tags": ["oncology", "mdt", "multi-discipline"],
    },
    {
        "key": "cardiovascular-evaluation-team",
        "name": "心血管评估团队",
        "description": "心脏病全链路评估，涵盖内科诊断、外科决策、影像和检验",
        "category": "medical",
        "agents": [
            {"agent_id": "cardiology-expert", "role": "心内科评估", "order": 1},
            {"agent_id": "cardiac-surgery-expert", "role": "心外科评估", "order": 2},
            {"agent_id": "radiology-expert", "role": "心脏影像", "order": 3},
            {"agent_id": "laboratory-expert", "role": "心脏标志物", "order": 4},
        ],
        "tags": ["cardiology", "cardiac-surgery", "assessment"],
    },
    # ==================== business（商业角色）====================
    {
        "key": "strategic-analysis-team",
        "name": "战略分析团队",
        "description": "商业战略多角度分析，覆盖 CEO 视角、研究分析和逆向思考",
        "category": "business",
        "agents": [
            {"agent_id": "ceo-bezos", "role": "战略决策", "order": 1},
            {"agent_id": "research-thompson", "role": "市场研究", "order": 2},
            {"agent_id": "critic-munger", "role": "风险质疑", "order": 3},
            {"agent_id": "cfo-campbell", "role": "财务可行性", "order": 4},
        ],
        "tags": ["strategy", "analysis", "decision-making"],
    },
    {
        "key": "product-development-team",
        "name": "产品研发团队",
        "description": "从产品设计到技术实现到质量保障的全流程团队",
        "category": "business",
        "agents": [
            {"agent_id": "product-norman", "role": "产品设计", "order": 1},
            {"agent_id": "fullstack-dhh", "role": "技术实现", "order": 2},
            {"agent_id": "qa-bach", "role": "质量保障", "order": 3},
            {"agent_id": "cto-vogels", "role": "技术决策", "order": 4},
        ],
        "tags": ["product", "development", "engineering"],
    },
    {
        "key": "marketing-growth-team",
        "name": "营销增长团队",
        "description": "GTM 全链路，覆盖市场调研、增长策略、销售执行和品牌传播",
        "category": "business",
        "agents": [
            {"agent_id": "research-thompson", "role": "市场调研", "order": 1},
            {"agent_id": "marketing-godin", "role": "增长策略", "order": 2},
            {"agent_id": "sales-ross", "role": "销售执行", "order": 3},
            {"agent_id": "operations-pg", "role": "运营落地", "order": 4},
            {"agent_id": "ceo-bezos", "role": "战略把关", "order": 5},
        ],
        "tags": ["marketing", "growth", "gtm"],
    },
    {
        "key": "ai-transformation-team",
        "name": "AI技术转型团队",
        "description": "AI 战略规划与技术落地，从 AI 决策到架构到实现到质量保障",
        "category": "business",
        "agents": [
            {"agent_id": "caio-ai", "role": "AI 战略", "order": 1},
            {"agent_id": "cto-vogels", "role": "技术架构", "order": 2},
            {"agent_id": "fullstack-dhh", "role": "全栈实现", "order": 3},
            {"agent_id": "qa-bach", "role": "质量保障", "order": 4},
        ],
        "tags": ["ai", "transformation", "technology"],
    },
    # ==================== finance（期货公司）====================
    {
        "key": "futures-investment-research-team",
        "name": "期货投资研究团队",
        "description": "投资决策全流程：策略制定、风险评估、行业研究和量化辅助",
        "category": "finance",
        "agents": [
            {"agent_id": "cio-dalio", "role": "投资策略", "order": 1},
            {"agent_id": "cro-taleb", "role": "风险评估", "order": 2},
            {"agent_id": "macro-analyst", "role": "宏观研判", "order": 3},
            {"agent_id": "quant-simons", "role": "量化辅助", "order": 4},
        ],
        "tags": ["investment", "research", "risk-management"],
    },
    {
        "key": "futures-quant-strategy-team",
        "name": "期货量化策略团队",
        "description": "量化策略开发与执行，覆盖模型构建、风险控制和投资决策",
        "category": "finance",
        "agents": [
            {"agent_id": "quant-simons", "role": "量化模型", "order": 1},
            {"agent_id": "cio-dalio", "role": "投资决策", "order": 2},
            {"agent_id": "cro-taleb", "role": "风险控制", "order": 3},
            {"agent_id": "macro-analyst", "role": "宏观环境", "order": 4},
        ],
        "tags": ["quantitative", "strategy", "model"],
    },
    {
        "key": "futures-asset-allocation-team",
        "name": "期货大类资产配置团队",
        "description": "跨资产轮动配置，覆盖宏观研判、投资策略、量化分析和风险评估",
        "category": "finance",
        "agents": [
            {"agent_id": "macro-analyst", "role": "宏观研判", "order": 1},
            {"agent_id": "cio-dalio", "role": "配置策略", "order": 2},
            {"agent_id": "quant-simons", "role": "量化分析", "order": 3},
            {"agent_id": "cro-taleb", "role": "风险评估", "order": 4},
        ],
        "tags": ["asset-allocation", "macro", "cross-asset"],
    },
    # ==================== securities（证券公司）====================
    {
        "key": "securities-sector-rotation-team",
        "name": "证券行业轮动配置团队",
        "description": "行业比较与轮动策略，覆盖宏观策略、消费、科技、能源等核心赛道",
        "category": "securities",
        "agents": [
            {"agent_id": "chief-strategist", "role": "策略主导", "order": 1},
            {"agent_id": "chief-economist", "role": "宏观研判", "order": 2},
            {"agent_id": "food-beverage-analyst", "role": "消费赛道", "order": 3},
            {"agent_id": "electronics-analyst", "role": "科技赛道", "order": 4},
            {"agent_id": "oil-gas-analyst", "role": "能源赛道", "order": 5},
        ],
        "tags": ["sector-rotation", "allocation", "strategy"],
    },
    {
        "key": "securities-fixed-income-research-team",
        "name": "证券固收研究团队",
        "description": "固定收益研究，覆盖利率定价、宏观经济、银行信用和风险评估",
        "category": "securities",
        "agents": [
            {"agent_id": "fixed-income-strategist", "role": "利率定价", "order": 1},
            {"agent_id": "chief-economist", "role": "宏观研判", "order": 2},
            {"agent_id": "banking-analyst", "role": "信用分析", "order": 3},
            {"agent_id": "cro-taleb", "role": "风险评估", "order": 4},
        ],
        "tags": ["fixed-income", "rates", "credit"],
    },
    {
        "key": "securities-new-energy-chain-team",
        "name": "证券新能源产业链团队",
        "description": "新能源全产业链研究，覆盖电力设备、汽车、有色和 ESG",
        "category": "securities",
        "agents": [
            {"agent_id": "power-equipment-analyst", "role": "电力设备", "order": 1},
            {"agent_id": "auto-analyst", "role": "新能源汽车", "order": 2},
            {"agent_id": "nonferrous-metals-analyst", "role": "上游金属", "order": 3},
            {"agent_id": "esg-analyst", "role": "ESG 评估", "order": 4},
        ],
        "tags": ["new-energy", "supply-chain", "ev"],
    },
    {
        "key": "securities-consumer-research-team",
        "name": "证券消费行业研究团队",
        "description": "消费行业景气追踪，覆盖食品饮料、家电、零售和纺织服装",
        "category": "securities",
        "agents": [
            {"agent_id": "food-beverage-analyst", "role": "食品饮料", "order": 1},
            {"agent_id": "home-appliance-analyst", "role": "家电", "order": 2},
            {"agent_id": "retail-analyst", "role": "零售", "order": 3},
            {"agent_id": "textile-apparel-analyst", "role": "纺织服装", "order": 4},
        ],
        "tags": ["consumer", "sector", "cyclical"],
    },
]


def seed_agent_packs():
    """创建/更新系统预设 AgentPack（幂等 upsert）"""
    db = SessionLocal()
    try:
        created = 0
        updated = 0

        for pack_data in SYSTEM_PACKS:
            existing = db.query(AgentPack).filter_by(
                catalog_key=pack_data["key"],
                is_system=True,
            ).first()

            if not existing:
                existing = db.query(AgentPack).filter_by(
                    name=pack_data["name"],
                    is_system=True,
                ).first()
                if existing:
                    logger.warning(
                        "按旧名称收编 AgentPack: name=%s key=%s",
                        pack_data["name"],
                        pack_data["key"],
                    )
                    existing.catalog_key = pack_data["key"]

            if existing:
                existing.name = pack_data["name"]
                existing.description = pack_data["description"]
                existing.category = pack_data["category"]
                existing.agents = pack_data["agents"]
                existing.tags = pack_data["tags"]
                updated += 1
                logger.info(f"更新: {pack_data['name']}")
            else:
                pack = AgentPack(
                    catalog_key=pack_data["key"],
                    name=pack_data["name"],
                    description=pack_data["description"],
                    category=pack_data["category"],
                    is_system=True,
                    creator_id=None,
                    agents=pack_data["agents"],
                    tags=pack_data["tags"],
                )
                db.add(pack)
                created += 1
                logger.info(f"创建: {pack_data['name']}")

        db.commit()
        logger.info(f"完成: 创建 {created}, 更新 {updated}")

    except Exception as e:
        db.rollback()
        logger.error(f"Seed 失败: {e}")
        raise
    finally:
        db.close()


if __name__ == '__main__':
    try:
        seed_agent_packs()
    except Exception as e:
        logger.error(f"种子数据脚本异常，跳过: {e}")
