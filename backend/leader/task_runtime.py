"""
Task Runtime - 任务运行时状态跟踪

跟踪任务执行状态，推送 SSE 事件，判断动态调整。

核心逻辑：
1. emit_* 方法：推送各类 SSE 事件
2. check_and_adjust：检查结果，判断是否需要调整
3. get_next_subtask：获取下一个待执行子任务
4. get_progress_summary：获取进度摘要

参见 feature-design 2026-06-10-agent-step-orchestration 第 2.2 节。
"""
import logging
import fnmatch
import re
import time
from typing import Dict, List, Optional, Any

from utils.async_utils import safe_async_run

from .task_types import (
    TaskDecomposition,
    SubTask,
    AdjustmentDecision,
    MAX_SUBTASKS,
)
from .sse_streamer import push_sse_event
from .locale_generation import build_output_locale_instruction, resolve_generation_locale
from schemas.leader import AdjustmentDecisionOutput

logger = logging.getLogger(__name__)

# URL 正则：匹配 http/https 链接
_URL_RE = re.compile(r'https?://\S+')


def _truncate_preserving_urls(text: str, max_len: int) -> str:
    """截断文本，但确保不切断 URL。

    若截断点落在 URL 内部，向前延伸至该 URL 末尾。
    """
    if len(text) <= max_len:
        return text
    truncated = text[:max_len]
    # 检查截断点是否在 URL 中间
    tail = text[max_len:]
    m = re.match(r'\S+', tail)
    if m:
        # 截断点后面紧接非空白字符 → 可能是被切断的 URL
        prefix = truncated.rsplit('\n', 1)[-1]  # 当前行
        if _URL_RE.search(prefix + m.group()):
            # 确认当前行含 URL 片段，延伸到该 token 末尾
            truncated += m.group()
    return truncated


# 动态调整判断 Prompt
ADJUSTMENT_PROMPT = """你是任务执行监控专家。请判断当前子任务执行结果是否需要调整计划。

## 子任务执行结果
{subtask_result}

## 当前计划状态
- 已完成子任务: {completed_count} 个
- 剩余子任务: {pending_count} 个
- 总子任务上限: {max_subtasks} 个

## 调整触发条件
1. **信息不足**：结果太短（<50字）或无实质内容 → 追加搜索子任务
2. **发现新问题**：结果暴露新需要 → 追加子任务解决新问题
3. **执行失败**：工具调用异常 → 替代方案或跳过

## 输出格式
请输出 JSON 格式的调整决策：
- action: continue（继续） | add_subtask（追加子任务） | modify_subtask（修改子任务） | skip（跳过当前）
- reason: 调整原因
- new_subtasks: 新增/修改的子任务列表（仅 add/modify 时提供）

## 约束
- 不允许终止整个 Agent 的既定子任务计划；即使发现高风险，也应 action=continue 并在 reason 说明风险
- 如果已完成子任务 ≥ {max_subtasks}，必须 action=continue
- 新增子任务总数不得超过上限
"""

_ADJUSTMENT_SIGNAL_MARKERS = (
    "信息不足", "缺少", "缺失", "无法确定", "不确定", "需补充", "需要补充",
    "冲突", "矛盾", "待验证", "未找到", "需要进一步", "insufficient",
    "missing", "uncertain", "conflict", "requires further",
)


