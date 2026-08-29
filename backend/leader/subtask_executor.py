"""
SubTask Executor - 子任务执行器

执行单个子任务的工具链，按顺序调用工具并收集结果。

核心逻辑：
1. 按 subtask.tools 顺序调用工具
2. 每次工具调用通过 runtime 推送 SSE subtool_call
3. 收集结果后调用 LLM 生成分析报告
4. 推送 SSE subtask_completed

参见 feature-design 2026-06-10-agent-step-orchestration 第 2.2 节。
"""
import logging
import fnmatch
import hashlib
import time
from datetime import datetime, timezone
from typing import Callable, Dict, List, Any, Optional

from schemas.leader import ReportEvidence

from .task_types import SubTask, TaskDecomposition
from .locale_generation import build_output_locale_instruction, resolve_generation_locale

logger = logging.getLogger(__name__)

INTERNAL_ANALYSIS_TOOL = "llm_analysis"

# 工具名称映射：业务代码期望 -> OpenHarness 实际
TOOL_NAME_MAPPING = {
    'file_write': 'write_file',
    'file_read': 'read_file',
    'file_edit': 'edit_file',
}

# 默认工具超时（秒）
DEFAULT_TOOL_TIMEOUT = 30
# 默认工具重试次数
DEFAULT_TOOL_MAX_RETRIES = 1
# 工具结果输入截断（字符数），保留足够原始数据供 LLM 摘要
_TOOL_RESULT_CHAR_LIMIT = 100000
# LLM 摘要输出截断（字符数），精简报告体量
_SUMMARY_CHAR_LIMIT = 3000
# 子任务纯分析/摘要是中间结果，不应使用模型理论最大输出上限。
_LLM_ANALYSIS_MAX_TOKENS = 4096
_LLM_SUMMARY_MAX_TOKENS = 4096
_LLM_ANALYSIS_ROLE_CHAR_LIMIT = 4000
_RAW_TOOL_RESULT_CHAR_LIMIT = 15000
_EVIDENCE_EXCERPT_CHAR_LIMIT = 300
_STRUCTURED_EVIDENCE_ITEM_LIMIT = 10


