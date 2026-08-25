"""
需求评估模块

负责分析用户需求的完整性和可行性
"""
import json
import logging
import re
from typing import Dict, List, Optional, Generator

from utils.async_utils import safe_async_run
from utils.locale_utils import SupportedLocale
from schemas.leader import AssessmentResult, normalize_category_key
try:
    from .locale_generation import build_output_locale_instruction, resolve_generation_locale
except ImportError:  # 保持旧测试通过 importlib 直接加载本模块的兼容性
    from leader.locale_generation import build_output_locale_instruction, resolve_generation_locale

logger = logging.getLogger(__name__)

# Assessment scoring constants
ASSESSMENT_SCORE_LOW = 30
ASSESSMENT_SCORE_HIGH = 85
ASSESSMENT_CHAR_THRESHOLD = 20

_MEDICAL_FALLBACK_KEYWORDS = frozenset({
    '患者', '病人', '症状', '病史', '诊断', '治疗', '用药', '药物', '手术',
    '病理', '检查结果', '化验', '医学影像', '肿瘤', '癌', '转移', '复发', '分期',
    '化疗', '放疗', '靶向', '免疫治疗', '基因检测', '住院', '疼痛', '发热',
    'patient', 'diagnosis', 'treatment', 'cancer', 'tumor', 'metastasis',
})

_ENGLISH_ASSESSMENT_FIELD_RULE = """## Mandatory English output rule
Write every user-visible JSON string value in English (en-US), even when the rubric, examples,
conversation history, user input, or immutable score keys below contain Chinese text.
The only Chinese text allowed in the JSON output is an exact `scores` object key defined by
`SCENE_SCORE_LIMITS`. Do not translate those machine-contract keys.
The values of `analysis`, `risk_reason`, `category_reason`, every `questions[].question`, and every
item in `questions[].options[]` must be English. Keep `scene`, `category`, `risk_level`, and
`questions[].selection_type` as the specified machine enum values.
"""


