"""Source-controlled translations for product-owned catalog labels.

The fallback zh-CN label remains the entity's source ``name``. This resource
only contains non-fallback translations keyed by stable catalog identity.
"""
from typing import Final


_AGENT_KEYS: Final[tuple[str, ...]] = tuple(
    """
    acupuncture-expert agribusiness-analyst agriculture-analyst allergy-expert
    asset-allocation-analyst asset-management auto-analyst banking-analyst
    basic-chemicals-analyst black-analyst breast-surgery-expert caio-ai
    cardiac-surgery-expert cardiology-expert ceo-bezos cfo-campbell
    chemical-analyst chief-economist chief-strategist cio-dalio coal-analyst
    computer-analyst construction-materials-analyst critic-munger cro-taleb
    cto-vogels defense-analyst dentist-expert derivatives-analyst
    dermatology-expert devops-hightower editor electronics-analyst
    endocrinology-expert ent-expert esg-analyst fin-engineer-analyst
    financial-analyst fixed-income-strategist food-beverage-analyst
    fullstack-dhh gastroenterology-expert gastrointestinal-surgery-expert
    general-practice-expert general-surgery-expert geriatrics-expert
    gynecology-expert hematology-expert hepatobiliary-surgery-expert
    home-appliance-analyst infectious-disease-expert interaction-cooper
    laboratory-expert light-industry-analyst machinery-analyst macro-analyst
    market-analyst marketing-godin media-analyst metals-analyst
    nephrology-expert neurology-expert neurosurgery-expert
    nonbank-finance-analyst nonferrous-metals-analyst nursing-expert
    nutrition-expert obstetrics-expert oil-gas-analyst oncology-expert
    operations-pg ophthalmology-expert orthopedics-expert
    pain-management-expert pathology-expert pediatrics-expert
    pharma-biotech-analyst plastic-surgery-expert power-equipment-analyst
    product-norman psychiatry-expert qa-bach quant-simons radiology-expert
    radiotherapy-expert real-estate-analyst rehabilitation-expert
    reproductive-medicine-expert research-thompson respirology-expert
    retail-analyst rheumatology-expert sales-ross social-service-analyst
    steel-analyst tcm-expert telecom-analyst textile-apparel-analyst
    thematic-analyst thoracic-surgery-expert thyroid-surgery-expert
    transplant-surgery-expert transport-analyst tuina-expert ui-duarte
    urology-expert utilities-analyst
    """.split()
)

_TOKEN_LABELS: Final[dict[str, str]] = {
    'ai': 'AI',
    'analyst': 'Analyst',
    'ceo': 'CEO',
    'cfo': 'CFO',
    'cio': 'CIO',
    'cro': 'CRO',
    'cto': 'CTO',
    'devops': 'DevOps',
    'ent': 'ENT',
    'esg': 'ESG',
    'expert': 'Specialist',
    'fin': 'Financial',
    'fullstack': 'Full-Stack',
    'mdt': 'MDT',
    'qa': 'QA',
    'tcm': 'Traditional Chinese Medicine',
    'ui': 'UI',
}

_AGENT_OVERRIDES: Final[dict[str, str]] = {
    'agriculture-analyst': 'Agricultural Commodities Analyst',
    'allergy-expert': 'Allergy and Immunology Specialist',
    'asset-management': 'Asset Management Director',
    'black-analyst': 'Ferrous Commodities Analyst',
    'caio-ai': 'Chief AI Officer',
    'ceo-bezos': 'Chief Executive Officer',
    'cfo-campbell': 'Chief Financial Officer',
    'chemical-analyst': 'Chemicals Analyst',
    'cio-dalio': 'Chief Investment Officer',
    'critic-munger': 'Contrarian Strategy Advisor',
    'cro-taleb': 'Chief Risk Officer',
    'cto-vogels': 'Chief Technology Officer',
    'devops-hightower': 'DevOps Director',
    'editor': 'Senior Editor',
    'ent-expert': 'ENT Specialist',
    'fin-engineer-analyst': 'Financial Engineering Analyst',
    'fixed-income-strategist': 'Chief Fixed Income Analyst',
    'fullstack-dhh': 'Full-Stack Engineering Lead',
    'general-practice-expert': 'General Practice Specialist',
    'interaction-cooper': 'Interaction Design Director',
    'laboratory-expert': 'Laboratory Medicine Specialist',
    'marketing-godin': 'Marketing Director',
    'metals-analyst': 'Nonferrous Metals Commodities Analyst',
    'nonbank-finance-analyst': 'Non-bank Financial Services Analyst',
    'nonferrous-metals-analyst': 'Nonferrous Metals Securities Analyst',
    'oncology-expert': 'Medical Oncology Specialist',
    'operations-pg': 'Operations Director',
    'product-norman': 'Product Design Director',
    'qa-bach': 'Quality Assurance Director',
    'quant-simons': 'Senior Quantitative Analyst',
    'radiotherapy-expert': 'Radiation Oncology Specialist',
    'research-thompson': 'Research Analyst',
    'respirology-expert': 'Pulmonology Specialist',
    'sales-ross': 'Sales Director',
    'ui-duarte': 'UI Design Director',
}


