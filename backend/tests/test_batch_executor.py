"""
批次执行器测试

测试批次执行器的核心功能：
- 批次内并行执行
- 批次间顺序执行
- 停止检查
- 结果规范化
- 空计划/空批次处理
"""
import re
from contextvars import ContextVar
from threading import Barrier

import pytest
from contextlib import contextmanager
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from leader.batch_executor import BatchExecutor
from leader.execution_result import AgentExecutionResult


class TestBatchExecutor:
    """BatchExecutor 单元测试"""

    def setup_method(self):
        """每个测试前初始化 mock coordinator"""
        self.mock_coordinator = MagicMock()
        self.mock_coordinator.get_agent_info.return_value = {
            "name": "Test Agent",
            "description": "Test agent for unit tests"
        }
        self.mock_coordinator.execute_agent.return_value = {
            "success": True,
            "status": "completed",
            "agent_id": "test_agent",
            "content": "Test execution result",
            "tool_calls": [{"tool": "web_search", "input": "test", "output": "ok"}],
            "tokens_used": 150,
            "execution_time": 0.3,
            "error": None
        }

    def test_execute_batch_parallel(self):
        """S2：单批次并行执行"""
        executor = BatchExecutor(self.mock_coordinator, max_parallel=5)

        batch = {"priority": 50, "agents": ["agent_1", "agent_2"]}
        results = executor.execute_batch(batch, "test task", [], 0)

        # 验证返回 2 个结果
        assert len(results) == 2
        # 验证都是成功
        assert all(r["success"] for r in results)
        # 验证 batch_index 正确
        assert all(r["batch_index"] == 0 for r in results)

    def test_execute_batch_parallel_uses_independent_context_copies(self):
        """并行工作线程继承调用方上下文，而不共享同一个 Context。"""
        service_context = ContextVar("test_batch_service_context", default=None)
        overlap = Barrier(2)
        coordinator = MagicMock()
        coordinator.get_agent_info.return_value = {"name": "Test Agent"}

        def execute_agent(agent_id, *_args):
            inherited_value = service_context.get()
            overlap.wait(timeout=2)
            return {
                "success": True,
                "status": "completed",
                "agent_id": agent_id,
                "content": inherited_value,
                "tool_calls": [],
                "tokens_used": 0,
                "execution_time": 0,
                "error": None,
            }

        coordinator.execute_agent.side_effect = execute_agent
        token = service_context.set("inherited-node-services")
        try:
            results = BatchExecutor(coordinator, max_parallel=2).execute_batch(
                {"agents": ["agent_1", "agent_2"]},
                "test task",
                [],
                0,
            )
        finally:
            service_context.reset(token)

        assert len(results) == 2
        assert all(result["success"] for result in results)
        assert {result["content"] for result in results} == {"inherited-node-services"}

    def test_execute_batch_passes_workflow_llm_service_to_coordinator(self):
        workflow_llm_service = MagicMock(model="workflow-model")
        executor = BatchExecutor(
            self.mock_coordinator,
            max_parallel=1,
            llm_service=workflow_llm_service,
        )

        executor.execute_batch(
            {"priority": 50, "agents": ["agent_1"]},
            "test task",
            [],
            0,
            user_id=7,
        )

        args = self.mock_coordinator.execute_agent.call_args.args
        assert args[0] == "agent_1"
        assert args[5] == 7
        assert args[6] is workflow_llm_service

    def test_execute_plan_sequential(self):
        """S1：多批次顺序执行"""
        executor = BatchExecutor(self.mock_coordinator, max_parallel=5)

        plan = {
            "execution_batches": [
                {"priority": 40, "agents": ["检验科专家"]},
                {"priority": 50, "agents": ["肿瘤内科专家", "病理科专家"]},
                {"priority": 90, "agents": ["critic-munger"]}
            ]
        }

        results = executor.execute_plan(plan, "test task", [])

        # 验证返回 4 个结果
        assert len(results) == 4
        # 验证批次索引正确（批次1=0，批次2=1，批次3=2）
        batch_indices = [r["batch_index"] for r in results]
        assert batch_indices == [0, 1, 1, 2]

    def test_execute_plan_skips_durable_agents_and_reports_only_new_results(self):
        executor = BatchExecutor(self.mock_coordinator, max_parallel=1)
        persisted = {
            "agent_id": "agent_1",
            "agent_name": "Agent 1",
            "success": True,
            "content": "durable result",
            "tokens_used": 10,
        }
        callbacks = []

        results = executor.execute_plan(
            {
                "execution_batches": [
                    {"priority": 40, "agents": ["agent_1"]},
                    {"priority": 50, "agents": ["agent_2"]},
                ]
            },
            "test task",
            [],
            initial_results=[persisted],
            result_callback=callbacks.append,
        )

        assert [call.args[0] for call in self.mock_coordinator.execute_agent.call_args_list] == ["agent_2"]
        assert [result["agent_id"] for result in results] == ["agent_2"]
        assert [result["agent_id"] for result in callbacks] == ["agent_2"]

    def test_build_context_preserves_structured_findings_and_evidence(self):
        executor = BatchExecutor(self.mock_coordinator)
        context = executor._build_context([{
            "success": True,
            "agent_id": "researcher",
            "agent_name": "研究员",
            "content": "完整报告",
            "summary": {
                "one_sentence": "核心结论",
                "key_findings": ["发现A", "发现B"],
                "recommendations": ["建议A"],
                "risks": ["风险A"],
            },
            "evidence_map": [{
                "evidence_id": "researcher_ev_1",
                "excerpt": "证据原文摘录",
            }],
        }])

        assert "核心结论" in context
        assert "发现A" in context
        assert "建议A" in context
        assert "风险A" in context
        assert "[evidence_id:researcher_ev_1]" in context
        assert "证据原文摘录" in context

    def test_execute_plan_stopped(self):
        """S3：用户中断"""
        stop_flag = False
        def stop_checker():
            return stop_flag

        executor = BatchExecutor(self.mock_coordinator, max_parallel=5, stop_checker=stop_checker)

        plan = {
            "execution_batches": [
                {"priority": 40, "agents": ["agent_1"]},
                {"priority": 50, "agents": ["agent_2"]}  # 这个批次会被跳过
            ]
        }

        # 执行第一批次后设置停止标志
        def execute_side_effect(agent_id, *args, **kwargs):
            nonlocal stop_flag
            if agent_id == "agent_1":
                stop_flag = True
            return self.mock_coordinator.execute_agent.return_value

        self.mock_coordinator.execute_agent.side_effect = execute_side_effect

        results = executor.execute_plan(plan, "test task", [])

        # 验证只执行了第一批次
        assert len(results) == 1
        assert results[0]["agent_id"] == "agent_1"

    def test_orchestration_stops_before_next_subtask(self):
        """任务编排循环内部应响应 stop_checker，而不是只在批次边界停止。"""
        executor = BatchExecutor(
            self.mock_coordinator,
            max_parallel=1,
            stop_checker=lambda: True,
            llm_service=MagicMock(),
            tool_registry=MagicMock(),
        )

        with patch("leader.task_planner.TaskPlanner.decompose", return_value={
            "agent_id": "agent_1",
            "agent_name": "Test Agent",
            "subtasks": [
                {
                    "id": "subtask_1",
                    "goal": "不应执行",
                    "tools": [],
                    "status": "pending",
                    "result": "",
                }
            ],
        }):
            result = executor._execute_agent_with_orchestration(
                agent_id="agent_1",
                task="test task",
                history=[],
                session_id=123,
                planner=MagicMock(),
                executor=MagicMock(),
            )

        assert result["status"] == "stopped"
        assert result["error"] == "用户请求停止执行"

    def test_normalize_result(self):
        """测试结果规范化"""
        executor = BatchExecutor(self.mock_coordinator, locale="en-US")

        raw_result = {
            "success": True,
            "status": "completed",
            "content": "Test content",
            "tool_calls": [],
            "tokens_used": 100,
            "execution_time": 0.5,
            "error": None,
            "decomposition": {"subtasks": [{"id": "subtask_1", "status": "completed"}]},
            "progress_summary": {"completedCount": 1, "totalCount": 1},
        }

        normalized = executor._normalize_result(raw_result, "test_agent", 1)

        # 验证 AgentExecutionResult 结构完整
        assert normalized["agent_id"] == "test_agent"
        assert normalized["agent_name"] == "Test Agent"
        assert normalized["success"] == True
        assert normalized["batch_index"] == 1
        assert normalized["tokens_used"] == 100
        assert normalized["decomposition"]["subtasks"][0]["status"] == "completed"
        assert normalized["progress_summary"]["completedCount"] == 1
        assert normalized["content_locale"] == "en-US"
        assert "created_at" in normalized

    def test_error_result(self):
        """S5：Agent 执行失败处理"""
        executor = BatchExecutor(self.mock_coordinator)

        error_result = executor._error_result("unknown_agent", 2, "Connection failed")

        assert error_result["success"] == False
        assert error_result["status"] == "failed"
        assert error_result["agent_id"] == "unknown_agent"
        assert error_result["batch_index"] == 2
        assert error_result["error"] == "Connection failed"

    def test_empty_plan(self):
        """S6：空执行计划处理"""
        executor = BatchExecutor(self.mock_coordinator)

        plan = {"execution_batches": []}
        results = executor.execute_plan(plan, "test task", [])

        assert len(results) == 0

    def test_empty_batch_skipped(self):
        """S7：空批次跳过"""
        executor = BatchExecutor(self.mock_coordinator)

        plan = {
            "execution_batches": [
                {"priority": 50, "agents": []},  # 空批次
                {"priority": 60, "agents": ["agent_1"]}
            ]
        }

        results = executor.execute_plan(plan, "test task", [])

        # 验证只执行了第二个批次
        assert len(results) == 1
        assert results[0]["batch_index"] == 1

    def test_agent_not_registered(self):
        """S8：Agent 未注册处理"""
        self.mock_coordinator.execute_agent.side_effect = ValueError("Agent '不存在专家' not registered")
        executor = BatchExecutor(self.mock_coordinator)

        batch = {"priority": 50, "agents": ["不存在专家"]}
        results = executor.execute_batch(batch, "test task", [], 0)

        # 验证返回失败结果
        assert len(results) == 1
        assert results[0]["success"] == False
        assert "not registered" in results[0]["error"]

    def test_tool_call_event_callback(self):
        """S4：工具调用事件实时推送"""
        event_log = []
        def event_callback(event_data):
            event_log.append(event_data)

        executor = BatchExecutor(self.mock_coordinator)

        batch = {"priority": 50, "agents": ["agent_1"]}
        executor.execute_batch(batch, "test task", [], 0, event_callback)

        # 验证 event_callback 被调用（HarnessCoordinator 会调用）
        # 注意：这里 mock execute_agent 不触发回调，实际运行时会触发

    def test_max_parallel_limit(self):
        """测试并行数限制"""
        executor = BatchExecutor(self.mock_coordinator, max_parallel=2)

        # 5 个 Agent，max_parallel=2
        batch = {"priority": 50, "agents": ["a1", "a2", "a3", "a4", "a5"]}
        results = executor.execute_batch(batch, "test task", [], 0)

        # 验证所有 Agent 都被执行（并行限制不影响结果数量）
        assert len(results) == 5

    def test_filter_tools_removes_file_read(self):
        """规划前应移除 file_read，避免生成无法执行的子任务"""
        tools = ["web_search", "file_read", "grep"]

        filtered = BatchExecutor._filter_tools_for_user(tools, user_id=None)

        assert "file_read" not in filtered
        assert filtered == ["web_search", "grep"]

    def test_filter_tools_removes_internal_llm_analysis(self):
        """动态子任务执行前也应剔除内部分析伪工具。"""
        tools = ["web_search", "llm_analysis", "grep"]

        filtered = BatchExecutor._filter_tools_for_user(tools, user_id=None)

        assert "llm_analysis" not in filtered
        assert filtered == ["web_search", "grep"]

    def test_collect_evidence_remaps_raw_refs_and_keys_in_two_passes(self):
        """证据 ID 加 agent 前缀后，raw_ref 和 raw_tool_results key 应保持一致。"""
        subtasks = [
            {
                "id": "subtask_1",
                "raw_tool_results": {
                    "ev_subtask_1_web_search_1": {"result": "A"},
                },
                "evidence_map": [
                    {
                        "evidence_id": "ev_subtask_1_web_search_1",
                        "title": "证据A",
                        "raw_ref": "raw_tool_results.ev_subtask_1_web_search_1",
                    }
                ],
            }
        ]

        raw_tool_results, evidence_map = BatchExecutor._collect_evidence(subtasks, "planner-agent")

        assert "planner-agent_ev_subtask_1_web_search_1" in raw_tool_results
        assert evidence_map[0]["evidence_id"] == "planner-agent_ev_subtask_1_web_search_1"
        assert evidence_map[0]["raw_ref"] == "raw_tool_results.planner-agent_ev_subtask_1_web_search_1"

    def test_scoped_evidence_ids_are_unique_valid_and_bounded(self):
        old_id = "ev_subtask_1_" + "mcp_tool_" * 12
        first_agent = "A" * 49 + "1"
        second_agent = "A" * 49 + "2"

        first = BatchExecutor._scoped_evidence_id(first_agent, old_id)
        second = BatchExecutor._scoped_evidence_id(second_agent, old_id)
        unicode_id = BatchExecutor._scoped_evidence_id("检验科专家", "证据一")

        assert first != second
        assert len(first) <= 100
        assert len(second) <= 100
        assert len(unicode_id) <= 100
        assert re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}", first)
        assert re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}", second)
        assert re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}", unicode_id)

    def test_extract_cited_evidence_ids_filters_uncited_and_unknown_ids(self):
        content = (
            "结论 A [evidence_id:agent_ev_2]，结论 B [evidence_id:unknown]，"
            "再次引用 [evidence_id:agent_ev_2]。"
        )

        refs = BatchExecutor._extract_cited_evidence_ids(
            content,
            {"agent_ev_1", "agent_ev_2"},
        )

        assert refs == ["agent_ev_2"]

    def test_build_result_event_omits_raw_tool_results(self):
        """实时 SSE 事件不应携带大体积 raw_tool_results。"""
        event = BatchExecutor._build_result_event(
            AgentExecutionResult(
                agent_id="planner",
                agent_name="Planner",
                success=True,
                status="completed",
                content="report",
                content_locale="en-US",
                summary={},
                structured_report={},
                raw_tool_results={"ev_1": {"result": "X" * 100}},
                evidence_map=[],
                tool_calls=[],
                tokens_used=1,
                execution_time=0.1,
                error=None,
                batch_index=0,
                created_at=datetime.now(timezone.utc).isoformat(),
            ),
            session_id=1,
        )

        assert event["type"] == "agent_result"
        assert event["content_locale"] == "en-US"
        assert "raw_tool_results" not in event

    @patch("leader.task_runtime.push_sse_event")
    def test_opposite_language_report_warns_once_without_regeneration(self, mock_push, caplog):
        class StubLLMService:
            def __init__(self):
                self.call_count = 0

            @contextmanager
            def capture_usage(self):
                yield {}

            def get_max_output_tokens(self):
                return 4096

            def call_sync(self, message, system_prompt=None, max_tokens=None, **kwargs):
                self.call_count += 1
                return "# 中文报告\n\n这是明确使用中文生成的完整分析报告，包含足够多的中文内容用于可靠判断。"

        class CompletedPlanner:
            def decompose(self, **kwargs):
                return {
                    "agent_id": "test_agent",
                    "agent_name": "Test Agent",
                    "original_task": kwargs["task"],
                    "current_subtask_id": None,
                    "subtasks": [{
                        "id": "subtask_1",
                        "goal": "Collect evidence",
                        "tools": [],
                        "status": "completed",
                        "result": "completed",
                        "raw_tool_results": {
                            "ev_raw": {"result": "原始工具结果 revenue grew 12%."},
                        },
                        "evidence_map": [{
                            "evidence_id": "ev_raw",
                            "title": "Raw result",
                            "excerpt": "revenue grew 12%",
                            "raw_ref": "raw_tool_results.ev_raw",
                        }],
                    }],
                }

        llm_service = StubLLMService()
        self.mock_coordinator.get_agent_info.return_value = {
            "name": "Test Agent",
            "tools": [],
            "system_prompt": "",
        }
        executor = BatchExecutor(
            self.mock_coordinator,
            llm_service=llm_service,
            locale="en-US",
        )

        with caplog.at_level("WARNING", logger="leader.batch_executor"):
            result = executor._execute_agent_with_orchestration(
                agent_id="test_agent",
                task="Compare options",
                history=[],
                session_id=123,
                planner=CompletedPlanner(),
                executor=MagicMock(),
            )

        assert result["content_locale"] == "zh-CN"
        assert llm_service.call_count == 1
        assert result["raw_tool_results"]["test_agent_ev_raw"]["result"] == "原始工具结果 revenue grew 12%."
        mismatch_logs = [record for record in caplog.records if "locale mismatch" in record.message]
        assert len(mismatch_logs) == 1

    @patch("leader.task_runtime.push_sse_event")
    def test_orchestration_ignores_abort_and_runs_remaining_subtasks(self, mock_push):
        """回归：动态调整若给出 legacy abort，后续 pending 子任务仍应继续执行。"""

        class StubLLMService:
            @contextmanager
            def capture_usage(self):
                yield {
                    "input_tokens": 50,
                    "output_tokens": 27,
                    "total_tokens": 77,
                    "call_count": 2,
                    "failure_count": 0,
                    "elapsed": 0.01,
                }

            async def call_structured(self, messages, response_model, temperature):
                from schemas.leader import AdjustmentDecisionOutput
                return AdjustmentDecisionOutput(
                    action="abort",
                    reason="建议终止",
                    new_subtasks=[],
                )

            def call_sync(self, message, system_prompt=None, max_tokens=None, **kwargs):
                return "final report"

            def get_max_output_tokens(self):
                return 16384

        class FakePlanner:
            def decompose(self, **kwargs):
                return {
                    "agent_id": "test_agent",
                    "agent_name": "Test Agent",
                    "original_task": kwargs["task"],
                    "current_subtask_id": "subtask_1",
                    "subtasks": [
                        {"id": "subtask_1", "goal": "任务一", "tools": [], "status": "pending", "result": ""},
                        {"id": "subtask_2", "goal": "任务二", "tools": [], "status": "pending", "result": ""},
                    ],
                }

        class FakeExecutor:
            def __init__(self):
                self.calls = []

            def execute_subtask(self, subtask, runtime, **kwargs):
                self.calls.append(subtask["id"])
                subtask["status"] = "completed"
                subtask["result"] = (
                    f"{subtask['id']} 完成。"
                    "该子任务已经提供了充分的分析内容、关键证据、风险说明和后续判断，"
                    "长度明确超过五十字，不应再触发信息不足的快速补搜逻辑。"
                )
                runtime.emit_subtask_completed(subtask)
                return subtask

        self.mock_coordinator.get_agent_info.return_value = {
            "name": "Test Agent",
            "tools": ["web_search"],
            "system_prompt": "",
        }
        executor = BatchExecutor(
            self.mock_coordinator,
            llm_service=StubLLMService(),
            tool_registry=MagicMock(),
        )
        fake_executor = FakeExecutor()

        result = executor._execute_agent_with_orchestration(
            agent_id="test_agent",
            task="test task",
            history=[],
            session_id=123,
            planner=FakePlanner(),
            executor=fake_executor,
        )

        assert fake_executor.calls == ["subtask_1", "subtask_2"]
        assert result["success"] is True
        assert result["tokens_used"] == 77
        assert result["execution_time"] > 0
        assert all(st["status"] == "completed" for st in result["decomposition"]["subtasks"])