def simple_assessment_fallback(message: str, locale: SupportedLocale = "zh-CN") -> Dict:
    """语言无关的确定性降级评估；医疗场景在模型失败时保持关闭。"""
    locale = resolve_generation_locale(explicit_locale=locale)
    is_english = locale == "en-US"
    text = (message or '').strip()
    compact_text = re.sub(r'\s+', '', text)
    lowered = text.lower()
    is_medical = any(keyword.lower() in lowered for keyword in _MEDICAL_FALLBACK_KEYWORDS)

    if is_medical:
        return {
            'score': ASSESSMENT_SCORE_LOW,
            'details': {
                'scene': 'medical',
                'analysis': (
                    'The assessment model is unavailable. Medical requests cannot proceed without structured verification.'
                    if is_english else
                    '评估模型不可用，医疗需求不能在缺少结构化核验时直接进入分析'
                ),
                'risk_reason': (
                    'Medical decisions have a high cost of error, so conservative fallback is enabled.'
                    if is_english else
                    '医疗决策具有较高错误成本，已启用保守降级'
                ),
                'scores': {},
            },
            'passed': False,
            'questions': [
                {
                    'question': 'Please provide the confirmed diagnosis, pathology type, and current stage.' if is_english else '请补充明确诊断、病理类型及当前分期。',
                    'options': ['Provide details', 'Not sure yet'] if is_english else ['详细补充', '暂不清楚'],
                },
                {
                    'question': 'Please provide prior and current treatments, medications, efficacy, and adverse reactions.' if is_english else '请补充既往和当前治疗、用药及疗效或不良反应。',
                    'options': ['Provide details', 'No treatment yet', 'Not sure yet'] if is_english else ['详细补充', '尚未治疗', '暂不清楚'],
                },
                {
                    'question': 'Please provide recent key test, imaging, or laboratory results.' if is_english else '请补充近期关键检查、影像或化验结果。',
                    'options': ['Provide details', 'No results yet', 'Not sure yet'] if is_english else ['详细补充', '暂无结果', '暂不清楚'],
                },
            ],
            'risk_level': 'high',
            'category': 'medical',
            'scene': 'medical',
            'degraded': True,
            'degradation_reason': (
                'The assessment model is unavailable; conservative medical fallback was used.'
                if is_english else
                '需求评估模型不可用，医疗场景采用保守降级'
            ),
        }

    sentence_count = len([part for part in re.split(r'[。！？.!?;；]+', text) if part.strip()])
    is_detailed = (
        len(compact_text) >= ASSESSMENT_CHAR_THRESHOLD
        or (len(compact_text) >= 12 and sentence_count >= 2)
    )
    if not is_detailed:
        return {
            'score': ASSESSMENT_SCORE_LOW,
            'details': {
                'scene': 'general',
                'analysis': (
                    'The request is too brief for a reliable assessment.'
                    if is_english else
                    '需求描述过于简短，无法进行有效评估'
                ),
                'risk_reason': '',
                'scores': {},
            },
            'passed': False,
            'questions': [{
                'question': 'Please add the goal, current situation, constraints, and expected outcome.' if is_english else '请补充目标、现状、约束条件和期望结果。',
                'options': ['Provide details', 'Give a brief summary', 'Skip for now'] if is_english else ['详细补充', '简要说明', '暂不补充'],
            }],
            'risk_level': 'low',
            'category': 'other',
            'scene': 'general',
            'degraded': True,
            'degradation_reason': (
                'The assessment model is unavailable; text completeness rules were used.'
                if is_english else
                '需求评估模型不可用，采用字符与句子完整度规则'
            ),
        }

    return {
        'score': ASSESSMENT_SCORE_HIGH,
        'details': {
            'scene': 'general',
            'analysis': (
                'The request meets the baseline completeness needed to form an expert team.'
                if is_english else
                '需求描述达到基础完整度，可以进行团队组建'
            ),
            'risk_reason': '',
            'scores': {},
        },
        'passed': True,
        'questions': [],
        'risk_level': 'medium',
        'category': 'other',
        'scene': 'general',
        'degraded': True,
        'degradation_reason': (
            'The assessment model is unavailable; text completeness rules were used.'
            if is_english else
            '需求评估模型不可用，采用字符与句子完整度规则'
        ),
    }

_SCENES = frozenset({
    "technology", "medical", "investment", "legal",
    "social_hotspot", "decision_making", "general",
})

_ASSESSMENT_THRESHOLDS = {
    "technology": 60,
    "medical": 50,
    "investment": 60,
    "legal": 55,
    "social_hotspot": 45,
    "decision_making": 55,
    "general": 50,
}

_SCENE_TABLE_ROWS = {
    "technology":      ("软件开发、系统设计、技术实现、编程问题", '“如何设计用户系统？”'),
    "medical":         ("疾病诊断、健康咨询、用药指导、症状分析", '“头痛三天了，怎么办？”'),
    "investment":      ("投资分析、理财规划、风险评估、资产配置", '“有100万如何理财？”'),
    "legal":           ("法律咨询、合同审查、纠纷处理、权益维护", '“房东不退押金怎么办？”'),
    "social_hotspot":  ("时事评论、热点分析、观点讨论、趋势判断", '“怎么看AI发展趋势？”'),
    "decision_making": ("选择困难、方案对比、决策辅助、利弊分析", '“该考研还是工作？”'),
    "general":         ("无法归类的通用问题", "其他"),
}

_CATEGORY_TABLE_ROWS = {
    "technology": "编程、软件开发、系统架构、数据库、API设计、DevOps等",
    "business":   "商业策略、市场营销、企业管理、产品规划等",
    "medical":    "医疗诊断、健康咨询、医学知识、药品信息等",
    "investment": "投资分析、理财规划、风险评估、股票基金等",
    "science":    "科研、物理、化学、生物、数学等学术问题",
    "writing":    "文案、创意写作、内容创作、编辑校对等",
    "legal":      "法律咨询、合规、合同审查、知识产权等",
    "education":  "教学方法、学习规划、课程设计、考试辅导等",
    "lifestyle":  "日常生活、旅游、美食、娱乐、健身等",
    "other":      "无法归类的需求",
}