def _label_from_key(key: str) -> str:
    return ' '.join(_TOKEN_LABELS.get(token, token.capitalize()) for token in key.split('-'))


_AGENT_TRANSLATIONS: Final[dict[str, dict[str, str]]] = {
    key: {'en-US': _AGENT_OVERRIDES.get(key, _label_from_key(key))}
    for key in _AGENT_KEYS
}

CATALOG_TRANSLATIONS: Final[dict[str, dict[str, dict[str, str]]]] = {
    'agent': _AGENT_TRANSLATIONS,
    'agent_category': {
        'all': {'en-US': 'All'},
        '_uncategorized': {'en-US': 'Uncategorized'},
        'medical': {'en-US': 'Medical Specialists'},
        'business': {'en-US': 'Business Roles'},
        'finance': {'en-US': 'Futures Research'},
        'securities': {'en-US': 'Securities Research'},
    },
    'agent_pack': {
        'medical-diagnosis-team': {'en-US': 'Medical Diagnosis Team'},
        'surgical-evaluation-team': {'en-US': 'Surgical Evaluation Team'},
        'oncology-mdt-team': {'en-US': 'Oncology MDT Team'},
        'cardiovascular-evaluation-team': {'en-US': 'Cardiovascular Evaluation Team'},
        'strategic-analysis-team': {'en-US': 'Strategic Analysis Team'},
        'product-development-team': {'en-US': 'Product Development Team'},
        'marketing-growth-team': {'en-US': 'Marketing Growth Team'},
        'ai-transformation-team': {'en-US': 'AI Transformation Team'},
        'futures-investment-research-team': {'en-US': 'Futures Investment Research Team'},
        'futures-quant-strategy-team': {'en-US': 'Futures Quant Strategy Team'},
        'futures-asset-allocation-team': {'en-US': 'Futures Asset Allocation Team'},
        'securities-sector-rotation-team': {'en-US': 'Securities Sector Rotation Team'},
        'securities-fixed-income-research-team': {'en-US': 'Securities Fixed Income Research Team'},
        'securities-new-energy-chain-team': {'en-US': 'Securities New Energy Value Chain Team'},
        'securities-consumer-research-team': {'en-US': 'Securities Consumer Research Team'},
    },
    'workflow_template': {
        'quick-medical-diagnosis': {'en-US': 'Quick Medical Diagnosis'},
        'quick-cardiovascular-evaluation': {'en-US': 'Quick Cardiovascular Evaluation'},
        'standard-surgical-evaluation': {'en-US': 'Standard Surgical Evaluation'},
        'standard-oncology-mdt': {'en-US': 'Standard Oncology MDT'},
        'quick-strategic-analysis': {'en-US': 'Quick Strategic Analysis'},
        'quick-marketing-growth': {'en-US': 'Quick Marketing Growth'},
        'standard-product-development': {'en-US': 'Standard Product Development'},
        'standard-ai-transformation': {'en-US': 'Standard AI Transformation'},
        'quick-futures-investment-research': {'en-US': 'Quick Futures Investment Research'},
        'quick-futures-quant-strategy': {'en-US': 'Quick Futures Quant Strategy'},
        'standard-futures-asset-allocation': {'en-US': 'Standard Futures Asset Allocation'},
        'quick-securities-sector-rotation': {'en-US': 'Quick Securities Sector Rotation'},
        'quick-securities-consumer-research': {'en-US': 'Quick Securities Consumer Research'},
        'standard-securities-fixed-income-research': {'en-US': 'Standard Securities Fixed Income Research'},
        'standard-securities-new-energy-research': {'en-US': 'Standard Securities New Energy Research'},
    },
    'knowledge_category': {
        'default': {'en-US': 'Uncategorized'},
        'regulation': {'en-US': 'Policies'},
        'workflow': {'en-US': 'Workflows'},
        'contract': {'en-US': 'Contracts'},
        'news': {'en-US': 'News'},
    },
}