class TaskRuntime:
    """任务运行时：状态跟踪 + 动态调整"""

    def __init__(
        self,
        session_id: int,
        decomposition: TaskDecomposition,
        llm_service=None,
        allowed_tools: Optional[List[str]] = None,
        locale: str = "zh-CN",
    ):
        """初始化任务运行时

        Args:
            session_id: LeaderSession ID
            decomposition: 任务分解计划
            llm_service: LLMService 实例（用于调整判断）
            allowed_tools: Agent 工具白名单；None 表示未提供策略，空列表表示禁止外部工具
        """
        self.session_id = session_id
        self.decomposition = decomposition
        self._llm_service = llm_service
        self.allowed_tools = list(allowed_tools) if allowed_tools is not None else None
        self._locale = resolve_generation_locale(explicit_locale=locale)
        self.completed_subtasks: List[str] = []
        self._start_time = time.time()

    def set_llm_service(self, llm_service):
        """注入 LLM Service（延迟注入）"""
        self._llm_service = llm_service

    def _localized(self, zh_text: str, en_text: str) -> str:
        return en_text if getattr(self, "_locale", "zh-CN") == "en-US" else zh_text

    def filter_tools(self, requested_tools: List[str]) -> List[str]:
        """按 Agent 白名单过滤规划或动态追加的工具。"""
        if self.allowed_tools is None:
            return list(requested_tools)
        return [
            tool
            for tool in requested_tools
            if any(fnmatch.fnmatch(tool, pattern) for pattern in self.allowed_tools)
        ]

    # ==================== SSE 推送方法 ====================

    def emit_decomposition(self) -> None:
        """推送任务分解事件"""
        event = {
            "type": "task_decomposition",
            "session_id": self.session_id,
            "agent_id": self.decomposition["agent_id"],
            "agent_name": self.decomposition["agent_name"],
            "subtasks": self.decomposition["subtasks"],
        }
        push_sse_event(self.session_id, event)
        logger.debug(f"TaskRuntime.emit_decomposition: {len(self.decomposition['subtasks'])} subtasks")

    def emit_subtask_started(self, subtask: SubTask) -> None:
        """推送子任务开始"""
        event = {
            "type": "subtask_started",
            "session_id": self.session_id,
            "agent_id": self.decomposition["agent_id"],
            "agent_name": self.decomposition["agent_name"],
            "subtask_id": subtask["id"],
            "goal": subtask["goal"],
            "tools": subtask.get("tools", []),
        }
        push_sse_event(self.session_id, event)
        logger.debug(f"TaskRuntime.emit_subtask_started: {subtask['id']}")

    def emit_subtool_call(
        self,
        subtask_id: str,
        tool_name: str,
        tool_input: Dict = None,
    ) -> None:
        """推送工具调用"""
        event = {
            "type": "subtool_call",
            "session_id": self.session_id,
            "agent_id": self.decomposition["agent_id"],
            "agent_name": self.decomposition["agent_name"],
            "subtask_id": subtask_id,
            "tool_name": tool_name,
            "tool_input": tool_input or {},
        }
        push_sse_event(self.session_id, event)
        logger.debug(f"TaskRuntime.emit_subtool_call: {subtask_id}/{tool_name}")

    def emit_subtask_result(
        self,
        subtask_id: str,
        result: str,
        evidence: Optional[Dict] = None,
    ) -> None:
        """推送子任务结果"""
        result_summary = _truncate_preserving_urls(result, 2000)
        event = {
            "type": "subtask_result",
            "session_id": self.session_id,
            "agent_id": self.decomposition["agent_id"],
            "agent_name": self.decomposition["agent_name"],
            "subtask_id": subtask_id,
            "result": result_summary,
        }
        if evidence:
            event["evidence"] = evidence
        push_sse_event(self.session_id, event)
        logger.debug(f"TaskRuntime.emit_subtask_result: {subtask_id} len={len(result)}")

    def emit_subtask_completed(self, subtask: SubTask) -> None:
        """推送子任务完成"""
        event = {
            "type": "subtask_completed",
            "session_id": self.session_id,
            "agent_id": self.decomposition["agent_id"],
            "agent_name": self.decomposition["agent_name"],
            "subtask_id": subtask["id"],
            "goal": subtask["goal"],
            "status": subtask["status"],
        }
        push_sse_event(self.session_id, event)

        # 更新已完成列表（completed 和 skipped 均视为已结束）
        if subtask["status"] in ("completed", "skipped"):
            self.completed_subtasks.append(subtask["id"])

        logger.debug(f"TaskRuntime.emit_subtask_completed: {subtask['id']} status={subtask['status']}")

    def emit_task_adjusted(
        self,
        action: str,
        reason: str,
        new_subtasks: List[SubTask],
    ) -> None:
        """推送任务调整"""
        event = {
            "type": "task_adjusted",
            "session_id": self.session_id,
            "agent_id": self.decomposition["agent_id"],
            "agent_name": self.decomposition["agent_name"],
            "action": action,
            "reason": reason,
            "new_subtasks": new_subtasks,
        }
        push_sse_event(self.session_id, event)
        logger.info(f"TaskRuntime.emit_task_adjusted: action={action}, reason={reason}")

    # ==================== 状态管理方法 ====================

    def get_next_subtask(self) -> Optional[SubTask]:
        """获取下一个待执行的子任务

        Returns:
            下一个 pending 状态的子任务，或 None
        """
        for subtask in self.decomposition["subtasks"]:
            if subtask["status"] == "pending":
                return subtask
        return None

    def get_progress_summary(self) -> Dict:
        """获取进度摘要（用于前端缩起状态）

        Returns:
            {
                currentSubtaskId,
                currentSubtaskGoal,
                completedCount,
                totalCount,
            }
        """
        subtasks = self.decomposition["subtasks"]
        completed = len([s for s in subtasks if s["status"] in ("completed", "skipped")])
        total = len(subtasks)
        current = self.get_next_subtask()

        return {
            "currentSubtaskId": current["id"] if current else None,
            "currentSubtaskGoal": current["goal"] if current else None,
            "completedCount": completed,
            "totalCount": total,
        }

    def get_all_results(self) -> str:
        """获取所有已完成子任务的汇总结果

        Returns:
            汇总结果字符串
        """
        results = []
        for subtask in self.decomposition["subtasks"]:
            if subtask["status"] == "completed" and subtask.get("result"):
                results.append(f"**{subtask['goal']}**\n{subtask['result']}")

        return "\n\n".join(results)

    # ==================== 动态调整方法 ====================

    def check_and_adjust(self, subtask_result: str) -> AdjustmentDecision:
        """检查执行结果，判断是否需要调整

        触发条件：
        - 信息不足：结果太短/无实质内容
        - 发现新问题：结果中暴露新需要
        - 执行失败：工具调用异常

        Args:
            subtask_result: 子任务执行结果

        Returns:
            AdjustmentDecision
        """
        # 检查是否已达上限（以已完成数为准，与 ADJUSTMENT_PROMPT 语义对齐）
        current_count = len(self.decomposition["subtasks"])
        completed_count = len(self.completed_subtasks)

        if current_count >= MAX_SUBTASKS:
            logger.info(f"TaskRuntime.check_and_adjust: max_subtasks reached ({current_count})")
            return {
                "action": "continue",
                "reason": self._localized(
                    f"已达到子任务上限 ({MAX_SUBTASKS})",
                    f"The subtask limit has been reached ({MAX_SUBTASKS})",
                ),
                "new_subtasks": [],
            }

        # 快速判断：结果包含明确的工具执行失败标记（避免误匹配正常文本中的 "error"）
        if "[失败]" in subtask_result or "Tool execution failed" in subtask_result:
            logger.info("TaskRuntime.check_and_adjust: execution failed, suggesting skip")
            return {
                "action": "skip",
                "reason": self._localized(
                    "子任务工具执行失败，跳过继续",
                    "The subtask tool failed; skip it and continue",
                ),
                "new_subtasks": [],
            }

        # 快速判断：结果太短（信息不足）
        if len(subtask_result.strip()) < 50:
            logger.info("TaskRuntime.check_and_adjust: result too short, adding search subtask")
            new_subtasks = [
                {
                    "id": f"subtask_{current_count + 1}",
                    "goal": self._localized("补充信息搜索", "Search for additional information"),
                    "tools": self.filter_tools(["web_search"]),
                    "status": "pending",
                    "result": "",
                    "added_dynamically": True,
                }
            ]
            # 快速路径也必须追加到 decomposition，否则 get_next_subtask 找不到
            for new_st in new_subtasks:
                self.decomposition["subtasks"].append(new_st)
            adjustment_reason = self._localized(
                "信息不足，追加搜索子任务",
                "The available information is insufficient; add a search subtask",
            )
            self.emit_task_adjusted("add_subtask", adjustment_reason, new_subtasks)
            return {
                "action": "add_subtask",
                "reason": adjustment_reason,
                "new_subtasks": new_subtasks,
            }

        # 只有结果明确暴露覆盖缺口或冲突时才进入昂贵的 LLM 调整判断。
        normalized_result = subtask_result.lower()
        if not any(marker.lower() in normalized_result for marker in _ADJUSTMENT_SIGNAL_MARKERS):
            return {
                "action": "continue",
                "reason": self._localized(
                    "结果未出现需要调整计划的明确信号",
                    "The result contains no clear signal that the plan needs adjustment",
                ),
                "new_subtasks": [],
            }

        return self._call_llm_adjust(subtask_result, completed_count)

    def _call_llm_adjust(
        self,
        subtask_result: str,
        completed_count: int,
    ) -> AdjustmentDecision:
        """调用 LLM 判断是否需要调整

        Args:
            subtask_result: 子任务结果
            completed_count: 已完成子任务数量

        Returns:
            AdjustmentDecision
        """
        if not self._llm_service:
            logger.warning("TaskRuntime: no llm_service, default to continue")
            return {
                "action": "continue",
                "reason": self._localized(
                    "无 LLM 服务，默认继续",
                    "No LLM service is available; continue by default",
                ),
                "new_subtasks": [],
            }

        prompt = ADJUSTMENT_PROMPT.format(
            subtask_result=subtask_result,
            completed_count=completed_count,
            pending_count=len(self.decomposition["subtasks"]) - completed_count,
            max_subtasks=MAX_SUBTASKS,
        )

        messages = [
            {
                "role": "system",
                "content": build_output_locale_instruction(
                    getattr(self, "_locale", "zh-CN"),
                    "agent_report",
                ),
            },
            {"role": "user", "content": prompt},
        ]

        try:
            output = safe_async_run(
                self._llm_service.call_structured(
                    messages=messages,
                    response_model=AdjustmentDecisionOutput,
                    temperature=0.1,  # 调整判断用低温度
                )
            )

            # 转换为 AdjustmentDecision
            available_slots = max(0, MAX_SUBTASKS - len(self.decomposition["subtasks"]))
            new_subtasks = [
                {
                    "id": st.id,
                    "goal": st.goal,
                    "tools": self.filter_tools(st.tools or []),
                    "status": "pending",
                    "result": "",
                    "added_dynamically": True,
                }
                for st in output.new_subtasks[:available_slots]
            ]

            decision = {
                "action": output.action,
                "reason": output.reason,
                "new_subtasks": new_subtasks,
            }

            if decision["action"] == "add_subtask" and not new_subtasks:
                decision = {
                    "action": "continue",
                    "reason": self._localized(
                        f"子任务数量已达到上限 ({MAX_SUBTASKS})",
                        f"The subtask limit has been reached ({MAX_SUBTASKS})",
                    ),
                    "new_subtasks": [],
                }

            # 兼容旧 Prompt / 旧模型行为：动态调整阶段不允许中途终止整条既定子任务链。
            if decision["action"] == "abort":
                logger.warning(
                    "TaskRuntime._call_llm_adjust returned legacy abort action; coercing to continue. "
                    f"reason={decision['reason']}"
                )
                decision = {
                    "action": "continue",
                    "reason": self._localized(
                        f"忽略中途终止建议，继续执行剩余子任务：{decision['reason']}",
                        f"Ignore the mid-run abort suggestion and continue the remaining subtasks: {decision['reason']}",
                    ),
                    "new_subtasks": [],
                }

            # 执行调整：更新 decomposition
            if decision["action"] == "add_subtask":
                for new_st in decision["new_subtasks"]:
                    self.decomposition["subtasks"].append(new_st)
                self.emit_task_adjusted(
                    decision["action"],
                    decision["reason"],
                    decision["new_subtasks"],
                )
            elif decision["action"] == "modify_subtask":
                for new_st in decision["new_subtasks"]:
                    # 查找并更新
                    for i, st in enumerate(self.decomposition["subtasks"]):
                        if st["id"] == new_st["id"]:
                            self.decomposition["subtasks"][i] = new_st
                self.emit_task_adjusted(
                    decision["action"],
                    decision["reason"],
                    decision["new_subtasks"],
                )

            return decision

        except Exception as e:
            logger.error(f"TaskRuntime._call_llm_adjust failed: {e}")
            return {
                "action": "continue",
                "reason": self._localized(
                    f"LLM 判断失败: {e}",
                    f"LLM adjustment evaluation failed: {e}",
                ),
                "new_subtasks": [],
            }