_RISK_LEVEL_SECTION = """\
## 三、决策风险等级评估

根据以下标准判断决策风险等级：

### **low**（低风险）
**适用场景**：简单查询、信息获取、常规操作、日常咨询
**特征**：
- 不涉及重大决策
- 结果可逆
- 影响范围小
- 错误成本较低

### **medium**（中风险）
**适用场景**：功能开发、技术选型、流程优化、方案设计
**特征**：
- 需要一定资源投入
- 结果部分可逆
- 影响范围中等
- 错误成本适中

### **high**（高风险）
**适用场景**：架构决策、重大投资、产品方向、战略规划、关键系统变更
**特征**：
- 资源投入大
- 结果难以逆转
- 影响范围广
- 涉及核心竞争力
- 错误成本高

**重要**：高风险决策会在后续流程中引入逆向思考顾问（critic-munger）进行批判性分析，确保决策质量。"""

_OUTPUT_FORMAT_TEMPLATE = """\
## 输出格式

请严格按照以下 JSON 格式输出，不要添加任何其他内容：

```json
{{
  "scene": "<场景类型: {scenes}>",
  "scores": {{
    "<维度名称（必须严格使用当前 scene 对应的中文维度名，禁止英文 key 和别名）>": <0-该维度最高分>,
    ...
  }},
  "total_score": <加权总分 0-100>,
  "analysis": "<评估分析：为什么给出这个评分>",
  "passed": <布尔值: 加权总分 >= 场景阈值>,
  "risk_level": "<low 或 medium 或 high>",
  "risk_reason": "<风险等级判断理由>",
  "category": "<{categories}>",
  "category_reason": "<分类理由>",
  "questions": [
    {{
      "question": "<针对缺失维度的具体问题1>",
      "options": ["<常见选项A>", "<常见选项B>", "<常见选项C>"],
      "selection_type": "<single 或 multiple>"
    }},
    {{
      "question": "<针对缺失维度的具体问题2>",
      "options": ["<常见选项A>", "<常见选项B>", "<常见选项C>"],
      "selection_type": "single"
    }}
  ]
}}
```

**重要规则**：

1. **评分计算**：
   - 总分 = 各维度得分之和（每个场景的维度分值总和为 100 分）
   - `scores` 只能使用 `SCENE_SCORE_LIMITS[scene]` 中定义的中文维度名
   - 不要翻译、改写、扩展维度名；若 scene=medical，只能从 `症状描述/病史信息/检查结果/用药情况/个人情况` 中选

2. **通过阈值**：
{threshold_lines}

3. **questions 规则**（强制要求，不可省略）：
   - 总分低于阈值时，**必须**在 questions 数组中提供 2-4 个针对性的补充问题
   - 每个问题**必须**包含 question（问题文本）和 options（**至少 3 个具体预设选项**）
   - 每个问题必须包含 selection_type；只能为 single（单选）或 multiple（多选）
   - options **不允许为空数组**，必须提供与问题场景紧密相关的具体选项
   - 选项应**根据问题具体内容定制**，而非通用占位符（如"详细描述"）
   - 示例：若问题为"症状持续多久？"，options 应为 ["几小时", "1-3天", "一周以上", "慢性长期"]
   - 示例：若问题为"使用什么技术栈？"，options 应为 ["Python/Flask", "Java/Spring", "Node.js", "Go", "其他"]
   - 每个缺失维度建议提出 1-2 个具体问题
   - 问题应具体、有针对性，帮助用户补充关键信息
   - **【重要去重规则】**：如果用户消息中包含"已问过的问题"列表，你必须：
     1. **逐一对比**：检查你生成的每个新问题是否与已问问题语义相似
     2. **严禁重复**：不得问已问过的问题或类似问题（如"持有股票"与"是否持有"视为重复）
     3. **探索新维度**：针对尚未覆盖的评分维度提出全新问题
     4. 如果所有维度都已覆盖但分数仍低，可深入追问细节而非重复已有问题

4. **风险等级判断**：
   - 基于问题的实际影响，而非仅看描述长度
   - 考虑资源投入、可逆性、影响范围

5. **category 规则**：
   - 必须是指定的分类之一，不能自创"""

