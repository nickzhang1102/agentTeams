"""
Batch Executor

批次执行器：按 execution_batches 顺序执行 Agent（批次内并行、批次间顺序）

新增功能（2026-06-10-agent-step-orchestration）：
- 串行上下文传递：后置 Agent task 包含前置输出
- 任务编排集成：execute_batch_with_decomposition() 使用 TaskPlanner/SubTaskExecutor
"""
import hashlib
import logging
import os
import re
import time
import contextvars
from contextlib import nullcontext
from datetime import datetime, timezone
from typing import Dict, List, Optional, Callable, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

from context.evidence_context import EvidenceContextBuilder

from .execution_result import AgentExecutionResult
from .report_structures import build_agent_structured_report
from .task_types import MAX_SUBTASKS, TaskDecomposition, SubTask
from .sse_streamer import push_sse_event
from .locale_generation import (
    detect_content_locale,
    resolve_agent_display_name,
    resolve_generation_locale,
)

logger = logging.getLogger(__name__)

_BATCH_CONTEXT_FINDING_LIMIT = 4
_BATCH_CONTEXT_ITEM_CHAR_LIMIT = 500
_BATCH_CONTEXT_REPORT_EXCERPT_LIMIT = 1500
_BATCH_CONTEXT_EVIDENCE_LIMIT = 4
_BATCH_CONTEXT_EVIDENCE_EXCERPT_LIMIT = 400


