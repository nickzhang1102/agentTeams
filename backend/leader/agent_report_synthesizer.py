"""
Agent Report Synthesizer - 单 Agent 子任务结果综合器

所有子任务执行完毕后，收集原始结果，调用 LLM 以 Agent 角色视角
生成一份完整的专业分析报告（含标题、分析正文、结论与建议）。

与 ResultSummarizer（跨 Agent 综合）对称：
- ResultSummarizer：综合多个 Agent 的报告 → 最终报告
- AgentReportSynthesizer：综合一个 Agent 的多个子任务结果 → 单 Agent 报告

参见 .codestable/issues/2026-06-12-agent-report-quality/analysis.md 方案 C。
"""
import logging
from typing import Any, Dict, List, Optional

from context.evidence_context import EvidenceContextBuilder

from .task_types import SubTask
from .locale_generation import build_output_locale_instruction, resolve_generation_locale

logger = logging.getLogger(__name__)

# 子任务结果输入截断（字符数），防止过大输入占用上下文
# 需与模型上下文窗口匹配：15K 字符 ≈ 5K tokens，15 个子任务 ≈ 75K tokens
_SUBTASK_RESULT_CHAR_LIMIT = 15000

# Agent 报告是子任务结果的二次综合，不应使用模型理论最大输出上限。
# 某些 OpenAI 兼容网关会在超大 max_tokens 下长时间挂起直到客户端超时。
_AGENT_REPORT_MAX_TOKENS = 8192
_EVIDENCE_ITEM_LIMIT = 10
_EVIDENCE_ITEM_CHAR_LIMIT = 4000
_EVIDENCE_TOTAL_CHAR_LIMIT = 20000

_ENGLISH_AGENT_REPORT_RULE = """## Mandatory English report rule
Write the complete user-visible report in English (en-US), including the title, summary, headings,
analysis, findings, recommendations, and risk discussion. The role definition, prior task results,
and evidence below may be Chinese reference material; do not let their language determine the report.
Do not copy Chinese prose into the report narrative. Preserve machine fields, evidence IDs, URLs,
code, numbers, and necessary verbatim evidence quotes exactly as provided.
"""