# Category suffix note used in threshold_lines for medical/social_hotspot/general
_THRESHOLD_NOTES = {
    "medical":        "（医疗场景门槛较低，避免延误）",
    "social_hotspot": "（鼓励讨论）",
}

_CATEGORIES = "|".join(_CATEGORY_TABLE_ROWS.keys())
_SCENES_PIPE = "|".join(_SCENES)

SCENE_SCORE_LIMITS = {
    "technology": {
        "目标明确性": 35,
        "预期成果": 25,
        "边界范围": 25,
        "约束条件": 15,
    },
    "medical": {
        "症状描述": 35,
        "病史信息": 20,
        "检查结果": 30,
        "用药情况": 10,
        "个人情况": 5,
    },
    "investment": {
        "投资目标": 28,
        "风险偏好": 28,
        "资金规模": 22,
        "投资期限": 13,
        "特殊限制": 9,
    },
    "legal": {
        "案件背景": 32,
        "当事人身份": 22,
        "争议焦点": 27,
        "期望结果": 13,
        "证据情况": 6,
    },
    "social_hotspot": {
        "话题明确性": 35,
        "分析深度": 30,
        "关注角度": 20,
        "背景了解": 10,
        "立场倾向": 5,
    },
    "decision_making": {
        "决策背景": 28,
        "可选方案": 28,
        "决策标准": 22,
        "个人情况": 13,
        "紧迫程度": 9,
    },
    "general": {
        "问题清晰度": 45,
        "背景信息": 30,
        "期望深度": 17,
        "应用场景": 8,
    },
}

SCENE_SCORE_DIM_HINTS = {
    "technology": {
        "目标明确性": "要解决什么问题？达到什么目的？",
        "预期成果": "成功标准是什么？交付物是什么？",
        "边界范围": "涉及哪些模块？不包括什么？",
        "约束条件": "时间限制？技术栈限制？性能要求？（可选，缺失不扣分）",
    },
    "medical": {
        "症状描述": "哪里不舒服？持续多久？严重程度？",
        "病史信息": "既往病史？家族病史？",
        "检查结果": "化验结果？影像报告？",
        "用药情况": "正在吃什么药？（可选，缺失不扣分）",
        "个人情况": "年龄？性别？过敏史？（可选，缺失不扣分）",
    },
    "investment": {
        "投资目标": "保值？增值？养老？教育？",
        "风险偏好": "保守？稳健？激进？",
        "资金规模": "可投资金额？",
        "投资期限": "短期？中期？长期？",
        "特殊限制": "流动性需求？行业偏好？（可选，缺失不扣分）",
    },
    "legal": {
        "案件背景": "发生了什么？时间线？",
        "当事人身份": "原告？被告？第三人？",
        "争议焦点": "主要分歧是什么？",
        "期望结果": "希望达成什么结果？",
        "证据情况": "有什么证据？（可选，缺失不扣分）",
    },
    "social_hotspot": {
        "话题明确性": "讨论的具体话题是什么？",
        "分析深度": "浅层了解？深度分析？全面研究？",
        "关注角度": "经济角度？社会角度？技术角度？",
        "背景了解": "是否了解相关背景？需要科普吗？",
        "立场倾向": "需要客观分析还是有倾向性？（可选，缺失不扣分）",
    },
    "decision_making": {
        "决策背景": "面临什么选择？为什么纠结？",
        "可选方案": "有哪些选项？",
        "决策标准": "最看重什么？成本？时间？风险？",
        "个人情况": "当前状态？资源条件？",
        "紧迫程度": "需要多久做决定？（可选，缺失不扣分）",
    },
    "general": {
        "问题清晰度": "问题是否表述清楚？",
        "背景信息": "相关背景是什么？",
        "期望深度": "简单回答？详细解释？专业分析？",
        "应用场景": "什么场景下需要？（可选，缺失不扣分）",
    },
}


