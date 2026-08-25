"""
团队组建模块

负责根据需求选择合适的 Agent 组建团队
"""
import json
import logging
import re
from typing import Dict, List, Optional

from utils.async_utils import safe_async_run
from schemas.leader import TeamSelectionResult
from .locale_generation import resolve_agent_display_name, resolve_generation_locale

logger = logging.getLogger(__name__)

_ENGLISH_TEAM_OUTPUT_RULE = """## Mandatory English output rule
Write every user-visible value in the team-selection JSON in English (en-US), including `analysis`,
`reason`, `role_description`, and `team_strategy`. Keep `agent_id`, enum values, and agent names
exactly as they appear in the available-agent list; those are machine/catalog values.
The rubric and available-agent descriptions below may be Chinese reference text, but they must not
determine the language of the output values.
"""


class TeamFormer:
    """团队组建器"""

    def __init__(self, llm_service, agent_reader, max_tokens_limit: int = 16384, locale: str = "zh-CN"):
        """
        初始化团队组建器

        Args:
            llm_service: LLM 服务实例
            agent_reader: Agent 内容读取器（AgentContentReader）
            max_tokens_limit: 最大 token 限制
        """
        self.llm_service = llm_service
        self.agent_reader = agent_reader
        self.max_tokens_limit = max_tokens_limit
        self.locale = resolve_generation_locale(explicit_locale=locale)

    def _build_system_prompt(self, json_only: bool = False) -> str:
        if self.locale == "en-US":
            prompt = (
                "You are a professional team formation advisor. Select the most suitable expert "
                "combination for the user's request and explain the selection briefly."
            )
            if json_only:
                prompt += " Return strict JSON only, with no additional text."
            return f"{_ENGLISH_TEAM_OUTPUT_RULE}\n{prompt}\n{_ENGLISH_TEAM_OUTPUT_RULE}"

        prompt = "你是一个专业的团队组建顾问，擅长根据需求选择最合适的专家组合。"
        if json_only:
            prompt += "\n\n请严格按照 JSON 格式输出，不要添加任何其他内容。"
        return prompt

    def form_team(
        self,
        message: str,
        risk_level: str = 'medium',
        retry_callback=None
    ) -> Dict:
        """
        组建 Agent 团队

        Args:
            message: 用户需求
            risk_level: 风险等级 (low/medium/high)
            retry_callback: 重试回调函数

        Returns:
            Dict: {
                'selected_agents': List[Dict],
                'team_strategy': str
            }
        """
        # 获取所有可用的 Agent
        all_agents = self.agent_reader.get_all_agents(is_enabled=True)

        # 检测是否为医疗场景
        is_medical = self._is_medical_scenario(message, all_agents)

        # 构建 Agent 列表信息
        agent_list_text = self._build_agent_list_for_selection(all_agents)

        # 构建选择提示词
        selection_prompt = self._build_selection_prompt(
            message, agent_list_text, risk_level, is_medical
        )

        # 调用 LLM 进行选择
        try:
            messages = [
                {"role": "system", "content": self._build_system_prompt()},
                {"role": "user", "content": selection_prompt},
            ]
            structured_result = safe_async_run(
                self.llm_service.call_structured(
                    messages=messages,
                    response_model=TeamSelectionResult,
                )
            )
            result = self._team_selection_model_to_result(structured_result)
            return self._validate_selected_agents(result, all_agents, is_medical, risk_level)
        except Exception as e:
            logger.warning(f"Structured agent selection failed, falling back to JSON parser: {e}", exc_info=True)

        selection_result = self._call_llm_for_agent_selection(
            selection_prompt, retry_callback
        )

        # 解析选择结果
        selected_agents_data = self._parse_agent_selection_result(selection_result)

        if not selected_agents_data:
            raise ValueError("Failed to parse agent selection result from Claude")

        return self._validate_selected_agents(
            selected_agents_data, all_agents, is_medical, risk_level
        )

    def _is_medical_scenario(self, message: str, all_agents: List[Dict]) -> bool:
        """
        检测是否为医疗场景

        Args:
            message: 用户需求
            all_agents: 所有可用的 Agent 列表

        Returns:
            bool: 是否为医疗场景
        """
        # 医疗关键词列表
        medical_keywords = [
            '诊断', '治疗', '症状', '疾病', '患者', '病人', '用药', '药物',
            '手术', '检查', '化验', '影像', '门诊', '住院', '出院',
            '疼痛', '发热', '咳嗽', '头痛', '腹痛', '胸痛',
            '高血压', '糖尿病', '肿瘤', '癌症', '心脏病', '肝病', '肾病',
            '风湿', '关节炎', '过敏', '感染', '炎症',
            'medical', 'patient', 'diagnosis', 'treatment', 'surgery', 'hospital'
        ]

        # 检查消息中是否包含医疗关键词
        message_lower = message.lower()
        for keyword in medical_keywords:
            if keyword.lower() in message_lower:
                return True

        # 检查是否有医疗类 Agent 被选中
        medical_agent_keywords = [
            '医生', '专家', '科', '医院', '诊疗', '临床',
            'cardiac', 'heart', 'surgery', 'transplant', 'rheumatology',
            'oncology', 'neurology', 'pediatrics', 'gynecology', 'urology'
        ]

        for agent in all_agents:
            desc = agent.get('description', '').lower()
            name = agent.get('name', '').lower()
            for keyword in medical_agent_keywords:
                if keyword.lower() in desc or keyword.lower() in name:
                    if any(k in message_lower for k in ['手术', '移植', '心脏', '肿瘤', '神经', '儿科', '妇科', '泌尿']):
                        return True

        return False

    def _build_agent_list_for_selection(self, all_agents: List[Dict]) -> str:
        """
        构建 Agent 列表文本，供 LLM 选择（精简格式以节省上下文）

        有 capabilities 的 Agent 追加一行能力摘要（能力 / 适用场景 / 专业度）；
        无 capabilities 的 Agent 保持旧格式（仅 agent_id + name + description）。

        Args:
            all_agents: 所有 Agent 元数据列表

        Returns:
            格式化的 Agent 列表文本
        """
        lines = []
        for i, agent in enumerate(all_agents, 1):
            # 截断描述到 80 字符，避免上下文膨胀
            desc = agent.get('description', '无描述')
            if len(desc) > 80:
                desc = desc[:77] + '...'
            agent_id = agent.get('agent_id', agent.get('id', ''))
            display_name = resolve_agent_display_name(
                agent_id,
                agent.get('name'),
                self.locale,
                agent.get('is_system'),
            )
            lines.append(f"{i}. `{agent_id}` - {display_name}: {desc}")

            # 有 capabilities 时追加能力行
            capabilities = agent.get('capabilities', [])
            if capabilities:
                caps_str = ', '.join(str(c) for c in capabilities[:6])
                parts = [f"能力: {caps_str}"]
                contexts = agent.get('preferred_contexts', [])
                if contexts:
                    parts.append(f"适用: {', '.join(str(c) for c in contexts[:4])}")
                skill_level = agent.get('skill_level', 3)
                parts.append(f"专业度: {skill_level}/5")
                lines.append('   ' + ' | '.join(parts))

        return '\n'.join(lines)

    def _build_selection_prompt(
        self,
        message: str,
        agent_list_text: str,
        risk_level: str,
        is_medical: bool
    ) -> str:
        """构建选择提示词"""
        # 风险等级中文映射
        risk_level_map = {
            'low': '低风险',
            'medium': '中风险',
            'high': '高风险'
        }
        risk_level_text = risk_level_map.get(risk_level, '中风险')

        # 根据风险等级和场景类型构建选择原则
        if risk_level == 'high':
            if is_medical:
                selection_principles = """## 选择原则
1. **医疗场景的特殊性**：医疗专家本身已具备鉴别诊断和风险预警能力，不需要额外的逆向思考顾问
2. 理解需求的本质和涉及的医疗领域
3. 选择能够覆盖诊断各方面的专家（如相关科室、影像、检验等）
4. 确保团队有足够的医疗专业覆盖
5. 考虑专家之间的互补性（如内科+外科+影像）
6. 优先选择最相关领域的资深专家
7. 团队规模建议 3-4 人，确保专业覆盖"""
            else:
                selection_principles = """## 选择原则
1. **必须包含 critic-munger（逆向思考顾问）作为团队一员** - 高风险决策需要逆向思维审查
2. 理解需求的本质和涉及的领域
3. 选择能够覆盖需求各个方面的专家
4. 确保团队有正反两方面的视角，避免集体确认偏差
5. 考虑专家之间的互补性
6. 优先选择最相关领域的资深专家
7. 团队规模建议 4-5 人，确保有足够的视角"""
        elif risk_level == 'medium':
            selection_principles = """## 选择原则
1. 建议考虑包含 critic-munger（逆向思考顾问）进行方案审查
2. 理解需求的本质和涉及的领域
3. 选择能够覆盖需求各个方面的专家
4. 考虑专家之间的互补性
5. 优先选择最相关领域的资深专家
6. 避免选择过多专家，保持团队精简高效（3-4人）"""
        else:  # low risk
            selection_principles = """## 选择原则
1. 理解需求的本质和涉及的领域
2. 选择能够覆盖需求各个方面的专家
3. 考虑专家之间的互补性
4. 优先选择最相关领域的资深专家
5. 避免选择过多专家，保持团队精简高效（2-3人）"""

        prompt = f"""你需要为一个团队选择最合适的专家组合。

## 用户需求
{message}

## 决策风险等级
当前决策风险等级为：**{risk_level_text}**

## 可用的专家列表
{agent_list_text}

## 任务
请分析用户需求，选择最合适的专家来组成团队。

## 输出格式
请按以下 JSON 格式输出（不要包含 ```json 标记）：
**重要：保持简洁，每个 agent 的 reason 和 role_description 控制在 50 字以内，避免输出过长导致截断。**

{{
  "analysis": "需求分析：简要说明你对需求的理解（50字以内）",
  "selected_agents": [
    {{
      "agent_id": "expert-id",
      "agent_name": "专家名称",
      "reason": "选择理由（50字以内）",
      "role_description": "角色描述（50字以内）"
    }}
  ],
  "team_strategy": "团队协作策略：这些专家如何协作来解决问题"
}}

{selection_principles}

**能力匹配指引**：
- 优先选择"能力"字段与需求关键词匹配度高的专家
- "适用场景"反映了专家最擅长的场景类型，结合需求判断
- "专业度"越高代表该领域经验越深，高风险决策优先选高专业度
- 无能力声明的专家仍可被选中，按名称和描述判断

请开始分析并选择专家："""
        if self.locale == "en-US":
            return f"{_ENGLISH_TEAM_OUTPUT_RULE}\n{prompt}\n{_ENGLISH_TEAM_OUTPUT_RULE}"
        return prompt

    def _team_selection_model_to_result(self, result: TeamSelectionResult) -> Dict:
        """将结构化团队选择模型转换为现有 dict 形状。"""
        return {
            'analysis': result.reasoning,
            'selected_agents': [agent.model_dump() for agent in result.agents],
            'team_strategy': result.team_strategy,
        }

    def _validate_selected_agents(
        self,
        result: Dict,
        all_agents: List[Dict],
        is_medical: bool,
        risk_level: str,
    ) -> Dict:
        """将模型实体引用限制在当前已启用 Agent 候选集内。"""
        available = {}
        for agent in all_agents:
            agent_id = agent.get('agent_id') or agent.get('id')
            if agent_id:
                available[agent_id] = agent

        selected = result.get('selected_agents') or []
        valid = []
        seen = set()
        rejected = 0
        fallback_used = False
        for selection in selected:
            agent_id = selection.get('agent_id')
            if not agent_id or agent_id not in available or agent_id in seen:
                rejected += 1
                continue
            seen.add(agent_id)
            normalized_selection = dict(selection)
            normalized_selection['agent_name'] = resolve_agent_display_name(
                agent_id,
                available[agent_id].get('name'),
                self.locale,
                available[agent_id].get('is_system'),
            )
            valid.append(normalized_selection)

        if not valid and available:
            fallback_used = True
            candidates = list(available.items())
            if is_medical:
                medical = [
                    item for item in candidates
                    if item[1].get('category') == 'medical'
                    or any(token in f"{item[1].get('name', '')} {item[1].get('description', '')}".lower()
                           for token in ('医疗', '医生', '肿瘤', '临床', 'medical', 'oncology'))
                ]
                if medical:
                    candidates = medical

            fallback_count = min(3 if risk_level == 'high' else 2, len(candidates))
            valid = [
                {
                    'agent_id': agent_id,
                    'agent_name': resolve_agent_display_name(
                        agent_id,
                        agent.get('name'),
                        self.locale,
                        agent.get('is_system'),
                    ),
                    'role_description': (
                        'Fallback execution using a registered Agent because model selection was invalid.'
                        if self.locale == 'en-US' else
                        '模型选择无有效候选，使用已注册 Agent 降级执行'
                    ),
                    'reason': (
                        'Deterministic candidate-validation fallback.'
                        if self.locale == 'en-US' else
                        '确定性候选校验降级'
                    ),
                    'is_fallback': True,
                }
                for agent_id, agent in candidates[:fallback_count]
            ]

        normalized = dict(result)
        normalized['selected_agents'] = valid
        if rejected or fallback_used or not valid:
            normalized['degraded'] = True
            if fallback_used:
                normalized['degradation_reason'] = (
                    f'团队模型没有可执行的有效成员（拒绝 {rejected} 个），已使用已注册 Agent 降级团队'
                )
            else:
                normalized['degradation_reason'] = (
                    f'团队模型返回 {rejected} 个无效或重复 Agent ID，已按已注册候选集过滤'
                )
            logger.warning(normalized['degradation_reason'])
        return normalized

    def _call_llm_for_agent_selection(self, prompt: str, retry_callback=None) -> str:
        """调用 LLM 进行 Agent 选择"""
        try:
            response = self.llm_service.call_sync(
                message=prompt,
                system_prompt=self._build_system_prompt(json_only=True),
                max_tokens=self.max_tokens_limit,
                retry_callback=retry_callback
            )
            return response
        except Exception as e:
            logger.error(f"LLM agent selection failed: {e}")
            raise

    def _parse_agent_selection_result(self, result: str) -> Optional[Dict]:
        """解析 Claude 的 Agent 选择结果"""
        try:
            if not result or not result.strip():
                logger.error("Empty Claude response")
                return None

            logger.info(f"Parsing Claude response, length: {len(result)}")

            # 预处理：替换中文引号
            result = result.replace('"', '"').replace('"', '"')
            result = result.replace('：', ':')

            # 尝试提取 JSON 部分
            json_str = None
            data = None

            # 方式1: 查找 ```json 代码块
            json_match = re.search(r'```json\s*(.*?)\s*```', result, re.DOTALL)
            if json_match:
                json_str = json_match.group(1).strip()
                logger.debug("Found JSON in code block")

            # 方式2: 查找裸 JSON 对象
            if json_str is None:
                json_match = re.search(r'\{(?:[^{}]|(?:\{(?:[^{}]|(?:\{[^{}]*\})*)*\})*)*\}', result, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                    logger.debug("Found JSON object in response")

            # 方式3: 尝试直接解析整个响应
            if json_str is None:
                json_str = result.strip()
                logger.debug("Attempting to parse entire response as JSON")

            if not json_str:
                logger.error(f"No JSON found in response. Response preview: {result[:500]}")
                return None

            # 解析 JSON（带容错和自动修复）
            try:
                data = json.loads(json_str)
            except json.JSONDecodeError as e:
                logger.warning(f"Initial JSON parse failed: {e}, attempting repair...")
                repaired_json = self._repair_truncated_json(json_str)
                if repaired_json:
                    try:
                        data = json.loads(repaired_json)
                        logger.info("Successfully parsed after JSON repair")
                    except json.JSONDecodeError as e2:
                        logger.error(f"Failed to parse repaired JSON: {e2}. Repaired JSON preview: {repaired_json[:500]}")
                        return None
                else:
                    logger.error(f"Failed to parse JSON: {e}. JSON string preview: {json_str[:500]}")
                    return None

            logger.info(f"Successfully parsed JSON with keys: {list(data.keys())}")

            # 适配不同的响应格式
            data = self._adapt_response_format(data)

            # 验证必需字段
            if 'selected_agents' not in data:
                logger.error("Missing 'selected_agents' in parsed result after adaptation")
                return None

            # 确保每个 agent 都有必需字段
            for agent in data['selected_agents']:
                if 'agent_id' not in agent:
                    logger.error(f"Missing 'agent_id' in agent: {agent}")
                    return None

                if 'role_description' not in agent:
                    agent['role_description'] = agent.get('reason', f"负责 {agent.get('agent_name', '相关领域')} 的工作")

            logger.info(f"Successfully parsed {len(data['selected_agents'])} agents")
            return data

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to parse agent selection result: {e}", exc_info=True)
            return None

    def _repair_truncated_json(self, json_str: str) -> Optional[str]:
        """
        修复被截断的 JSON 字符串

        LLM 输出可能因为 max_tokens 限制而被截断，此方法尝试修复常见的截断模式：
        - 在字符串中间截断 → 关闭字符串、对象/数组
        - 在数组中间截断 → 关闭数组
        - 缺少闭合的 } 或 ]

        Args:
            json_str: 可能被截断的 JSON 字符串

        Returns:
            Optional[str]: 修复后的 JSON 字符串，如果无法修复则返回 None
        """
        if not json_str:
            return None

        try:
            # 首先尝试直接解析（可能已经完整）
            json.loads(json_str)
            return json_str
        except json.JSONDecodeError:
            pass

        repaired = json_str.strip()

        # 策略1: 如果在字符串内部截断（最后一个引号未关闭）
        # 统计引号数量，如果是奇数说明有未关闭的字符串
        quote_count = repaired.count('"')
        if quote_count % 2 == 1:
            # 找到最后一个完整的字段值位置
            last_colon = repaired.rfind(':')
            if last_colon > 0:
                # 截断到最后一个冒号之前，移除不完整的值
                before_colon = repaired[:last_colon].rstrip()
                # 移除可能的逗号和字段名
                if before_colon.endswith(','):
                    before_colon = before_colon[:-1].rstrip()
                if before_colon.endswith('"'):
                    # 回退到上一个完整的键值对
                    prev_comma = before_colon.rfind(',')
                    if prev_comma > 0:
                        repaired = repaired[:prev_comma]
                    else:
                        repaired = before_colon[:-1]  # 移除开头的引号
                logger.info(f"Truncation detected in string value, truncated to {len(repaired)} chars")

        # 策略2: 平衡括号
        open_braces = repaired.count('{') - repaired.count('}')
        open_brackets = repaired.count('[') - repaired.count(']')

        # 关闭未闭合的数组和对象（从内到外）
        if open_brackets > 0:
            repaired += ']' * open_brackets
            logger.info(f"Added {open_brackets} closing bracket(s)")

        if open_braces > 0:
            repaired += '}' * open_braces
            logger.info(f"Added {open_braces} closing brace(s)")

        # 验证修复后的 JSON 是否可解析
        try:
            json.loads(repaired)
            logger.info(f"JSON repair successful, final length: {len(repaired)}")
            return repaired
        except json.JSONDecodeError as e:
            logger.warning(f"JSON repair attempt failed: {e}")
            return None

    def _adapt_response_format(self, data: Dict) -> Dict:
        """适配不同的 API 响应格式"""
        # 已经是标准格式
        if 'selected_agents' in data:
            logger.debug("Response is in standard Claude format")
            return data

        # 适配代理服务格式（如 glm-5）
        if 'recommended_team' in data:
            logger.info("Adapting proxy service format (recommended_team) to standard format")
            adapted = {
                'selected_agents': [],
                'team_strategy': data.get('project_requirement', '团队协作策略')
            }

            for agent in data['recommended_team']:
                role = agent.get('role', 'unknown')
                agent_id = self._map_role_to_agent_id(role)
                is_fallback = (agent_id == 'fullstack-dhh' and role not in ('全栈技术主管', '全栈开发'))

                adapted['selected_agents'].append({
                    'agent_id': agent_id,
                    'agent_name': agent.get('role', role),
                    'reason': agent.get('reason', ''),
                    **({'is_fallback': True} if is_fallback else {}),
                    'role_description': agent.get('role', role),
                    'priority': agent.get('priority', '中')
                })

            logger.info(f"Adapted {len(adapted['selected_agents'])} agents from proxy format")
            return adapted

        # 其他未知格式
        logger.warning(f"Unknown response format with keys: {list(data.keys())}")
        return data

    def _map_role_to_agent_id(self, role: str) -> str:
        """将角色名称映射到 Agent ID。

        优先查映射表，未命中则尝试 DB 模糊查询，最终 fallback 到 fullstack-dhh。
        """
        role_mapping = {
            # 开发类角色 → fullstack-dhh（全栈技术主管）
            '后端开发工程师': 'fullstack-dhh',
            '后端开发': 'fullstack-dhh',
            '前端开发工程师': 'fullstack-dhh',
            '前端开发': 'fullstack-dhh',
            '数据库工程师': 'fullstack-dhh',
            '数据库管理员': 'fullstack-dhh',
            '架构师': 'cto-vogels',
            '系统架构师': 'cto-vogels',
            '测试工程师': 'qa-bach',
            'DevOps工程师': 'devops-hightower',
            '安全工程师': 'compliance-gensler',
            '产品经理': 'product-norman',
            'UI设计师': 'product-norman',
            '项目经理': 'ceo-bezos',
        }

        # 尝试精确匹配
        if role in role_mapping:
            return role_mapping[role]

        # 尝试模糊匹配（映射表）
        for key, agent_id in role_mapping.items():
            if key in role or role in key:
                logger.info(f"Fuzzy matched role '{role}' to agent_id '{agent_id}'")
                return agent_id

        # DB 兜底：用 agent_reader 模糊搜索 name 或 description
        if self.agent_reader:
            try:
                all_agents = self.agent_reader.get_all_agents(is_enabled=True)
                role_lower = role.lower()
                for agent in all_agents:
                    name = (agent.get('name') or '').lower()
                    desc = (agent.get('description') or '').lower()
                    if role_lower in name or role_lower in desc:
                        aid = agent.get('agent_id', agent.get('id', ''))
                        if aid:
                            logger.info(f"DB fuzzy matched role '{role}' to agent_id '{aid}'")
                            return aid
            except Exception as e:
                logger.warning(f"DB fallback lookup failed for role '{role}': {e}")

        # 最终 fallback
        logger.warning(f"No agent_id mapping found for role '{role}', using fullstack-dhh as default")
        return 'fullstack-dhh'