class AgentReportSynthesizer:
    """单 Agent 子任务结果综合器"""

    def __init__(self, llm_service=None, locale: str = "zh-CN"):
        """初始化

        Args:
            llm_service: LLMService 实例
        """
        self._llm_service = llm_service
        self._locale = resolve_generation_locale(explicit_locale=locale)

    def set_llm_service(self, llm_service):
        """注入 LLM Service（延迟注入）"""
        self._llm_service = llm_service

    def synthesize(
        self,
        subtasks: List[SubTask],
        agent_name: str,
        agent_type: str,
        original_task: str,
        agent_system_prompt: str = "",
        evidence_map: Optional[List[Dict[str, Any]]] = None,
        raw_tool_results: Optional[Dict[str, Any]] = None,
    ) -> str:
        """综合所有子任务结果，生成完整专业报告

        Args:
            subtasks: 所有子任务（含 result）
            agent_name: Agent 名称
            agent_type: Agent 类型
            original_task: 原始任务描述
            agent_system_prompt: Agent 角色定义（Role/Persona/Core Expertise）
            evidence_map: 可引用证据的有界元数据与摘录
            raw_tool_results: 仅用于按 raw_ref 解析候选段落，不整体注入 prompt

        Returns:
            综合报告字符串；LLM 不可用时回退到文本拼接
        """
        completed = [s for s in subtasks if s.get("status") == "completed" and s.get("result")]
        if not completed:
            return "No execution results" if self._locale == "en-US" else "无执行结果"

        if not self._llm_service:
            logger.warning("AgentReportSynthesizer: no llm_service, falling back to safe report")
            return self._fallback_report(completed)

        max_tokens = self._get_report_max_tokens()
        prompt = self._build_prompt(
            completed,
            agent_name,
            agent_type,
            original_task,
            agent_system_prompt,
            evidence_map=evidence_map,
            raw_tool_results=raw_tool_results,
            output_token_budget=max_tokens,
        )

        # 使用 Agent 角色定义作为 system_prompt（优先级高于默认角色描述）
        effective_system_prompt = (
            agent_system_prompt
            if agent_system_prompt
            else self._build_system_prompt(agent_name, agent_type)
        )

        # 注入当前日期，防止 LLM 使用过时的训练数据日期
        from .node_utils import build_current_date_prompt
        effective_system_prompt = self._wrap_system_prompt(
            effective_system_prompt + build_current_date_prompt()
        )

        try:
            response = self._llm_service.call_sync(
                message=prompt,
                system_prompt=effective_system_prompt,
                max_tokens=max_tokens,
                max_attempts=1,
                reject_truncated=True,
            )
            content = response if isinstance(response, str) else response.get("content", "")
            if content and content.strip():
                logger.info(
                    f"AgentReportSynthesizer: synthesized report for '{agent_name}', "
                    f"{len(content)} chars"
                )
                return content
            else:
                logger.warning("AgentReportSynthesizer: LLM returned empty, falling back")
                return self._fallback_report(completed)
        except Exception as e:
            logger.error(f"AgentReportSynthesizer: LLM call failed: {e}, falling back")
            return self._fallback_report(completed)

    def _get_report_max_tokens(self) -> int:
        """获取 Agent 报告合成的输出预算。"""
        model_max_tokens = self._llm_service.get_max_output_tokens()
        report_max_tokens = min(model_max_tokens, _AGENT_REPORT_MAX_TOKENS)
        if report_max_tokens < model_max_tokens:
            logger.info(
                "AgentReportSynthesizer: capping max_tokens from %s to %s for report synthesis",
                model_max_tokens,
                report_max_tokens,
            )
        return report_max_tokens

    def _wrap_system_prompt(self, prompt: str) -> str:
        if self._locale != "en-US":
            return prompt + build_output_locale_instruction(self._locale, "agent_report")
        instruction = build_output_locale_instruction(self._locale, "agent_report")
        return f"{_ENGLISH_AGENT_REPORT_RULE}\n{prompt}\n{instruction}\n{_ENGLISH_AGENT_REPORT_RULE}"

    def _wrap_user_prompt(self, prompt: str) -> str:
        if self._locale != "en-US":
            return prompt
        return f"{_ENGLISH_AGENT_REPORT_RULE}\n{prompt}\n{_ENGLISH_AGENT_REPORT_RULE}"

    def _build_system_prompt(self, agent_name: str, agent_type: str) -> str:
        """构建 System Prompt（角色定位）"""
        if self._locale == "en-US":
            role_desc = f"You are {agent_name}"
            if agent_type:
                role_desc += f", a {agent_type} professional"
            return (
                f"{role_desc}. You have completed multiple research subtasks and must now write "
                "a complete analysis report from your professional perspective."
            )
        role_desc = f"你是「{agent_name}」"
        if agent_type:
            role_desc += f"，属于{agent_type}类型的专业人士"
        return f"{role_desc}。你已完成多项调研子任务，现在需要基于所有调研结果，以你的专业视角撰写一份完整的分析报告。报告应体现你的专业素养、深度分析能力和独到见解。"

    def _build_prompt(
        self,
        subtasks: List[SubTask],
        agent_name: str,
        agent_type: str,
        original_task: str,
        agent_system_prompt: str = "",
        evidence_map: Optional[List[Dict[str, Any]]] = None,
        raw_tool_results: Optional[Dict[str, Any]] = None,
        output_token_budget: int = _AGENT_REPORT_MAX_TOKENS,
    ) -> str:
        """构建角色中心的综合分析 Prompt"""
        # 组装子任务结果
        results_text = ""
        for i, st in enumerate(subtasks, 1):
            result = st.get("result", "")
            # 保留合理长度（与模型上下文窗口匹配）
            if len(result) > _SUBTASK_RESULT_CHAR_LIMIT:
                result = result[:_SUBTASK_RESULT_CHAR_LIMIT] + "...(已截断)"
            results_text += f"\n### 子任务 {i}：{st['goal']}\n{result}\n"

        evidence_text = self._build_evidence_text(
            evidence_map or [], raw_tool_results=raw_tool_results
        )
        evidence_requirements = (
            "\n9. **证据引用**——凡是由证据支持的关键事实或结论，必须在对应句末使用 "
            "`[evidence_id:实际ID]`；只能引用下方提供的 ID，不得杜撰。\n"
            if evidence_text
            else "\n9. **证据边界**——当前没有可引用证据，不得虚构 evidence_id。\n"
        )

        # 角色中心 Prompt：以角色身份驱动报告生成
        if agent_system_prompt:
            prompt = f"""你是「{agent_name}」，已经以你的专业视角完成了以下调研子任务。
现在请你基于这些调研结果，撰写一份能体现你专业素养的最终分析报告。

## 原始需求
{original_task}

## 你的调研结果
{results_text}

{evidence_text}

## 报告要求

1. **角色第一**——报告的分析框架、关注重点、语言风格必须符合你的专业身份
2. **只写你专业范畴内的分析**——不属于你职责的内容标注"需咨询XX专家"，不要越界泛泛而谈
3. **结构**：
   - 报告标题（体现你的分析视角）
   - 一句话摘要（只用一句话概括本报告的核心内容，不要写成建议、发现或风险清单）
   - 你的分析范围（简要说明你从什么角度切入）
   - 核心分析（你专业视角的深度分析，分主题展开）
   - 关键发现（你的专业判断，不是简单罗列数据）
   - 你的建议（基于你角色能力可给出的建议，不必面面俱到）
   - 超出你专业范围的部分（需要其他角色补充什么）

4. **不要复述调研过程**——直接给出你的专业分析和判断
5. **不要附加原始子任务结果或工具摘要**——报告末尾不要出现"子任务摘要"、"工具结果"、"工具调用摘要"等中间过程内容
6. **摘要边界**——一句话摘要只说明"这份报告主要得出什么判断/覆盖什么内容"；关键发现、建议、风险必须放在对应章节
7. **禁止开场白**——不要输出"好的"、"遵照您的指示"、"作为一名..."、"我已经审阅..."、"以下是..."等确认式或角色扮演式开头；第一行必须直接进入报告标题
8. **Markdown 格式，详尽充实**{evidence_requirements}"""
        else:
            prompt = f"""请综合以下调研结果，撰写一份完整的分析报告。

## 原始需求
{original_task}

## 调研结果
{results_text}

{evidence_text}

## 报告要求
1. 结构完整：报告标题、一句话摘要、概述、核心分析、关键发现、结论建议、风险提示
2. 不要简单罗列，要整合分析
3. 不要附加原始子任务结果或工具摘要；只输出最终分析报告正文
4. 一句话摘要只概括本报告的核心内容，不要写成建议、发现或风险清单
5. 禁止开场白；不要输出"好的"、"遵照您的指示"、"作为一名..."、"我已经审阅..."、"以下是..."等确认式或角色扮演式开头，第一行必须直接进入报告标题
6. Markdown 格式，详尽充实
7. 有证据支撑的事实或结论必须在对应句末使用 `[evidence_id:实际ID]`；只能引用上方提供的 ID，不得杜撰"""

        if self._locale == "en-US":
            safe_units = max(400, int(output_token_budget * 0.45))
            completion_requirement = (
                f"\n10. **Completion boundary** — keep the complete report within approximately "
                f"{safe_units} effective words. Finish every section and never stop mid-sentence.\n"
            )
        else:
            safe_units = max(600, int(output_token_budget * 0.65))
            completion_requirement = (
                f"\n10. **完整性边界**——完整报告控制在约 {safe_units} 个有效字符以内；"
                "必须收束所有章节，绝不能停在半句话或未完成的列表中。\n"
            )
        return self._wrap_user_prompt(prompt + completion_requirement)

    @staticmethod
    def _build_evidence_text(
        evidence_map: List[Dict[str, Any]],
        raw_tool_results: Optional[Dict[str, Any]] = None,
    ) -> str:
        """构建受统一预算约束的证据段落，供 Agent 报告引用。"""
        selection = EvidenceContextBuilder(
            total_char_budget=_EVIDENCE_TOTAL_CHAR_LIMIT,
            item_char_budget=_EVIDENCE_ITEM_CHAR_LIMIT,
            item_limit=_EVIDENCE_ITEM_LIMIT,
        ).build(evidence_map, raw_tool_results=raw_tool_results)
        if not selection.text:
            return ""
        return "## 可引用证据（相关段落）\n" + selection.text

    def _fallback_report(self, subtasks: List[SubTask]) -> str:
        """降级方案：不暴露子任务中间摘要的可见报告。"""
        if self._locale == "en-US":
            goals = "\n".join(f"- {st.get('goal', 'Unnamed subtask')}" for st in subtasks)
            return (
                "## Agent Report Generation Failed\n\n"
                "The Agent completed its subtasks, but the report synthesis service is temporarily unavailable. "
                "A complete analysis report could not be generated.\n\n"
                "### Completed Subtasks\n"
                f"{goals or '- None'}"
            )
        goals = "\n".join(f"- {st.get('goal', '未命名子任务')}" for st in subtasks)
        return (
            "## Agent 报告生成失败\n\n"
            "Agent 已完成子任务执行，但报告合成服务暂时不可用，无法生成完整分析报告。\n\n"
            "### 已完成子任务\n"
            f"{goals or '- 无'}"
        )
