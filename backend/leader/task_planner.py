"""
Task Planner - 任务分解器

根据 Agent 类型生成结构化任务分解计划。

核心逻辑：
1. 医疗类 Agent：直接规划（依赖内部专业知识）
2. 其他类 Agent：先探索后规划（先做探索性调用）
3. 串行编排：后置 Agent 根据前置输出规划

参见 feature-design 2026-06-10-agent-step-orchestration 第 2.2 节。
"""
import asyncio
import logging
import time
from typing import Dict, List, Optional, Any

from .task_types import (
    TaskDecomposition,
    SubTask,
    DecompositionResult,
    MAX_SUBTASKS,
    TOOL_CHAIN_TEMPLATES,
)
from .locale_generation import build_output_locale_instruction, resolve_generation_locale
from schemas.leader import TaskDecompositionOutput, StructuredSubTask

logger = logging.getLogger(__name__)


# 任务分解 Prompt（角色中心版）
# 设计原则：角色定义不是附加信息，而是决定"做什么、不做什么"的核心约束。
# 每个子任务必须体现该角色的专业视角、分析方法论和职责边界。
TASK_DECOMPOSITION_PROMPT = """{role_section}
## 用户需求
{task}

{context_section}
## 分解要求

1. **你只从自己的专业视角出发**——你的子任务必须体现你角色的核心能力，不要越界去做其他角色的事
2. **明确不做清单**——在 reasoning 中说明"作为该角色，我不会关注 X，因为这不属于我的专业范畴"
3. **每个子任务有明确的专业目标**——不是泛泛的"分析需求"，而是你这个角色会具体关注什么
4. **工具选择服从角色判断**——你的角色决定用什么工具，不要机械地按模板选工具
5. **子任务数量不超过 {max_subtasks} 个**，宁精勿滥
6. **如果已有前置 Agent 输出，利用但不重复**——前置 Agent 的专业结论作为你的输入，不要重复他们的工作

## 可用工具
- web_search: 搜索互联网获取信息
- file_write: 写入文件
- grep: 搜索文件内容
- glob: 查找文件
- bash: 执行命令
- knowledge_search: 搜索知识图谱
- mcp__*: MCP 工具（如 mcp__exa__web_search）

## 输出格式
JSON 格式的子任务列表，每个子任务包含：
- id: 子任务ID（如 subtask_1）
- goal: 子任务目标（体现你角色的专业视角）
- tools: 工具链
- reasoning: 为什么需要这个子任务 + 作为该角色你不会关注什么及原因
"""

# 无角色降级 Prompt
TASK_DECOMPOSITION_PROMPT_FALLBACK = """请将用户的任务分解为子任务列表。

## 用户需求
{task}

{context_section}
## 分解规则
1. 每个子任务必须有明确的目标和工具链
2. 子任务之间有逻辑顺序
3. 子任务数量不超过 {max_subtasks} 个

## 可用工具
- web_search, file_write, grep, glob, bash, knowledge_search, mcp__*

## 输出格式
JSON 格式的子任务列表，每个子任务包含：
- id, goal, tools, reasoning
"""