class BatchExecutor:
    """批次执行器：按 execution_batches 顺序执行 Agent

    执行模式：
    - 批次内：ThreadPoolExecutor 并行执行（max_parallel 限制）
    - 批次间：循环顺序执行（等待上一批次完成）
    - 上下文传递：批次间传递前置 Agent 输出摘要

    中断机制：
    - 每批次前检查 stop_checker
    - 中断后不执行后续批次
    """

    def __init__(
        self,
        harness_coordinator: Any,
        max_parallel: int = 5,
        stop_checker: Optional[Callable[[], bool]] = None,
        llm_service: Any = None,
        tool_registry: Any = None,
        system_prompt_addition: Optional[str] = None,
        locale: str = "zh-CN",
    ):
        """初始化批次执行器

        Args:
            harness_coordinator: HarnessCoordinator 实例
            max_parallel: 批次内最大并行数
            stop_checker: 停止标志检查函数
            llm_service: LLMService 实例（任务编排用）
            tool_registry: ToolRegistry 实例（任务编排用）
            system_prompt_addition: 注入到 Agent system prompt 的额外内容
        """
        self.coordinator = harness_coordinator
        self.max_parallel = max_parallel
        self.stop_checker = stop_checker
        self._llm_service = llm_service
        self._tool_registry = tool_registry
        self._system_prompt_addition = system_prompt_addition
        self._locale = resolve_generation_locale(explicit_locale=locale)

    def set_llm_service(self, llm_service: Any) -> None:
        """注入 LLM Service（延迟注入）"""
        self._llm_service = llm_service

    def set_tool_registry(self, tool_registry: Any) -> None:
        """注入 Tool Registry（延迟注入）"""
        self._tool_registry = tool_registry

    def execute_batch(
        self,
        batch: Dict,
        task: str,
        history: List[Dict],
        batch_index: int,
        event_callback: Optional[Callable] = None,
        user_id: Optional[int] = None,
        session_id: Optional[int] = None,
        result_callback: Optional[Callable[[AgentExecutionResult], None]] = None,
    ) -> List[AgentExecutionResult]:
        """执行单个批次（批次内并行）

        Args:
            batch: {"priority": 40, "agents": ["检验科专家"]}
            task: 执行任务
            history: 对话历史
            batch_index: 批次索引
            event_callback: SSE 事件回调

        Returns:
            List[AgentExecutionResult]
        """
        agents = batch.get("agents", [])
        if not agents:
            return []

        # 检查停止标志
        if self.stop_checker and self.stop_checker():
            logger.info(f"Execution stopped before batch {batch_index}")
            return []

        results = []

        # 前置校验：过滤未注册的 Agent，避免异常中断整个批次
        valid_agents = []
        for agent_id in agents:
            if self.coordinator.get_agent_info(agent_id):
                valid_agents.append(agent_id)
            else:
                logger.warning(f"Agent '{agent_id}' not registered, skipping")
                # 记录为错误结果，确保结果列表完整
                result = self._error_result(agent_id, batch_index, f"Agent '{agent_id}' not registered")
                results.append(result)
                if result_callback:
                    result_callback(result)

        if not valid_agents:
            return results

        # 批次内并行执行（仅执行已注册的 Agent）
        # 捕获调用方 contextvars（NodeServices），在线程池 worker 中恢复，
        # 否则 worker 线程内 get_services() 拿不到服务实例（contextvars 不自动跨线程）。
        with ThreadPoolExecutor(max_workers=min(len(valid_agents), self.max_parallel)) as executor:
            futures = {
                self._submit_with_context(
                    executor,
                    self.coordinator.execute_agent,
                    agent_id,
                    task,
                    None,
                    history,
                    event_callback,
                    user_id,
                    self._llm_service,
                ): agent_id
                for agent_id in valid_agents
            }

            for future in as_completed(futures):
                agent_id = futures[future]
                try:
                    result = future.result()
                    result = self._normalize_result(result, agent_id, batch_index)
                    results.append(result)
                except Exception as e:
                    logger.error(f"Agent {agent_id} execution failed: {e}", exc_info=True)
                    result = self._error_result(agent_id, batch_index, str(e))
                    results.append(result)

                # 实时推送 agent 结果到前端（不等整个 execute_plan 返回）
                if session_id:
                    push_sse_event(session_id, self._build_result_event(result, session_id))
                if result_callback:
                    result_callback(result)

        return results

    def execute_plan(
        self,
        plan: Dict,
        task: str,
        history: List[Dict],
        event_callback: Optional[Callable] = None,
        session_id: Optional[int] = None,
        use_task_orchestration: bool = False,
        user_id: Optional[int] = None,
        initial_results: Optional[List[AgentExecutionResult]] = None,
        result_callback: Optional[Callable[[AgentExecutionResult], None]] = None,
    ) -> List[AgentExecutionResult]:
        """执行完整 DAG 计划（批次间顺序 + 上下文传递）

        Args:
            plan: DAGExecutionPlan
            task: 执行任务
            history: 对话历史
            event_callback: SSE 事件回调
            session_id: LeaderSession ID（任务编排用）
            use_task_orchestration: 是否使用任务编排模式

        Returns:
            List[AgentExecutionResult]（按执行顺序）
        """
        all_results = list(initial_results or [])
        new_results = []
        completed_agent_ids = {
            result.get("agent_id") for result in all_results if result.get("agent_id")
        }
        batches = plan.get("execution_batches", [])

        for batch_index, batch in enumerate(batches):
            # 每批次前检查停止
            if self.stop_checker and self.stop_checker():
                logger.info(f"Execution stopped at batch {batch_index}")
                break

            remaining_agents = [
                agent_id for agent_id in batch.get("agents", [])
                if agent_id not in completed_agent_ids
            ]
            if not remaining_agents:
                logger.info("Skipping fully persisted batch %s", batch_index)
                continue
            runnable_batch = {**batch, "agents": remaining_agents}

            # 上下文传递：构建前置 Agent 输出摘要
            if all_results and batch_index > 0:
                context = self._build_context(all_results)
                task_with_context = f"{task}\n\n前置 Agent 输出：\n{context}"
            else:
                task_with_context = task

            # 选择执行模式
            if use_task_orchestration and session_id:
                batch_results = self.execute_batch_with_decomposition(
                    runnable_batch, task_with_context, history, batch_index, session_id,
                    event_callback, user_id=user_id, result_callback=result_callback,
                )
            else:
                batch_results = self.execute_batch(
                    runnable_batch, task_with_context, history, batch_index, event_callback,
                    user_id=user_id, session_id=session_id, result_callback=result_callback,
                )

            all_results.extend(batch_results)
            new_results.extend(batch_results)
            completed_agent_ids.update(
                result.get("agent_id") for result in batch_results if result.get("agent_id")
            )

        return new_results

    def execute_batch_with_decomposition(
        self,
        batch: Dict,
        task: str,
        history: List[Dict],
        batch_index: int,
        session_id: int,
        event_callback: Optional[Callable] = None,
        user_id: Optional[int] = None,
        result_callback: Optional[Callable[[AgentExecutionResult], None]] = None,
    ) -> List[AgentExecutionResult]:
        """执行单个批次，使用任务分解编排

        Args:
            batch: {"priority": 40, "agents": ["检验科专家"]}
            task: 执行任务（含上下文）
            history: 对话历史
            batch_index: 批次索引
            session_id: LeaderSession ID
            event_callback: SSE 事件回调

        Returns:
            List[AgentExecutionResult]
        """
        from .task_planner import TaskPlanner
        from .subtask_executor import SubTaskExecutor
        from .task_runtime import TaskRuntime
        from services.harness.harness_adapter import HarnessToolRegistry
        from services.harness.harness_coordinator import get_agent_type_from_id

        agents = batch.get("agents", [])
        if not agents:
            return []

        # 检查停止标志
        if self.stop_checker and self.stop_checker():
            logger.info(f"Execution stopped before batch {batch_index}")
            return []

        results = []

        # 初始化任务编排组件
        planner = TaskPlanner(llm_service=self._llm_service, locale=self._locale)
        executor = SubTaskExecutor(
            tool_registry=self._tool_registry,
            llm_service=self._llm_service,
            user_id=user_id,
            locale=self._locale,
        )

        # 前置校验：过滤未注册的 Agent
        valid_agents = []
        for agent_id in agents:
            if self.coordinator.get_agent_info(agent_id):
                valid_agents.append(agent_id)
            else:
                logger.warning(f"Agent '{agent_id}' not registered, skipping")
                result = self._error_result(agent_id, batch_index, f"Agent '{agent_id}' not registered")
                results.append(result)
                if result_callback:
                    result_callback(result)

        if not valid_agents:
            return results

        # 批次内并行执行（使用任务编排）
        # 捕获调用方 contextvars（NodeServices），在线程池 worker 中恢复。
        with ThreadPoolExecutor(max_workers=min(len(valid_agents), self.max_parallel)) as pool:
            futures = {
                self._submit_with_context(
                    pool,
                    self._execute_agent_with_orchestration,
                    agent_id,
                    task,
                    history,
                    session_id,
                    planner,
                    executor,
                    event_callback,
                ): agent_id
                for agent_id in valid_agents
            }

            for future in as_completed(futures):
                agent_id = futures[future]
                try:
                    result = future.result()
                    result = self._normalize_result(result, agent_id, batch_index)
                    results.append(result)
                except Exception as e:
                    logger.error(f"Agent {agent_id} orchestration failed: {e}", exc_info=True)
                    result = self._error_result(agent_id, batch_index, str(e))
                    results.append(result)

                # 实时推送 agent 结果到前端（不等整个 execute_plan 返回）
                push_sse_event(session_id, self._build_result_event(result, session_id))
                if result_callback:
                    result_callback(result)

        return results

    @staticmethod
    def _submit_with_context(pool: ThreadPoolExecutor, func: Callable, *args):
        """将调用方的上下文独立副本提交给一个 worker。

        一个 ``Context`` 同一时刻只能被一个线程进入。若为整个并行批次捕获
        一个共享实例，会导致并发 worker 抛出
        ``RuntimeError: context is already entered``。
        """
        worker_context = contextvars.copy_context()
        return pool.submit(worker_context.run, func, *args)

    def _execute_agent_with_orchestration(
        self,
        agent_id: str,
        task: str,
        history: List[Dict],
        session_id: int,
        planner: Any,
        executor: Any,
        event_callback: Optional[Callable] = None,
    ) -> Dict:
        """使用任务编排执行单个 Agent

        Args:
            agent_id: Agent ID
            task: 执行任务
            history: 对话历史
            session_id: LeaderSession ID
            planner: TaskPlanner 实例
            executor: SubTaskExecutor 实例
            event_callback: SSE 事件回调

        Returns:
            执行结果字典
        """
        started_at = time.perf_counter()
        usage_metrics = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "call_count": 0,
            "failure_count": 0,
            "elapsed": 0.0,
        }
        from services.harness.harness_coordinator import get_agent_type_from_id
        from .task_runtime import TaskRuntime

        # 获取 Agent 信息
        agent_info = self.coordinator.get_agent_info(agent_id)
        agent_name = resolve_agent_display_name(
            agent_id,
            agent_info.get("name") if agent_info else agent_id,
            self._locale,
            agent_info.get("is_system") if agent_info else None,
        )
        agent_tools = agent_info.get("tools", []) if agent_info else []
        # 从 Agent 配置加载角色定义（Role/Persona/Core Expertise）
        agent_system_prompt = agent_info.get("system_prompt", "") if agent_info else ""

        # 注入模板自定义系统提示
        if self._system_prompt_addition:
            agent_system_prompt = f"{agent_system_prompt}\n\n{self._system_prompt_addition}" if agent_system_prompt else self._system_prompt_addition

        if agent_system_prompt:
            logger.info(f"Agent {agent_id}: loaded system_prompt ({len(agent_system_prompt)} chars)")

        # 按 user_id 过滤不可用的工具（避免 LLM 规划后全部被跳过）
        user_id = getattr(executor, '_user_id', None)
        agent_tools = self._filter_tools_for_user(agent_tools, user_id)

        # 获取 Agent 类型
        agent_type = get_agent_type_from_id(agent_id)

        capture_usage = getattr(self._llm_service, "capture_usage", None)
        usage_context = capture_usage() if callable(capture_usage) else nullcontext(usage_metrics)
        captured_metrics = usage_context.__enter__()
        if isinstance(captured_metrics, dict):
            usage_metrics = captured_metrics

        try:
            # 1. TaskPlanner 分解任务（注入 Agent 角色定义）
            decomposition = planner.decompose(
                agent_id=agent_id,
                agent_name=agent_name,
                task=task,
                available_tools=agent_tools,
                agent_system_prompt=agent_system_prompt,
            )

            # 2. TaskRuntime 初始化
            runtime = TaskRuntime(
                session_id=session_id,
                decomposition=decomposition,
                llm_service=self._llm_service,
                allowed_tools=agent_tools,
                locale=self._locale,
            )
            runtime.emit_decomposition()

            # 3. 执行所有子任务（直到无 pending 子任务）
            # 安全守卫：独立迭代计数器防止 LLM 持续 add_subtask 导至无限循环
            configured_iterations = int(os.getenv('MAX_AGENT_SUBTASK_ITERATIONS', str(MAX_SUBTASKS)))
            MAX_ITERATIONS = max(1, min(configured_iterations, MAX_SUBTASKS))
            iteration_count = 0
            while True:
                if self.stop_checker and self.stop_checker():
                    logger.info(f"Agent {agent_id}: stop requested before next subtask")
                    return self._apply_execution_metrics(
                        self._stopped_result(agent_id, agent_name), usage_metrics, started_at
                    )

                subtask = runtime.get_next_subtask()
                if not subtask:
                    break

                subtask["tools"] = runtime.filter_tools(
                    self._filter_tools_for_user(subtask.get("tools", []), user_id)
                )

                iteration_count += 1
                if iteration_count > MAX_ITERATIONS:
                    logger.error(f"Agent {agent_id}: iteration limit ({MAX_ITERATIONS}) reached, forcing stop")
                    break

                # 执行子任务（注入 Agent 角色定义）
                executed = executor.execute_subtask(
                    subtask=subtask,
                    runtime=runtime,
                    task_context=task,
                    session_id=session_id,
                    agent_name=agent_name,
                    agent_type=agent_type,
                    agent_system_prompt=agent_system_prompt,
                    allowed_tools=agent_tools,
                )

                if self.stop_checker and self.stop_checker():
                    logger.info(f"Agent {agent_id}: stop requested after subtask {subtask.get('id')}")
                    return self._apply_execution_metrics(
                        self._stopped_result(agent_id, agent_name), usage_metrics, started_at
                    )

                # 4. 检查是否需要调整
                # 失败/空响应已经由子任务标记为 skipped；不要把空结果误判为“信息不足”
                # 再动态追加搜索任务，否则一次可恢复的 LLM 空响应会表现为流程卡住。
                if executed.get("status") in {"failed", "skipped"} and not executed.get("result"):
                    continue
                decision = runtime.check_and_adjust(executed.get("result", ""))
                if decision["action"] == "abort":
                    logger.warning(
                        f"Agent {agent_id}: legacy abort decision ignored, continue remaining subtasks. "
                        f"reason={decision['reason']}"
                    )
                    continue

            if self.stop_checker and self.stop_checker():
                logger.info(f"Agent {agent_id}: stop requested before final synthesis")
                return self._apply_execution_metrics(
                    self._stopped_result(agent_id, agent_name), usage_metrics, started_at
                )

            # 5. 生成最终结果：综合所有子任务结果生成完整报告（注入 Agent 角色定义）
            from .agent_report_synthesizer import AgentReportSynthesizer
            raw_tool_results, evidence_map = self._collect_evidence(decomposition["subtasks"], agent_id)
            synthesizer = AgentReportSynthesizer(
                llm_service=self._llm_service,
                locale=self._locale,
            )
            final_content = synthesizer.synthesize(
                subtasks=decomposition["subtasks"],
                agent_name=agent_name,
                agent_type=agent_type,
                original_task=task,
                agent_system_prompt=agent_system_prompt,
                evidence_map=evidence_map,
                raw_tool_results=raw_tool_results,
            )
            available_evidence_ids = {
                item.get("evidence_id") for item in evidence_map if item.get("evidence_id")
            }
            evidence_refs = self._extract_cited_evidence_ids(
                final_content,
                available_evidence_ids,
            )
            structured_report = build_agent_structured_report(
                final_content,
                evidence_refs=evidence_refs,
                claim_id_prefix=agent_id,
            )
            content_locale = detect_content_locale(final_content, self._locale)
            if content_locale != self._locale:
                logger.warning(
                    "Leader output locale mismatch: session=%s kind=agent_report agent=%s expected=%s actual=%s",
                    session_id,
                    agent_id,
                    self._locale,
                    content_locale,
                )
            progress_summary = runtime.get_progress_summary()
            degraded = bool(decomposition.get("degraded"))
            degradation_reason = decomposition.get("degradation_reason") if degraded else None

            result = {
                "success": True,
                "status": "completed",
                "content": final_content,
                "summary": structured_report["summary"],
                "structured_report": structured_report,
                "content_locale": content_locale,
                "raw_tool_results": raw_tool_results,
                "evidence_map": evidence_map,
                "tool_calls": [],  # 子任务级别的 tool_calls 已通过 SSE 推送
                "tokens_used": 0,
                "execution_time": 0,
                "decomposition": decomposition,
                "progress_summary": progress_summary,
                "quality_status": "degraded" if degraded else "normal",
                "degradation_reason": degradation_reason,
            }
            return self._apply_execution_metrics(result, usage_metrics, started_at)

        except Exception as e:
            logger.error(f"Agent {agent_id} orchestration failed: {e}", exc_info=True)
            result = {
                "success": False,
                "status": "failed",
                "content": f"Agent 任务编排执行失败: {str(e)}",
                "tool_calls": [],
                "tokens_used": 0,
                "execution_time": 0,
                "error": str(e),
            }
            return self._apply_execution_metrics(result, usage_metrics, started_at)
        finally:
            usage_context.__exit__(None, None, None)

    @staticmethod
    def _stopped_result(agent_id: str, agent_name: str) -> Dict:
        return {
            "success": False,
            "status": "stopped",
            "content": "用户请求停止执行",
            "tool_calls": [],
            "tokens_used": 0,
            "execution_time": 0,
            "error": "用户请求停止执行",
            "agent_id": agent_id,
            "agent_name": agent_name,
        }

    @staticmethod
    def _apply_execution_metrics(
        result: Dict,
        usage_metrics: Dict[str, Any],
        started_at: float,
    ) -> Dict:
        """附加每个 Agent 的 LLM token 用量及实际墙钟耗时。"""
        total_tokens = usage_metrics.get("total_tokens")
        if total_tokens is None:
            total_tokens = usage_metrics.get("input_tokens", 0) + usage_metrics.get("output_tokens", 0)
        result["tokens_used"] = max(0, int(total_tokens or 0))
        result["execution_time"] = max(0.0, round(time.perf_counter() - started_at, 6))
        return result

    def _build_context(self, results: List[AgentExecutionResult]) -> str:
        """构建前置 Agent 输出摘要

        Args:
            results: 前置批次执行结果

        Returns:
            上下文摘要字符串
        """
        context_parts = []

        for r in results:
            # TypedDict 使用字典访问而非属性访问
            success = r.get("success", False) if isinstance(r, dict) else getattr(r, "success", False)
            content = r.get("content", "") if isinstance(r, dict) else getattr(r, "content", "")
            agent_name = r.get("agent_name", r.get("agent_id", "unknown")) if isinstance(r, dict) else getattr(r, "agent_name", getattr(r, "agent_id", "unknown"))

            if success and content:
                summary = r.get("summary") if isinstance(r, dict) else getattr(r, "summary", None)
                lines = [f"### {agent_name}"]
                if isinstance(summary, dict):
                    self._append_context_value(lines, "结论", summary.get("one_sentence"))
                    self._append_context_items(lines, "关键发现", summary.get("key_findings"))
                    self._append_context_items(lines, "建议", summary.get("recommendations"))
                    self._append_context_items(lines, "风险", summary.get("risks"))
                    self._append_context_items(lines, "待确认", summary.get("open_questions"))

                evidence_map = r.get("evidence_map", []) if isinstance(r, dict) else getattr(r, "evidence_map", [])
                raw_tool_results = r.get("raw_tool_results", {}) if isinstance(r, dict) else getattr(r, "raw_tool_results", {})
                preferred_refs = summary.get("evidence_refs", []) if isinstance(summary, dict) else []
                selection = EvidenceContextBuilder(
                    total_char_budget=(
                        _BATCH_CONTEXT_EVIDENCE_LIMIT
                        * _BATCH_CONTEXT_EVIDENCE_EXCERPT_LIMIT
                    ),
                    item_char_budget=_BATCH_CONTEXT_EVIDENCE_EXCERPT_LIMIT,
                    item_limit=_BATCH_CONTEXT_EVIDENCE_LIMIT,
                ).build(
                    evidence_map or [],
                    raw_tool_results=raw_tool_results or {},
                    preferred_refs=preferred_refs,
                )
                if selection.text:
                    lines.append("证据段落：")
                    lines.extend(selection.text.splitlines())

                if len(lines) == 1:
                    lines.append(
                        self._clip_context_text(content, _BATCH_CONTEXT_REPORT_EXCERPT_LIMIT)
                    )
                context_parts.append("\n".join(lines))

        if not context_parts:
            return "无前置输出"

        return "\n".join(context_parts)

    @staticmethod
    def _clip_context_text(value: Any, limit: int) -> str:
        text = str(value or "").strip()
        if len(text) <= limit:
            return text
        return text[:limit] + "...(已截断)"

    @classmethod
    def _append_context_value(cls, lines: List[str], label: str, value: Any) -> None:
        text = cls._clip_context_text(value, _BATCH_CONTEXT_ITEM_CHAR_LIMIT)
        if text:
            lines.append(f"{label}：{text}")

    @classmethod
    def _append_context_items(cls, lines: List[str], label: str, value: Any) -> None:
        if not isinstance(value, list):
            return
        items = [
            cls._clip_context_text(item, _BATCH_CONTEXT_ITEM_CHAR_LIMIT)
            for item in value[:_BATCH_CONTEXT_FINDING_LIMIT]
        ]
        items = [item for item in items if item]
        if items:
            lines.append(f"{label}：" + "；".join(items))

    @staticmethod
    def _scoped_evidence_id(agent_id: str, evidence_id: str, max_len: int = 100) -> str:
        """为单个 Agent 的证据构建稳定且唯一的持久化键。"""
        agent_text = str(agent_id or "")
        evidence_text = str(evidence_id or "")

        def normalize(value: str, fallback: str) -> str:
            normalized = "".join(
                ch if (ch.isascii() and (ch.isalnum() or ch in "_.:-")) else "_"
                for ch in value
            ).strip("_.:-")
            return normalized or fallback

        safe_agent = normalize(agent_text, "agent")
        safe_evidence = normalize(evidence_text, "evidence")
        candidate = f"{safe_agent}_{safe_evidence}"
        if (
            candidate == f"{agent_text}_{evidence_text}"
            and len(candidate) <= max_len
        ):
            return candidate

        digest = hashlib.sha256(
            f"{agent_text}\0{evidence_text}".encode("utf-8")
        ).hexdigest()[:16]
        suffix = f"_{digest}"
        stem = candidate[:max_len - len(suffix)].rstrip("_.:-") or "evidence"
        return f"{stem}{suffix}"

    @staticmethod
    def _collect_evidence(subtasks: List[SubTask], agent_id: str) -> tuple[Dict, List[Dict]]:
        """合并各子任务的证据，并为 evidence_id 添加 Agent 前缀。

        每个 Agent 的子任务编号都从 subtask_1 开始，如果不加前缀，
        不同 Agent 之间会出现相同的 evidence_id；加前缀可保证
        在会话（最终报告）层面的唯一性。前缀会经过规范化，
        使拼接后的证据 ID 仍是合法的持久化键
        （见 DecisionEvidenceService._EVIDENCE_ID_RE）。
        """
        raw_tool_results: Dict = {}
        evidence_map: List[Dict] = []
        id_remap: Dict[str, str] = {}   # old_id → new_id
        for subtask in subtasks:
            for item in subtask.get("evidence_map", []) or []:
                if not isinstance(item, dict):
                    continue
                old_id = item.get("evidence_id")
                if old_id and old_id not in id_remap:
                    id_remap[old_id] = BatchExecutor._scoped_evidence_id(
                        agent_id, old_id
                    )

        for subtask in subtasks:
            old_raw = subtask.get("raw_tool_results", {}) or {}
            for old_key, value in old_raw.items():
                new_key = id_remap.get(old_key, old_key)
                raw_tool_results[new_key] = value
            for item in subtask.get("evidence_map", []) or []:
                if isinstance(item, dict):
                    old_id = item.get("evidence_id")
                    new_id = id_remap.get(old_id, old_id)
                    enriched = {**item, "agent_id": agent_id, "evidence_id": new_id}
                    if old_id and new_id != old_id:
                        enriched["raw_ref"] = f"raw_tool_results.{new_id}"
                    evidence_map.append(enriched)
        return raw_tool_results, evidence_map

    @staticmethod
    def _extract_cited_evidence_ids(content: str, available_ids: set[str]) -> List[str]:
        """按报告出现顺序提取引用，并丢弃不存在的证据 ID。"""
        cited = re.findall(r"\[evidence_id:([^\]\s]+)\]", content or "")
        return list(dict.fromkeys(item for item in cited if item in available_ids))

    def _normalize_result(
        self,
        result: Dict,
        agent_id: str,
        batch_index: int
    ) -> AgentExecutionResult:
        """规范化执行结果

        Args:
            result: HarnessCoordinator.execute_agent() 返回值
            agent_id: Agent ID
            batch_index: 批次索引

        Returns:
            AgentExecutionResult
        """
        agent_info = self.coordinator.get_agent_info(agent_id)
        agent_name = agent_id
        if agent_info:
            agent_name = resolve_agent_display_name(
                agent_id,
                agent_info.get("name", agent_id),
                self._locale,
                agent_info.get("is_system"),
            )

        return AgentExecutionResult(
            agent_id=agent_id,
            agent_name=agent_name,
            success=result.get("success", False),
            status=result.get("status", "completed"),
            content=result.get("content", ""),
            content_locale=result.get("content_locale", self._locale),
            summary=result.get("summary"),
            structured_report=result.get("structured_report"),
            raw_tool_results=result.get("raw_tool_results"),
            evidence_map=result.get("evidence_map"),
            tool_calls=result.get("tool_calls", []),
            tokens_used=result.get("tokens_used", 0),
            execution_time=result.get("execution_time", 0),
            error=result.get("error"),
            batch_index=batch_index,
            created_at=datetime.now(timezone.utc).isoformat(),
            decomposition=result.get("decomposition"),
            progress_summary=result.get("progress_summary"),
            quality_status=result.get("quality_status", "normal"),
            degradation_reason=result.get("degradation_reason"),
        )

    @staticmethod
    def _filter_tools_for_user(tools: List[str], user_id: Optional[int] = None) -> List[str]:
        """按当前执行约束过滤工具列表。

        规划阶段调用，避免 LLM 规划当前不稳定或不可用的工具。

        Args:
            tools: 原始工具列表
            user_id: 当前用户 ID

        Returns:
            过滤后的工具列表
        """
        filtered_tools = [
            tool for tool in tools
            if tool not in {"file_read", "llm_analysis"}
        ]

        if not user_id or "knowledge_search" not in filtered_tools:
            return filtered_tools
        try:
            from config import Config
            import os
            graph_path = Config.get_user_graph_path(user_id)
            if not (os.path.exists(graph_path) and os.path.getsize(graph_path) > 10):
                logger.info(f"_filter_tools_for_user: removing knowledge_search (no graph for user_id={user_id})")
                return [t for t in filtered_tools if t != "knowledge_search"]
        except Exception:
            return filtered_tools
        return filtered_tools

    def _error_result(
        self,
        agent_id: str,
        batch_index: int,
        error: str
    ) -> AgentExecutionResult:
        """构建错误结果

        Args:
            agent_id: Agent ID
            batch_index: 批次索引
            error: 错误信息

        Returns:
            AgentExecutionResult（失败状态）
        """
        return AgentExecutionResult(
            agent_id=agent_id,
            agent_name=agent_id,
            success=False,
            status="failed",
            content="",
            tool_calls=[],
            tokens_used=0,
            execution_time=0,
            error=error,
            batch_index=batch_index,
            created_at=datetime.now(timezone.utc).isoformat()
        )

    @staticmethod
    def _build_result_event(result: AgentExecutionResult, session_id: int) -> Dict:
        """构建 agent 结果 SSE 事件（用于实时推送）

        Args:
            result: 规范化的执行结果
            session_id: LeaderSession ID

        Returns:
            SSE 事件字典（agent_result 或 agent_error）
        """
        if result.get("success"):
            return {
                "type": "agent_result",
                "session_id": session_id,
                "agent_id": result.get("agent_id"),
                "agent_name": result.get("agent_name"),
                "content": result.get("content"),
                "content_locale": result.get("content_locale"),
                "summary": result.get("summary"),
                "structured_report": result.get("structured_report"),
                "evidence_map": result.get("evidence_map"),
                "status": "success",
                "tool_calls": result.get("tool_calls", []),
                "tokens_used": result.get("tokens_used", 0),
                "execution_time": result.get("execution_time", 0),
                "decomposition": result.get("decomposition"),
                "progress_summary": result.get("progress_summary"),
                "quality_status": result.get("quality_status", "normal"),
                "degradation_reason": result.get("degradation_reason"),
            }
        return {
            "type": "agent_error",
            "session_id": session_id,
            "agent_id": result.get("agent_id"),
            "agent_name": result.get("agent_name"),
            "content": result.get("content") or result.get("error") or "Agent 执行失败",
            "error": result.get("error"),
            "status": "failed",
        }