class RequirementAssessor:
    """需求评估器"""

    def __init__(
        self,
        llm_service,
        max_tokens_limit: int = 16384,
        locale: SupportedLocale = "zh-CN",
    ):
        """
        初始化需求评估器

        Args:
            llm_service: LLM 服务实例
            max_tokens_limit: 最大 token 限制
        """
        self.llm_service = llm_service
        self.max_tokens_limit = max_tokens_limit
        self.locale = resolve_generation_locale(explicit_locale=locale)

    def _build_system_prompt(self, json_only: bool = False) -> str:
        if self.locale == "en-US":
            prompt = (
                "You are a professional requirements analyst. Your primary task is to identify "
                "the request scenario and assess information completeness for that scenario."
            )
            if json_only:
                prompt += " Return strict JSON only, with no additional text."
        else:
            prompt = "你是一个专业的需求分析师。你的首要任务是识别问题场景，然后根据场景评估信息完整性。"
            if json_only:
                prompt += "\n\n请严格按照 JSON 格式输出，不要添加任何其他内容。"

        return (
            prompt
            + build_output_locale_instruction(self.locale, "assessment")
            + build_output_locale_instruction(self.locale, "question")
        )

    def assess_requirement(
        self,
        message: str,
        history: List[Dict],
        retry_callback=None,
        context_messages: Optional[List[Dict]] = None,
        previous_questions: Optional[List[Dict]] = None,
    ) -> Dict:
        """
        评估需求完整性

        Args:
            message: 用户消息（当 context_messages 为空时使用）
            history: 对话历史
            retry_callback: 重试回调函数
            context_messages: 预构建的 LLM 消息列表（ContextPack.to_messages() 输出）
            previous_questions: 之前已问过的问题列表（用于 fallback 路径去重）

        Returns:
            Dict: 评估结果
        """
        # 格式化对话历史
        history_context = self._format_history_for_assessment(history) if history else ""

        # 构建评估提示词（fallback 路径需要注入已问过的问题）
        assessment_prompt = self._build_assessment_prompt(message, history_context, previous_questions)

        # 【调试日志】打印完整评估提示词
        logger.info(f"=== ASSESSMENT PROMPT START (message_len={len(message)}, "
                     f"has_context_messages={context_messages is not None}, "
                     f"previous_questions_count={len(previous_questions) if previous_questions else 0}) ===")
        system_prompt = self._build_system_prompt()
        logger.info(f"[ASSESSMENT_SYSTEM_PROMPT] {system_prompt}")
        logger.info(f"[ASSESSMENT_USER_PROMPT]\n{assessment_prompt[:3000]}")
        logger.info("=== ASSESSMENT PROMPT END ===")

        try:
            messages = [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {"role": "user", "content": assessment_prompt},
            ]
            structured = safe_async_run(
                self.llm_service.call_structured(
                    messages=messages,
                    response_model=AssessmentResult,
                )
            )
            result = self._assessment_model_to_result(structured)
            # 【调试日志】打印结构化评估结果
            logger.info(f"[ASSESSMENT_RESULT] score={result.get('score')}, passed={result.get('passed')}, "
                        f"risk_level={result.get('risk_level')}, questions_count={len(result.get('questions', []))}")
            if result.get('questions'):
                logger.info(f"[ASSESSMENT_QUESTIONS] {[q.get('question', '')[:50] for q in result['questions']]}")
            return result
        except Exception as e:
            logger.warning(f"Structured assessment failed, falling back to JSON parser: {e}", exc_info=True)

        try:
            # 调用 LLM API（带重试回调）
            response = self.llm_service.call_sync(
                message=assessment_prompt,
                system_prompt=self._build_system_prompt(json_only=True),
                max_tokens=self.max_tokens_limit,
                retry_callback=retry_callback
            )

            # 解析 JSON 响应（fallback 路径，待 call_structured 稳定后移除）
            result = self._parse_assessment_response(response)

            # 【调试日志】打印 fallback 评估结果
            logger.info(f"[ASSESSMENT_RESULT_FALLBACK] score={result.get('score')}, passed={result.get('passed')}, "
                        f"risk_level={result.get('risk_level')}, questions_count={len(result.get('questions', []))}")
            if result.get('questions'):
                logger.info(f"[ASSESSMENT_QUESTIONS_FALLBACK] {[q.get('question', '')[:50] for q in result['questions']]}")

            return result

        except Exception as e:
            logger.error(f"LLM assessment API call failed: {e}", exc_info=True)
            # Fallback to simple assessment
            return self._simple_assessment(message)

    def _format_history_for_assessment(self, history: List[Dict], max_turns: int = 3) -> str:
        """
        格式化对话历史供评估使用

        Args:
            history: 对话历史
            max_turns: 最大轮次

        Returns:
            格式化的历史文本
        """
        if not history:
            return ""

        # 只取最近的几轮对话
        recent_history = history[-max_turns:] if len(history) > max_turns else history

        lines = []
        for turn in recent_history:
            role = "用户" if turn.get('role') == 'user' else "助手"
            content = turn.get('content', '')[:200]  # 限制每条长度
            lines.append(f"**{role}**: {content}")

        return "\n\n".join(lines)

    def _build_assessment_prompt(
        self,
        message: str,
        history_context: str,
        previous_questions: Optional[List[Dict]] = None,
    ) -> str:
        """构建评估提示词

        Args:
            message: 用户消息
            history_context: 对话历史上下文
            previous_questions: 之前已问过的问题列表（格式 [{"question": "...", "options": [...]}]）
        """
        dedup_section = ""
        if previous_questions:
            dedup_section = "\n\n**【已问过的问题 - 禁止重复】**\n"
            dedup_section += "以下问题已经问过用户，请**不要**再问类似或相同的问题：\n"
            for i, q in enumerate(previous_questions, 1):
                dedup_section += f"  {i}. {q.get('question', '')}\n"
            dedup_section += "\n请针对其他缺失维度提出**全新的**问题。如果所有维度都已覆盖，可深入追问细节。\n"

        scene_table = "\n".join(
            f"| {scene} | {feat} | {example} |"
            for scene, (feat, example) in _SCENE_TABLE_ROWS.items()
        )
        category_table = "\n".join(
            f"| **{cat}** | {desc} |"
            for cat, desc in _CATEGORY_TABLE_ROWS.items()
        )
        threshold_lines = "\n".join(
            f"   - {scene}: {_ASSESSMENT_THRESHOLDS[scene]} 分{_THRESHOLD_NOTES.get(scene, '')}"
            for scene in _SCENES
        )

        history_section = ""
        if history_context:
            history_section = f"## 对话历史\n{history_context}"

        output_section = _OUTPUT_FORMAT_TEMPLATE.format(
            scenes=_SCENES_PIPE,
            categories=_CATEGORIES,
            threshold_lines=threshold_lines,
        )

        prompt = f"""请评估以下问题，识别场景类型并评估信息完整性。
{dedup_section}

## 用户问题
{message}

{history_section}

---

## 一、场景识别

请判断问题属于以下哪个场景：

| 场景 | 特征 | 示例 |
|------|------|------|
{scene_table}

---

## 二、信息完整性评估

根据识别的场景，使用对应的评估维度（总分均为 100 分）。

**关键要求**：
- 你必须先确定 `scene`，再根据该 `scene` 从下方评分详情规范中选择维度
- `scores` 里的 key 必须严格使用当前 `scene` 对应的中文维度名
- 不允许输出英文 key，不允许输出别名，不允许输出当前 `scene` 之外的维度
- `total_score` 必须等于 `scores` 中各维度分数之和

{self._build_scene_score_reference()}

---

{_RISK_LEVEL_SECTION}

---

## 四、问题分类

根据问题内容，选择最匹配的分类：

| 分类 | 说明 |
|------|------|
{category_table}

---

{output_section}
"""
        if self.locale == "en-US":
            return f"{_ENGLISH_ASSESSMENT_FIELD_RULE}\n{prompt}\n{_ENGLISH_ASSESSMENT_FIELD_RULE}"
        return prompt

    def _assessment_model_to_result(self, result: AssessmentResult) -> Dict:
        """将结构化评估模型转换为现有 dict 形状。"""
        # 使用 _normalize_questions 确保 options fallback 生效
        raw_questions = [q.model_dump(exclude_unset=True) for q in result.questions]
        normalized_questions = self._normalize_questions(raw_questions)
        return self._build_normalized_result(
            scene=result.scene,
            score=result.score,
            scores=result.scores,
            analysis=result.details,
            risk_reason=result.risk_reason,
            questions=normalized_questions,
            risk_level=result.risk_level,
            category=result.category,
        )

    def _parse_assessment_response(self, response: str) -> Dict:  # TODO: cleanup after call_structured stabilization
        """解析评估响应"""
        # 尝试多种 JSON 提取方式
        result = None
        json_str = None

        # 方式1: 查找 ```json 代码块
        json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1).strip()
            try:
                result = json.loads(json_str)
            except json.JSONDecodeError as e:
                logger.warning(f"JSON parse failed in code block: {e}")

        # 方式2: 查找裸 JSON 对象
        if result is None:
            json_match = re.search(r'\{(?:[^{}]|(?:\{(?:[^{}]|(?:\{[^{}]*\})*)*\})*)*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                try:
                    result = json.loads(json_str)
                except json.JSONDecodeError as e:
                    logger.warning(f"JSON parse failed in raw search: {e}")

        # 方式3: 尝试直接解析整个响应
        if result is None:
            try:
                result = json.loads(response.strip())
            except json.JSONDecodeError as e:
                logger.error(f"All JSON parse attempts failed: {e}")
                raise ValueError(f"Failed to parse LLM response as JSON: {e}")

        if result is None:
            raise ValueError("Failed to extract valid JSON from LLM response")

        # 构建标准格式结果
        return self._normalize_assessment_result(result)

    def _normalize_assessment_result(self, result: Dict) -> Dict:
        """标准化评估结果"""
        # 获取场景类型
        scene = result.get('scene', 'general')
        valid_scenes = list(_SCENES)
        if scene not in valid_scenes:
            scene = 'general'

        # 获取风险等级
        risk_level = result.get('risk_level', 'medium')
        if risk_level not in ['low', 'medium', 'high']:
            risk_level = 'medium'

        # 获取分类
        category = normalize_category_key(result.get('category', 'other'))

        return self._build_normalized_result(
            scene=scene,
            score=result.get('score', result.get('total_score', 50)),
            scores=result.get('scores', {}),
            analysis=result.get('analysis', ''),
            risk_reason=result.get('risk_reason', ''),
            questions=self._normalize_questions(result.get('questions', [])),
            risk_level=risk_level,
            category=category,
        )

    def _build_normalized_result(
        self,
        scene: str,
        score,
        scores,
        analysis: str,
        risk_reason: str,
        questions: list,
        risk_level: str,
        category: str,
    ) -> Dict:
        """规范化维度评分，并保证总分与展示明细一致。"""
        normalized_scores = self._normalize_scores(scene, scores)
        normalized_score = self._normalize_total_score(score, normalized_scores, bool(scores))
        passed = normalized_score >= self._get_scene_threshold(scene)

        return {
            'score': normalized_score,
            'details': {
                'scene': scene,
                'analysis': analysis,
                'risk_reason': risk_reason,
                'scores': normalized_scores,
            },
            'passed': passed,
            'questions': questions,
            'risk_level': risk_level,
            'category': category,
            'scene': scene,
        }

    def _normalize_scores(self, scene: str, scores) -> Dict[str, int]:
        """按场景允许维度白名单和单维上限清洗评分详情。"""
        if not isinstance(scores, dict):
            return {}

        allowed_scores = SCENE_SCORE_LIMITS.get(scene, SCENE_SCORE_LIMITS['general'])
        normalized_scores: Dict[str, int] = {}

        for raw_name, raw_score in scores.items():
            score_name = str(raw_name).strip() if raw_name is not None else ""
            if score_name not in allowed_scores:
                continue
            if not isinstance(raw_score, (int, float)):
                continue

            bounded_score = max(0, min(allowed_scores[score_name], int(raw_score)))
            previous_score = normalized_scores.get(score_name)
            normalized_scores[score_name] = (
                bounded_score if previous_score is None else max(previous_score, bounded_score)
            )

        return normalized_scores

    def _build_scene_score_reference(self) -> str:
        """生成发给 LLM 的场景评分详情规范。"""
        lines = ["### 场景评分详情规范"]
        for scene, dimension_limits in SCENE_SCORE_LIMITS.items():
            lines.append(f"\n#### {scene}")
            for dim_name, max_score in dimension_limits.items():
                dim_hint = SCENE_SCORE_DIM_HINTS.get(scene, {}).get(dim_name, "")
                lines.append(f"- {dim_name}: 0-{max_score} 分；{dim_hint}")
        return "\n".join(lines)

    def _normalize_total_score(self, score, normalized_scores: Dict[str, int], has_raw_scores: bool) -> int:
        """存在评分详情时，优先根据展示明细重算总分。"""
        if has_raw_scores:
            return min(100, sum(normalized_scores.values()))

        if not isinstance(score, (int, float)):
            return 50
        return max(0, min(100, int(score)))

    @staticmethod
    def _get_scene_threshold(scene: str) -> int:
        """返回场景通过阈值。"""
        return _ASSESSMENT_THRESHOLDS.get(scene, _ASSESSMENT_THRESHOLDS["general"])

    def _normalize_questions(self, questions: list) -> list:
        """标准化问题格式

        兼容两种格式：
        - 新格式：[{"question": "...", "options": ["..."]}, ...]
        - 旧格式：["问题1", "问题2", ...]

        当 LLM 未返回 options 时，自动补充通用选项 fallback。

        Returns:
            统一为新格式列表
        """
        if not questions:
            return []

        # 通用选项 fallback（适用于大多数追问场景）
        GENERIC_OPTIONS = (
            ["Provide details", "Give a brief summary", "Skip for now"]
            if self.locale == "en-US"
            else ["详细描述", "简要说明", "暂不补充"]
        )

        normalized = []
        for q in questions:
            if isinstance(q, dict):
                # 新格式：保留 question + options（空时补充 fallback）
                opts = q.get("options", [])
                if not opts:  # 空数组或缺失时补充通用选项
                    opts = GENERIC_OPTIONS
                question_text = q.get("question", str(q))
                selection_type = q.get("selection_type")
                if selection_type not in {"single", "multiple"}:
                    lowered = str(question_text).lower()
                    selection_type = (
                        "multiple"
                        if any(marker in lowered for marker in (
                            "可多选", "（多选）", "[多选]", "multiple choice",
                            "select all that apply", "select one or more",
                        ))
                        else "single"
                    )
                normalized.append({
                    "question": question_text,
                    "options": opts,
                    "selection_type": selection_type,
                })
            elif isinstance(q, str):
                # 旧格式：字符串转为对象，补充通用选项
                normalized.append({
                    "question": q,
                    "options": GENERIC_OPTIONS,
                    "selection_type": "single",
                })
            else:
                normalized.append({
                    "question": str(q),
                    "options": GENERIC_OPTIONS,
                    "selection_type": "single",
                })
        return normalized

    def _simple_assessment(self, message: str) -> Dict:
        """简单评估（降级方案 - 仅用于 LLM 完全失败时）"""
        return simple_assessment_fallback(message, self.locale)