class TaskPlanner:
    """任务分解器"""

    def __init__(self, llm_service=None, locale: str = "zh-CN"):
        """初始化任务分解器

        Args:
            llm_service: LLMService 实例（用于 call_structured）
        """
        self._llm_service = llm_service
        self._locale = resolve_generation_locale(explicit_locale=locale)

    def set_llm_service(self, llm_service):
        """注入 LLM Service（延迟注入）"""
        self._llm_service = llm_service

    def decompose(
        self,
        agent_id: str,
        agent_name: str,
        task: str,
        context: str = "",
        available_tools: List[str] = None,
        agent_system_prompt: str = "",
    ) -> TaskDecomposition:
        """生成角色视角驱动的任务分解计划

        Args:
            agent_id: Agent ID
            agent_name: Agent 名称
            task: 原始任务描述
            context: 前置 Agent 输出（串行编排时）
            available_tools: Agent 可用的工具列表
            agent_system_prompt: Agent 角色定义（Role/Persona/Core Expertise）

        Returns:
            TaskDecomposition 结构化任务分解计划
        """
        start_time = time.time()

        # 构建上下文段落
        context_section = ""
        if context:
            context_section = f"## 前置 Agent 输出\n{context}\n"

        # 根据是否有角色定义选择 Prompt 模板
        if agent_system_prompt:
            # 角色中心模式：角色定义作为身份核心，决定"做什么、不做什么"
            role_section = (
                f"## 你是谁\n"
                f"你是「{agent_name}」。以下是你完整的职业角色定义——"
                f"它决定了你分析问题的方式、关注的重点、使用的工具和职责的边界。\n\n"
                f"{agent_system_prompt}\n"
            )
            prompt = TASK_DECOMPOSITION_PROMPT.format(
                role_section=role_section,
                task=task,
                context_section=context_section,
                max_subtasks=MAX_SUBTASKS,
            )
            logger.info(f"TaskPlanner: role-centric decomposition for '{agent_name}' ({len(agent_system_prompt)} chars role)")
        else:
            # 降级模式：无角色定义时的通用分解
            prompt = TASK_DECOMPOSITION_PROMPT_FALLBACK.format(
                task=task,
                context_section=context_section,
                max_subtasks=MAX_SUBTASKS,
            )
            logger.info(f"TaskPlanner: fallback decomposition for '{agent_name}' (no role)")

        messages = [
            {
                "role": "system",
                "content": build_output_locale_instruction(self._locale, "agent_report"),
            },
            {"role": "user", "content": prompt},
        ]

        # 调用 LLM 结构化输出
        decomposition = self._call_llm_decompose(messages, available_tools)

        # 转换为 TaskDecomposition
        result = self._build_task_decomposition(
            agent_id, agent_name, task, decomposition
        )

        logger.info(
            f"TaskPlanner.decompose: agent={agent_id}, "
            f"subtasks={len(result['subtasks'])}, "
            f"took={time.time() - start_time:.2f}s"
        )

        return result

    def _call_llm_decompose(
        self,
        messages: List[Dict],
        available_tools: List[str] = None,
    ) -> DecompositionResult:
        """调用 LLM 结构化输出分解结果

        Args:
            messages: 消息列表
            available_tools: 可用工具列表（用于过滤）

        Returns:
            DecompositionResult 或 fallback
        """
        if not self._llm_service:
            logger.warning("TaskPlanner: no LLMService, using fallback")
            return self._fallback_decompose(messages[-1].get("content", ""))

        try:
            # 异步调用转为同步
            output = asyncio.run(
                self._llm_service.call_structured(
                    messages=messages,
                    response_model=TaskDecompositionOutput,
                    temperature=0.3,  # 分解任务允许稍高温度
                )
            )

            # 转换为 DecompositionResult
            subtasks = [
                {
                    "id": st.id,
                    "goal": st.goal,
                    "tools": self._filter_tools(st.tools or [], available_tools),
                    "reasoning": st.reasoning or "",
                }
                for st in output.subtasks
            ]
            if len(subtasks) > MAX_SUBTASKS:
                logger.warning(
                    "TaskPlanner: truncating %s planned subtasks to hard limit %s",
                    len(subtasks),
                    MAX_SUBTASKS,
                )
            return {
                "subtasks": subtasks[:MAX_SUBTASKS],
                "reasoning": output.reasoning,
            }

        except Exception as e:
            logger.error(f"TaskPlanner._call_llm_decompose failed: {e}")
            return self._fallback_decompose(messages[-1].get("content", ""))

    def _filter_tools(
        self,
        requested_tools: List[str],
        available_tools: List[str] = None,
    ) -> List[str]:
        """过滤工具：仅保留可用工具

        Args:
            requested_tools: 请求的工具列表
            available_tools: 可用工具列表（None 表示全部可用）

        Returns:
            过滤后的工具列表
        """
        if available_tools is None:
            return requested_tools

        # 支持通配符匹配（如 mcp__exa__*）
        import fnmatch

        filtered = []
        for tool in requested_tools:
            if any(fnmatch.fnmatch(tool, pattern) for pattern in available_tools):
                filtered.append(tool)

        return filtered

    def _fallback_decompose(self, task: str) -> DecompositionResult:
        """分解失败时的 fallback：单子任务

        Args:
            task: 任务描述

        Returns:
            单子任务的 DecompositionResult
        """
        is_english = self._locale == "en-US"
        return {
            "subtasks": [
                {
                    "id": "subtask_1",
                    "goal": "Analyze the user request" if is_english else "分析用户需求",
                    "tools": [],
                    "reasoning": (
                        "Task decomposition failed; using the default analysis task"
                        if is_english else
                        "LLM 分解失败，使用默认分析任务"
                    ),
                }
            ],
            "reasoning": "Decomposition failed; using fallback" if is_english else "分解失败，使用 fallback",
            "degraded": True,
            "degradation_reason": (
                "The task decomposition model failed; a generic single-task fallback was used."
                if is_english else
                "任务分解模型失败，已使用通用单任务降级方案"
            ),
        }

    def _build_task_decomposition(
        self,
        agent_id: str,
        agent_name: str,
        task: str,
        decomposition: DecompositionResult,
    ) -> TaskDecomposition:
        """构建 TaskDecomposition 对象

        Args:
            agent_id: Agent ID
            agent_name: Agent 名称
            task: 原始任务
            decomposition: LLM 输出的分解结果

        Returns:
            TaskDecomposition
        """
        # 转换 subtasks 为完整 SubTask 格式
        subtasks: List[SubTask] = []
        source_subtasks = decomposition.get("subtasks", [])[:MAX_SUBTASKS]
        for i, st in enumerate(source_subtasks):
            subtasks.append({
                "id": st.get("id", f"subtask_{i + 1}"),
                "goal": st.get("goal", f"子任务 {i + 1}"),
                "tools": st.get("tools", []),
                "status": "pending",
                "result": "",
                "added_dynamically": False,
            })

        # 确保有至少一个子任务
        if not subtasks:
            subtasks.append({
                "id": "subtask_1",
                "goal": "分析用户需求",
                "tools": [],
                "status": "pending",
                "result": "",
                "added_dynamically": False,
            })

        # 确定 current_subtask_id
        current_subtask_id = subtasks[0]["id"] if subtasks else None

        result: TaskDecomposition = {
            "agent_id": agent_id,
            "agent_name": agent_name,
            "original_task": task,
            "subtasks": subtasks,
            "current_subtask_id": current_subtask_id,
        }
        if decomposition.get("degraded"):
            result["degraded"] = True
            result["degradation_reason"] = decomposition.get(
                "degradation_reason", "任务分解已降级"
            )
        return result
