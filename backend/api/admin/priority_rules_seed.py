"""优先级规则 Seed 数据

默认 Agent 优先级规则配置，供 seed_priority_rules 端点使用。
从 admin_api.py 路由中解耦，便于测试 fixture 和 CLI 工具复用。
"""

from typing import Any, Dict, List, Optional


DEFAULT_PRIORITY_RULES: List[Dict[str, Any]] = [
    # 高风险技术场景 → critic-munger 后置审核
    {
        'trigger_scene': 'technology',
        'trigger_risk_level': 'high',
        'trigger_category': None,
        'agent_id': 'critic-munger',
        'priority': 90,
        'rule_priority': 10,
        'description': '高风险技术场景：逆向思考顾问最后执行审核'
    },
    # 医疗肿瘤场景 → 检验科前置
    {
        'trigger_scene': 'medical',
        'trigger_risk_level': None,
        'trigger_category': '肿瘤',
        'agent_id': '检验科专家',
        'priority': 40,
        'rule_priority': 5,
        'description': '肿瘤场景：检验科专家先执行提供基础数据'
    },
    # 医疗肿瘤场景 → 放射科次前置
    {
        'trigger_scene': 'medical',
        'trigger_risk_level': None,
        'trigger_category': '肿瘤',
        'agent_id': '放射科专家',
        'priority': 45,
        'rule_priority': 5,
        'description': '肿瘤场景：放射科专家次执行提供影像依据'
    },
    # 医疗心血管场景 → 检验科前置
    {
        'trigger_scene': 'medical',
        'trigger_risk_level': None,
        'trigger_category': '心血管',
        'agent_id': '检验科专家',
        'priority': 40,
        'rule_priority': 5,
        'description': '心血管场景：检验科专家先执行'
    },
    # 高风险商业场景 → critic-munger 后置
    {
        'trigger_scene': 'business',
        'trigger_risk_level': 'high',
        'trigger_category': None,
        'agent_id': 'critic-munger',
        'priority': 90,
        'rule_priority': 10,
        'description': '高风险商业场景：逆向思考顾问最后执行审核'
    },
]