class TestAgentExecutionResult:
    """AgentExecutionResult TypedDict 测试"""

    def test_type_structure(self):
        """验证 TypedDict 结构完整"""
        result = AgentExecutionResult(
            agent_id="test",
            agent_name="Test Agent",
            success=True,
            status="completed",
            content="test content",
            tool_calls=[],
            tokens_used=100,
            execution_time=0.5,
            error=None,
            batch_index=0,
            created_at=datetime.now(timezone.utc).isoformat()
        )

        # 验证所有字段存在
        assert result["agent_id"] == "test"
        assert result["agent_name"] == "Test Agent"
        assert result["success"] == True
        assert result["status"] == "completed"
        assert result["content"] == "test content"
        assert result["tool_calls"] == []
        assert result["tokens_used"] == 100
        assert result["execution_time"] == 0.5
        assert result["error"] is None
        assert result["batch_index"] == 0
        assert "created_at" in result

    def test_error_result_structure(self):
        """验证错误结果结构"""
        result = AgentExecutionResult(
            agent_id="failed_agent",
            agent_name="Failed Agent",
            success=False,
            status="failed",
            content="",
            tool_calls=[],
            tokens_used=0,
            execution_time=0,
            error="Connection timeout",
            batch_index=2,
            created_at=datetime.now(timezone.utc).isoformat()
        )

        assert result["success"] == False
        assert result["status"] == "failed"
        assert result["error"] == "Connection timeout"

    def test_execute_batch_decomposition_uses_independent_context_copies(self):
        """编排路径同样为每个并行 worker 提供独立的调用方上下文副本。"""
        service_context = ContextVar("test_decomposition_service_context", default=None)
        overlap = Barrier(2)

        def fake_orchestration(agent_id, *_args, **_kwargs):
            inherited_value = service_context.get()
            overlap.wait(timeout=2)
            return {
                "success": True,
                "status": "completed",
                "agent_id": agent_id,
                "content": inherited_value,
                "tool_calls": [],
                "tokens_used": 0,
                "execution_time": 0,
                "error": None,
            }

        executor = BatchExecutor(
            MagicMock(),
            max_parallel=2,
            llm_service=MagicMock(),
        )
        executor.coordinator.get_agent_info.return_value = {"name": "Test Agent"}
        # 用受控桩替换真实编排执行体：本测试只钉住上下文传播与并发安全。
        executor._execute_agent_with_orchestration = fake_orchestration

        token = service_context.set("inherited-node-services")
        try:
            with patch("leader.batch_executor.push_sse_event"):
                results = executor.execute_batch_with_decomposition(
                    {"agents": ["agent_1", "agent_2"]},
                    "test task",
                    [],
                    0,
                    session_id=123,
                )
        finally:
            service_context.reset(token)

        assert len(results) == 2
        assert all(result["success"] for result in results)
        assert {result["content"] for result in results} == {"inherited-node-services"}