class SubTaskExecutor:
    """子任务执行器"""

    def __init__(
        self,
        tool_registry=None,
        llm_service=None,
        tool_timeout: int = DEFAULT_TOOL_TIMEOUT,
        tool_max_retries: int = DEFAULT_TOOL_MAX_RETRIES,
        user_id: Optional[int] = None,
        allowed_tools: Optional[List[str]] = None,
        locale: str = "zh-CN",
        tool_event_callback: Optional[Callable] = None,
    ):
        """初始化子任务执行器

        Args:
            tool_registry: HarnessToolRegistry 或 ToolsRegistry 实例
            llm_service: LLMService 实例（用于无工具子任务的纯分析）
            tool_timeout: 工具执行超时秒数
            tool_max_retries: 工具失败重试次数
            user_id: 用户 ID（注入工具执行上下文）
            allowed_tools: Agent 工具白名单；None 表示未提供策略，空列表表示禁止外部工具
            tool_event_callback: 工具调用事件回调（started/completed），
                用于恢复 ToolCallLog 持久化与 tool_call_* SSE 事件
        """
        self._tool_registry = tool_registry
        self._llm_service = llm_service
        self._tool_timeout = tool_timeout
        self._tool_max_retries = tool_max_retries
        self._user_id = user_id
        self._allowed_tools = list(allowed_tools) if allowed_tools is not None else None
        self._locale = resolve_generation_locale(explicit_locale=locale)
        self._tool_event_callback = tool_event_callback

    def _fire_tool_event(
        self,
        event_type: str,
        agent_name: Optional[str],
        tool_name: str,
        tool_input=None,
        output_summary=None,
        is_error: bool = False,
    ) -> None:
        """触发工具调用事件回调（线程池 worker 中调用；回调自身需线程安全）。"""
        callback = self._tool_event_callback
        if callback is None:
            return
        # 与 execution_nodes._on_agent_event 的 DB 侧 [:500] 截断对齐，
        # 避免大输出工具把整段结果塞进 SSE 事件
        if output_summary:
            output_summary = str(output_summary)[:500]
        try:
            callback({
                "type": event_type,
                "agent_id": agent_name,
                "agent_name": agent_name,
                "tool_name": tool_name,
                "tool_input": tool_input,
                "tool_output_summary": output_summary,
                "is_error": is_error,
            })
        except Exception:
            logger.debug("tool_event_callback error", exc_info=True)

    def set_tool_registry(self, tool_registry):
        """注入 Tool Registry（延迟注入）"""
        self._tool_registry = tool_registry

    def set_llm_service(self, llm_service):
        """注入 LLM Service（延迟注入）"""
        self._llm_service = llm_service

    def execute_subtask(
        self,
        subtask: SubTask,
        runtime: Any,
        task_context: str,
        session_id: int,
        agent_name: str = "",
        agent_type: str = "",
        agent_system_prompt: str = "",
        allowed_tools: Optional[List[str]] = None,
    ) -> SubTask:
        """执行单个子任务

        Args:
            subtask: 子任务定义
            runtime: TaskRuntime 实例（用于 SSE 推送）
            task_context: 任务上下文（原始任务 + 前置输出）
            session_id: LeaderSession ID
            agent_name: Agent 名称（用于 LLM 汇总分析的视角）
            agent_type: Agent 类型（用于 LLM 汇总分析的视角）
            agent_system_prompt: Agent 角色定义（Role/Persona/Core Expertise）
            allowed_tools: 本次 Agent 工具白名单；提供时覆盖构造参数

        Returns:
            更新后的 SubTask（包含执行结果）
        """
        start_time = time.time()
        subtask_id = subtask["id"]
        goal = subtask["goal"]
        tools = subtask.get("tools", [])
        normalized_tools = [tool for tool in tools if tool != INTERNAL_ANALYSIS_TOOL]

        logger.info(f"SubTaskExecutor: starting {subtask_id}, goal={goal}, tools={tools}")

        # 标记为 running
        subtask["status"] = "running"

        # 推送 SSE subtask_started
        if runtime:
            runtime.emit_subtask_started(subtask)

        # 执行工具链或纯分析
        results = []
        if tools:
            for tool_name in tools:
                if tool_name == INTERNAL_ANALYSIS_TOOL:
                    if runtime:
                        runtime.emit_subtool_call(subtask_id, INTERNAL_ANALYSIS_TOOL, {"goal": goal})

                    result = self._execute_llm_analysis(subtask, task_context, agent_system_prompt, agent_name)
                    self._attach_evidence(subtask, result, INTERNAL_ANALYSIS_TOOL)
                    results.append(result)

                    if runtime and result.get("success"):
                        runtime.emit_subtask_result(
                            subtask_id,
                            result.get("result", ""),
                            self._last_evidence(subtask),
                        )
                    continue

                # 按 user_id 粒度跳过无知识库的 knowledge_search
                if tool_name == "knowledge_search" and not self._is_knowledge_available_for_user():
                    logger.info(f"SubTaskExecutor: skipping knowledge_search for user_id={self._user_id} (no knowledge graph)")
                    continue

                # 推送 SSE subtool_call
                tool_input = self._build_tool_input(subtask, task_context, tool_name, session_id=session_id, agent_id=agent_name)
                if runtime:
                    runtime.emit_subtool_call(subtask_id, tool_name, tool_input)

                self._fire_tool_event("tool_call_started", agent_name, tool_name, tool_input=tool_input)

                # 执行工具（含重试）
                result = self._execute_single_tool_with_retry(
                    tool_name,
                    subtask,
                    task_context,
                    session_id=session_id,
                    agent_id=agent_name,
                    allowed_tools=allowed_tools,
                )

                self._fire_tool_event(
                    "tool_call_completed",
                    agent_name,
                    tool_name,
                    output_summary=str(result.get("result", "")) if result.get("success") else None,
                    is_error=not result.get("success"),
                )
                self._attach_evidence(subtask, result, tool_name)
                results.append(result)

                # 推送 SSE subtask_result
                if runtime and result.get("success"):
                    runtime.emit_subtask_result(
                        subtask_id,
                        result.get("result", ""),
                        self._last_evidence(subtask),
                    )

                # 工具失败时记录错误（重试后仍然失败）
                if not result.get("success"):
                    logger.warning(
                        f"SubTaskExecutor: tool {tool_name} failed after retries: {result.get('error')}"
                    )
                    # 继续执行下一个工具（不中断）
        else:
            # 无工具：纯分析子任务，调用 LLM
            if runtime:
                runtime.emit_subtool_call(subtask_id, INTERNAL_ANALYSIS_TOOL, {"goal": goal})

            result = self._execute_llm_analysis(subtask, task_context, agent_system_prompt, agent_name)
            self._attach_evidence(subtask, result, INTERNAL_ANALYSIS_TOOL)
            results.append(result)

            if runtime and result.get("success"):
                runtime.emit_subtask_result(
                    subtask_id,
                    result.get("result", ""),
                    self._last_evidence(subtask),
                )

        # 单个短结果已经可直接消费；多结果或超长结果才调用 LLM 摘要。
        has_successful_result = any(r.get("success") for r in results)
        if has_successful_result:
            successful_results = [r for r in results if r.get("success")]
            failed_results = [r for r in results if not r.get("success")]
            only_result = successful_results[0] if len(successful_results) == 1 else None
            only_text = str(only_result.get("result", "")) if only_result else ""
            if only_result and not failed_results and len(only_text) <= _SUMMARY_CHAR_LIMIT:
                subtask["result"] = only_text
            else:
                subtask["result"] = self._summarize_with_llm(results, goal)
            subtask["status"] = "completed"
        else:
            # 全部失败：标记跳过，不产出无意义内容
            subtask["result"] = ""
            subtask["status"] = "skipped"

        # 推送 SSE subtask_completed
        if runtime:
            runtime.emit_subtask_completed(subtask)

        logger.info(
            f"SubTaskExecutor: completed {subtask_id}, "
            f"tools_count={len(tools)}, "
            f"took={time.time() - start_time:.2f}s"
        )

        return subtask

    def _attach_evidence(self, subtask: SubTask, result: Dict, tool_name: str) -> None:
        """Attach evidence metadata and bounded raw tool result to a subtask."""
        evidence_map = subtask.setdefault("evidence_map", [])
        raw_tool_results = subtask.setdefault("raw_tool_results", {})
        metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
        candidates = metadata.get("evidence_items") if isinstance(metadata, dict) else None

        attached_ids = []
        if result.get("success") and isinstance(candidates, list):
            for candidate in candidates[:_STRUCTURED_EVIDENCE_ITEM_LIMIT]:
                evidence_id = self._attach_candidate_evidence(
                    subtask,
                    candidate,
                    tool_name,
                    evidence_map,
                    raw_tool_results,
                )
                if evidence_id:
                    attached_ids.append(evidence_id)
        if attached_ids:
            result["evidence_id"] = attached_ids[0]
            result["evidence_ids"] = attached_ids
            return

        evidence_id = self._make_evidence_id(subtask["id"], tool_name, len(evidence_map) + 1)
        raw_value = result.get("result") or result.get("error") or ""
        raw_text = str(raw_value)
        raw_tool_results[evidence_id] = {
            "tool_name": tool_name,
            "success": bool(result.get("success")),
            "result": self._truncate(raw_text, _RAW_TOOL_RESULT_CHAR_LIMIT),
            "error": result.get("error"),
        }
        is_internal_analysis = result.get("source_type") == INTERNAL_ANALYSIS_TOOL
        evidence = ReportEvidence(
            schema_version=1,
            evidence_id=evidence_id,
            source_type="subtask_result" if is_internal_analysis else "tool_result",
            source_id=tool_name,
            title=(
                f"子任务分析: {subtask['goal']}"
                if is_internal_analysis
                else f"{tool_name}: {subtask['goal']}"
            ),
            excerpt=self._truncate(raw_text, _EVIDENCE_EXCERPT_CHAR_LIMIT),
            raw_ref=f"raw_tool_results.{evidence_id}",
            completeness="legacy",
            agent_id=None,
            subtask_id=subtask["id"],
            created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )
        evidence_map.append(evidence.model_dump())
        result["evidence_id"] = evidence_id

    def _attach_candidate_evidence(
        self,
        subtask: SubTask,
        candidate: Any,
        tool_name: str,
        evidence_map: List[Dict],
        raw_tool_results: Dict,
    ) -> Optional[str]:
        if not isinstance(candidate, dict):
            return None
        passage = str(candidate.get("passage") or candidate.get("excerpt") or "").strip()
        if not passage:
            return None

        evidence_id = self._make_evidence_id(
            subtask["id"], tool_name, len(evidence_map) + 1
        )
        passage = self._truncate(passage, _RAW_TOOL_RESULT_CHAR_LIMIT)
        excerpt = self._truncate(
            str(candidate.get("excerpt") or passage),
            _EVIDENCE_EXCERPT_CHAR_LIMIT,
        )
        content_hash = str(candidate.get("content_hash") or "").strip()
        if not content_hash:
            content_hash = hashlib.sha256(passage.encode("utf-8")).hexdigest()

        raw_tool_results[evidence_id] = {
            "tool_name": tool_name,
            "success": True,
            "result": passage,
            "passage": passage,
            "error": None,
        }
        source_type = str(candidate.get("source_type") or "tool_result")
        if source_type not in {"web", "knowledge", "memory", "user_input", "tool_result"}:
            source_type = "tool_result"
        locator = candidate.get("locator")
        if not isinstance(locator, dict):
            locator = {}

        evidence = ReportEvidence(
            schema_version=2,
            evidence_id=evidence_id,
            source_type=source_type,
            source_id=candidate.get("source_id") or tool_name,
            title=str(candidate.get("title") or f"{tool_name}: {subtask['goal']}"),
            excerpt=excerpt,
            raw_ref=f"raw_tool_results.{evidence_id}",
            url=candidate.get("url"),
            provider=candidate.get("provider"),
            locator=locator,
            rank=self._optional_int(candidate.get("rank")),
            relevance_score=self._optional_float(candidate.get("relevance_score")),
            content_hash=content_hash,
            source_version=candidate.get("source_version"),
            completeness=self._normalize_completeness(candidate.get("completeness")),
            agent_id=None,
            subtask_id=subtask["id"],
            created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )
        evidence_map.append(evidence.model_dump())
        return evidence_id

    @staticmethod
    def _last_evidence(subtask: SubTask) -> Optional[Dict]:
        evidence_map = subtask.get("evidence_map", []) or []
        if not evidence_map:
            return None
        last = evidence_map[-1]
        return {
            "evidence_id": last.get("evidence_id"),
            "title": last.get("title"),
            "excerpt": last.get("excerpt"),
            "source_type": last.get("source_type"),
            "source_id": last.get("source_id"),
        }

    @staticmethod
    def _make_evidence_id(subtask_id: str, tool_name: str, index: int) -> str:
        safe_subtask = "".join(ch if ch.isalnum() else "_" for ch in subtask_id.lower())
        safe_tool = "".join(ch if ch.isalnum() else "_" for ch in tool_name.lower())
        return f"ev_{safe_subtask}_{safe_tool}_{index}"

    @staticmethod
    def _truncate(text: str, limit: int) -> str:
        if not text or len(text) <= limit:
            return text or ""
        return text[:limit] + "...(已截断)"

    @staticmethod
    def _optional_int(value: Any) -> Optional[int]:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _optional_float(value: Any) -> Optional[float]:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _normalize_completeness(value: Any) -> str:
        normalized = str(value or "snippet").strip().lower()
        if normalized in {"passage", "snippet", "legacy", "unavailable"}:
            return normalized
        return "snippet"

    def _execute_single_tool_with_retry(
        self,
        tool_name: str,
        subtask: SubTask,
        task_context: str,
        session_id: Optional[int] = None,
        agent_id: Optional[str] = None,
        allowed_tools: Optional[List[str]] = None,
    ) -> Dict:
        """执行单个工具（含重试）

        Args:
            tool_name: 工具名称
            subtask: 子任务定义
            task_context: 任务上下文
            session_id: LeaderSession ID（用于 file_write 沙箱隔离）
            agent_id: Agent ID（用于 file_write 沙箱隔离）

        Returns:
            执行结果 {success, result, error}
        """
        last_error = None
        for attempt in range(self._tool_max_retries + 1):
            if attempt > 0:
                logger.info(f"SubTaskExecutor: retrying tool {tool_name}, attempt {attempt + 1}")
            result = self._execute_single_tool(
                tool_name,
                subtask,
                task_context,
                session_id=session_id,
                agent_id=agent_id,
                allowed_tools=allowed_tools,
            )
            if result.get("success"):
                return result
            last_error = result
            # 工具未找到不重试
            if "not found" in result.get("error", "").lower():
                break

        return last_error or {"success": False, "error": "Tool execution failed after retries"}

    def _execute_single_tool(
        self,
        tool_name: str,
        subtask: SubTask,
        task_context: str,
        session_id: Optional[int] = None,
        agent_id: Optional[str] = None,
        allowed_tools: Optional[List[str]] = None,
    ) -> Dict:
        """执行单个工具

        Args:
            tool_name: 工具名称
            subtask: 子任务定义
            task_context: 任务上下文
            session_id: LeaderSession ID（用于 file_write 沙箱隔离）
            agent_id: Agent ID（用于 file_write 沙箱隔离）

        Returns:
            执行结果 {success, result, error}
        """
        if not self._tool_registry:
            logger.warning(f"SubTaskExecutor: no tool_registry, skipping {tool_name}")
            return {"success": False, "error": "Tool registry not initialized"}

        if not self._is_tool_allowed(tool_name, allowed_tools):
            logger.warning("SubTaskExecutor: tool %s is not allowed for this agent", tool_name)
            return {"success": False, "error": f"Tool '{tool_name}' is not allowed for this agent"}

        # 构建工具输入
        tool_input = self._build_tool_input(subtask, task_context, tool_name, session_id=session_id, agent_id=agent_id)

        # 如果构建输入失败（返回 None），跳过此工具
        if tool_input is None:
            logger.warning(f"SubTaskExecutor: skipping tool {tool_name} due to invalid input")
            return {"success": False, "error": f"Cannot build valid input for {tool_name}"}

        # 工具名称映射转换
        mapped_tool_name = TOOL_NAME_MAPPING.get(tool_name, tool_name)
        if mapped_tool_name != tool_name:
            logger.debug(f"SubTaskExecutor: mapped tool name {tool_name} -> {mapped_tool_name}")

        # 执行工具（传递超时参数和 user_id）
        try:
            tool_metadata = {}
            if self._user_id is not None:
                tool_metadata['user_id'] = self._user_id
            result = self._tool_registry.execute_tool(
                mapped_tool_name, tool_input, timeout=self._tool_timeout, metadata=tool_metadata
            )
            return result
        except Exception as e:
            logger.error(f"SubTaskExecutor: tool {tool_name} exception: {e}")
            return {"success": False, "error": str(e)}

    def _is_tool_allowed(
        self,
        tool_name: str,
        allowed_tools: Optional[List[str]] = None,
    ) -> bool:
        """在最终执行边界校验白名单，兼容通配符和业务工具别名。"""
        patterns = self._allowed_tools if allowed_tools is None else allowed_tools
        if patterns is None:
            return True
        mapped_tool_name = TOOL_NAME_MAPPING.get(tool_name, tool_name)
        candidates = (tool_name, mapped_tool_name)
        return any(
            fnmatch.fnmatch(candidate, pattern)
            for candidate in candidates
            for pattern in patterns
        )

    def _execute_llm_analysis(
        self,
        subtask: SubTask,
        task_context: str,
        agent_system_prompt: str = "",
        agent_name: str = "",
    ) -> Dict:
        """纯分析子任务：调用 LLM

        Args:
            subtask: 子任务定义
            task_context: 任务上下文
            agent_system_prompt: Agent 角色定义

        Returns:
            分析结果 {success, result, error}
        """
        if not self._llm_service:
            logger.warning("SubTaskExecutor: no llm_service, skipping analysis")
            return {"success": False, "error": "LLM service not initialized"}

        goal = subtask["goal"]

        agent_system_prompt = self._truncate_context(agent_system_prompt, _LLM_ANALYSIS_ROLE_CHAR_LIMIT)

        # 角色中心 Prompt：角色决定分析方式
        if agent_system_prompt:
            prompt = f"""你是「{agent_name if agent_name else '专业分析师'}」，以下是你的角色定义：
{agent_system_prompt}

---

## 你需要分析的目标
{goal}

## 任务上下文
{task_context}

请严格从你的专业视角分析，用你的角色语言和方法论给出判断。
只分析你专业范畴内的内容，不属于你职责的部分标注"需咨询其他专家"。"""
        else:
            prompt = f"""请分析以下任务：

## 任务上下文
{task_context}

## 分析目标
{goal}

请提供简洁的分析结果，不要展开太多细节。"""

        try:
            # 语言约束必须位于角色、模板附加提示和日期提示之后。
            from .node_utils import build_current_date_prompt
            system_prompt = (agent_system_prompt or "") + build_current_date_prompt()
            system_prompt += build_output_locale_instruction(self._locale, "agent_report")
            response = self._llm_service.call_sync(
                message=prompt,
                system_prompt=system_prompt,
                max_tokens=self._get_llm_budget(_LLM_ANALYSIS_MAX_TOKENS),
                max_attempts=1,
                empty_content_ok=True,
            )
            content = response if isinstance(response, str) else response.get("content", "")

            if not content or not content.strip():
                logger.warning("SubTaskExecutor: LLM analysis returned empty content; marking subtask skipped")
                return {
                    "success": False,
                    "result": "",
                    "error": "LLM returned empty content",
                    "source_type": INTERNAL_ANALYSIS_TOOL,
                }

            return {"success": True, "result": content, "source_type": INTERNAL_ANALYSIS_TOOL}

        except Exception as e:
            logger.error(f"SubTaskExecutor: LLM analysis exception: {e}")
            error_prefix = (
                "LLM analysis timed out or failed: "
                if self._locale == "en-US"
                else "LLM 分析超时或失败："
            )
            return {"success": False, "result": "", "error": f"{error_prefix}{str(e)}"}

    def _build_tool_input(
        self,
        subtask: SubTask,
        task_context: str,
        tool_name: str,
        session_id: Optional[int] = None,
        agent_id: Optional[str] = None,
    ) -> Dict:
        """构建工具输入参数

        Args:
            subtask: 子任务定义
            task_context: 任务上下文
            tool_name: 工具名称
            session_id: LeaderSession ID（用于 file_write 沙箱隔离）
            agent_id: Agent ID（用于 file_write 沙箱隔离）

        Returns:
            工具输入参数字典
        """
        goal = subtask["goal"]

        # 根据工具类型构建输入
        if tool_name == "web_search":
            return {"query": goal}
        elif tool_name == "file_read":
            # file_read 需要文件路径，不能传入目录
            # 简单策略：从 goal 提取文件名，如无法提取则返回空结果
            # TODO: 更好的方案是让 LLM 生成文件路径
            import re
            match = re.search(r'`([^`]+\.(py|ts|js|jsx|tsx|md|txt|json|yaml|yml))`', goal)
            if match:
                path = match.group(1)
            else:
                # 如果无法提取文件路径，使用 glob 工具替代
                logger.warning(f"SubTaskExecutor: file_read requires file path, but goal '{goal}' has no clear file. Skipping.")
                return None  # 返回 None 表示跳过此工具
            return {"path": path}
        elif tool_name == "file_write":
            # 沙箱隔离：按 session/agent/subtask 生成唯一路径，防止并发覆盖和路径遍历
            output_path = self._build_sandboxed_output_path(session_id, agent_id, subtask.get("id", "unknown"))
            return {"path": output_path, "content": task_context}
        elif tool_name in ("grep", "search_files"):
            return {"pattern": goal, "root": "."}  # 修复：使用 root 而非 path
        elif tool_name == "glob":
            return {"pattern": "**/*", "root": "."}  # 修复：使用 root 而非 path
        elif tool_name == "knowledge_search":
            return {"query": goal}
        elif tool_name.startswith("mcp__"):
            return {"query": goal}
        else:
            return {"query": goal}

    @staticmethod
    def _build_sandboxed_output_path(
        session_id: Optional[int],
        agent_id: Optional[str],
        subtask_id: str,
    ) -> str:
        """构建沙箱隔离的输出文件路径

        路径格式: {WORKSPACE_DIR}/leader_output/session_{sid}/{agent_id}/{subtask_id}.md
        - 每个 session 独立目录，避免跨会话污染
        - 每个 agent 独立子目录，避免并发覆盖
        - 每个 subtask 独立文件，保留完整输出历史

        Args:
            session_id: LeaderSession ID
            agent_id: Agent ID
            subtask_id: 子任务 ID

        Returns:
            沙箱内的输出文件路径（绝对路径）
        """
        import os
        import re as _re

        try:
            from config import Config
            workspace = Config.WORKSPACE_DIR or "data/workspace"
        except Exception:
            workspace = "data/workspace"

        # 路径安全：仅保留字母数字下划线连字符
        safe_agent = _re.sub(r'[^a-zA-Z0-9_-]', '_', agent_id or "unknown")
        safe_subtask = _re.sub(r'[^a-zA-Z0-9_-]', '_', subtask_id or "output")

        output_dir = os.path.join(
            workspace, "leader_output",
            f"session_{session_id or 'unknown'}",
            safe_agent,
        )
        os.makedirs(output_dir, exist_ok=True)

        return os.path.join(output_dir, f"{safe_subtask}.md")

    def _is_knowledge_available_for_user(self) -> bool:
        """检查当前用户的知识图谱是否存在（按 user_id 粒度）。

        与 harness_coordinator._is_knowledge_available(user_id) 逻辑一致，
        但作为实例方法直接使用 self._user_id。
        """
        if self._user_id is None:
            return False
        try:
            from config import Config
            import os
            graph_path = Config.get_user_graph_path(self._user_id)
            return os.path.exists(graph_path) and os.path.getsize(graph_path) > 10
        except Exception:
            return False

    def _summarize_with_llm(
        self,
        results: List[Dict],
        goal: str,
    ) -> str:
        """调用 LLM 将工具结果形成摘要

        不注入角色定义和需求上下文，纯粹基于工具返回数据生成摘要。

        Args:
            results: 工具执行结果列表
            goal: 子任务目标

        Returns:
            摘要字符串（截断至 _SUMMARY_CHAR_LIMIT）
        """
        if not self._llm_service:
            logger.warning("SubTaskExecutor: no llm_service, returning raw results")
            return self._concat_raw_results(results)

        # 提取成功和失败结果
        successful = [r for r in results if r.get("success")]
        failed = [r for r in results if not r.get("success")]

        # 构建工具结果文本
        tool_results_text = ""
        for i, r in enumerate(successful, 1):
            result_text = r.get("result", "")
            if len(result_text) > _TOOL_RESULT_CHAR_LIMIT:
                result_text = result_text[:_TOOL_RESULT_CHAR_LIMIT] + "...(已截断)"
            tool_results_text += f"\n### 工具结果 {i}\n{result_text}\n"

        if failed:
            tool_results_text += "\n### 失败的工具\n"
            for r in failed:
                error_text = r.get('error', '未知错误')
                raw_output = r.get('result', '')
                if raw_output and raw_output.strip():
                    tool_results_text += f"- {error_text}（部分返回：{raw_output[:500]}）\n"
                else:
                    tool_results_text += f"- {error_text}\n"

        prompt = f"""基于以下工具调研结果，围绕目标直接输出摘要内容。
不要有任何开场白、过渡句或角色扮演式的开头，直接从正文开始。

## 目标
{goal}

## 工具调研结果
{tool_results_text}

## 要求
1. 提取关键信息，形成 3000 字以内的摘要
2. 不要简单罗列，要整合归纳
3. 使用 Markdown 格式
4. 如有数据矛盾或不确定性，明确指出"""

        try:
            system_prompt = (
                "你是数据摘要工具。禁止任何开场白、角色介绍或过渡语句，直接输出摘要正文。"
                + build_output_locale_instruction(self._locale, "agent_report")
            )
            response = self._llm_service.call_sync(
                message=prompt,
                system_prompt=system_prompt,
                max_tokens=self._get_llm_budget(_LLM_SUMMARY_MAX_TOKENS),
                max_attempts=1,
                empty_content_ok=True,
            )
            content = response if isinstance(response, str) else response.get("content", "")
            if content and content.strip():
                # 截断至摘要上限
                if len(content) > _SUMMARY_CHAR_LIMIT:
                    content = content[:_SUMMARY_CHAR_LIMIT] + "...(已截断)"
                logger.info(f"SubTaskExecutor: LLM summary generated, {len(content)} chars")
                return content
            else:
                logger.info("SubTaskExecutor: LLM returned empty, returning raw results")
                return self._concat_raw_results(results)
        except Exception as e:
            logger.error(f"SubTaskExecutor: LLM summary failed: {e}, returning raw results")
            return self._concat_raw_results(results)

    def _get_llm_budget(self, cap: int) -> int:
        """返回当前中间任务的输出预算。"""
        return min(self._llm_service.get_max_output_tokens(), cap)

    @staticmethod
    def _truncate_context(text: str, limit: int) -> str:
        """保留尾部上下文，避免每个纯分析子任务重复携带完整历史。"""
        if not text or len(text) <= limit:
            return text or ""
        return f"...(前文已截断，保留最近 {limit} 字符)\n{text[-limit:]}"

    def _concat_raw_results(self, results: List[Dict]) -> str:
        """LLM 不可用时直接拼接工具原始结果（截断至 _SUMMARY_CHAR_LIMIT）"""
        parts = []
        for r in results:
            if r.get("success"):
                parts.append(r.get("result", ""))
            else:
                if self._locale == "en-US":
                    parts.append(f"[Failed] {r.get('error', 'Unknown error')}")
                else:
                    parts.append(f"[失败] {r.get('error', '未知错误')}")
        text = "\n".join(parts)
        if len(text) > _SUMMARY_CHAR_LIMIT:
            text = text[:_SUMMARY_CHAR_LIMIT] + "...(已截断)"
        if text:
            return text
        return "No execution results" if self._locale == "en-US" else "无执行结果"
