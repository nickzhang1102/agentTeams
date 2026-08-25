from unittest.mock import MagicMock, patch

from leader.subtask_executor import SubTaskExecutor


def test_execute_subtask_runs_llm_analysis_without_tool_registry_lookup():
    llm_service = MagicMock()
    llm_service.get_max_output_tokens.return_value = 4096
    llm_service.call_sync.return_value = "analysis result"

    tool_registry = MagicMock()
    runtime = MagicMock()
    executor = SubTaskExecutor(tool_registry=tool_registry, llm_service=llm_service)

    subtask = {
        "id": "subtask_1",
        "goal": "分析风险",
        "tools": ["llm_analysis"],
        "status": "pending",
        "result": "",
    }

    result = executor.execute_subtask(
        subtask=subtask,
        runtime=runtime,
        task_context="期货投资场景",
        session_id=1,
        agent_name="魔鬼代言人",
    )

    assert result["status"] == "completed"
    assert result["result"] == "analysis result"
    assert result["evidence_map"][0]["source_type"] == "subtask_result"
    tool_registry.execute_tool.assert_not_called()
    # 单个短分析结果可直接消费，不再重复调用摘要模型。
    assert llm_service.call_sync.call_count == 1


def test_execute_subtask_caps_llm_analysis_and_summary_token_budgets():
    llm_service = MagicMock()
    llm_service.get_max_output_tokens.return_value = 327680
    llm_service.call_sync.return_value = "analysis result"

    executor = SubTaskExecutor(tool_registry=MagicMock(), llm_service=llm_service)
    subtask = {
        "id": "subtask_1",
        "goal": "分析风险",
        "tools": ["llm_analysis"],
        "status": "pending",
        "result": "",
    }

    result = executor.execute_subtask(
        subtask=subtask,
        runtime=MagicMock(),
        task_context="期货投资场景",
        session_id=1,
    )

    assert result["result"] == "analysis result"
    calls = llm_service.call_sync.call_args_list
    assert calls[0].kwargs["max_tokens"] == 4096
    assert calls[0].kwargs["max_attempts"] == 1


def test_execute_subtask_attaches_tool_evidence_and_truncates_raw_result():
    tool_registry = MagicMock()
    tool_registry.execute_tool.return_value = {
        "success": True,
        "result": "R" * 60000,
    }
    llm_service = MagicMock()
    llm_service.get_max_output_tokens.return_value = 4096
    llm_service.call_sync.return_value = "summary result"

    executor = SubTaskExecutor(tool_registry=tool_registry, llm_service=llm_service)
    subtask = {
        "id": "subtask_1",
        "goal": "搜索资料",
        "tools": ["web_search"],
        "status": "pending",
        "result": "",
    }

    result = executor.execute_subtask(
        subtask=subtask,
        runtime=MagicMock(),
        task_context="任务",
        session_id=1,
    )

    assert result["status"] == "completed"
    assert llm_service.call_sync.call_count == 1
    assert len(result["evidence_map"]) == 1
    evidence = result["evidence_map"][0]
    assert evidence["evidence_id"].startswith("ev_subtask_1_web_search_")
    assert evidence["raw_ref"] == f"raw_tool_results.{evidence['evidence_id']}"
    raw = result["raw_tool_results"][evidence["evidence_id"]]
    assert raw["tool_name"] == "web_search"
    assert raw["success"] is True
    assert len(raw["result"]) < 15100


def test_execute_subtask_attaches_each_structured_search_result_as_evidence():
    tool_registry = MagicMock()
    candidates = [
        {
            "source_type": "web",
            "source_id": f"https://example.com/{index}",
            "title": f"Result {index}",
            "url": f"https://example.com/{index}",
            "provider": "exa",
            "rank": index,
            "excerpt": f"Excerpt {index}",
            "passage": ("P" * 350) + ("critical limitation" if index == 8 else ""),
            "locator": {},
            "completeness": "passage",
        }
        for index in range(1, 11)
    ]
    tool_registry.execute_tool.return_value = {
        "success": True,
        "result": "search result",
        "metadata": {"evidence_items": candidates},
    }
    executor = SubTaskExecutor(tool_registry=tool_registry)
    subtask = {
        "id": "subtask_1",
        "goal": "搜索资料",
        "tools": ["web_search"],
        "status": "pending",
        "result": "",
    }

    result = executor.execute_subtask(
        subtask=subtask,
        runtime=MagicMock(),
        task_context="任务",
        session_id=1,
    )

    assert len(result["evidence_map"]) == 10
    eighth = result["evidence_map"][7]
    assert eighth["rank"] == 8
    assert eighth["url"] == "https://example.com/8"
    assert eighth["schema_version"] == 2
    assert "critical limitation" not in eighth["excerpt"]
    assert "critical limitation" in result["raw_tool_results"][eighth["evidence_id"]]["passage"]


def test_execute_llm_analysis_preserves_large_context_and_marks_timeout_as_failure_result():
    llm_service = MagicMock()
    llm_service.get_max_output_tokens.return_value = 327680
    llm_service.call_sync.side_effect = RuntimeError("Request timed out.")

    executor = SubTaskExecutor(llm_service=llm_service)

    task_context = "BEGIN-PATIENT-CONTEXT\n" + ("A" * 50000) + "\nEND-PATIENT-CONTEXT"
    result = executor._execute_llm_analysis(
        subtask={"id": "subtask_1", "goal": "分析风险", "tools": []},
        task_context=task_context,
        agent_system_prompt="R" * 10000,
        agent_name="测试专家",
    )

    assert result["success"] is False
    assert "LLM 分析超时或失败" in result["error"]
    assert result["result"] == ""
    call = llm_service.call_sync.call_args
    assert call.kwargs["max_tokens"] == 4096
    assert call.kwargs["max_attempts"] == 1
    assert task_context in call.kwargs["message"]
    task_context_section = call.kwargs["message"].split("## 任务上下文", 1)[1]
    assert "前文已截断" not in task_context_section
    assert len(call.kwargs["system_prompt"]) < 5000


def test_execute_llm_analysis_empty_response_is_a_skipped_subtask_not_an_exception():
    llm_service = MagicMock()
    llm_service.get_max_output_tokens.return_value = 4096
    llm_service.call_sync.return_value = ""

    executor = SubTaskExecutor(llm_service=llm_service)
    result = executor.execute_subtask(
        subtask={
            "id": "subtask_1",
            "goal": "分析风险",
            "tools": ["llm_analysis"],
            "status": "pending",
            "result": "",
        },
        runtime=MagicMock(),
        task_context="Context",
        session_id=1,
    )

    assert result["status"] == "skipped"
    assert result["result"] == ""
    raw_error = next(iter(result["raw_tool_results"].values()))["error"]
    assert "empty content" in raw_error
    assert llm_service.call_sync.call_args.kwargs["empty_content_ok"] is True


def test_english_llm_analysis_appends_locale_instruction_after_role_and_date():
    llm_service = MagicMock()
    llm_service.get_max_output_tokens.return_value = 4096
    llm_service.call_sync.return_value = "English analysis"
    executor = SubTaskExecutor(llm_service=llm_service, locale="en-US")

    with patch("leader.node_utils.build_current_date_prompt", return_value="<DATE>"):
        result = executor._execute_llm_analysis(
            subtask={"id": "subtask_1", "goal": "Analyze risk", "tools": []},
            task_context="Context",
            agent_system_prompt="<ROLE>",
            agent_name="Risk Analyst",
        )

    system_prompt = llm_service.call_sync.call_args.kwargs["system_prompt"]
    assert result["result"] == "English analysis"
    assert system_prompt.startswith("<ROLE><DATE>")
    assert system_prompt.index("<DATE>") < system_prompt.index("## Output language")
    assert system_prompt.endswith("Preserve user input, raw evidence, and tool results verbatim.")


def test_english_llm_analysis_failure_and_empty_tool_fallback_are_localized():
    llm_service = MagicMock()
    llm_service.get_max_output_tokens.return_value = 4096
    llm_service.call_sync.side_effect = RuntimeError("timeout")
    executor = SubTaskExecutor(llm_service=llm_service, locale="en-US")

    result = executor._execute_llm_analysis(
        subtask={"id": "subtask_1", "goal": "Analyze risk", "tools": []},
        task_context="Context",
    )

    assert result["error"].startswith("LLM analysis timed out or failed")
    assert executor._concat_raw_results([]) == "No execution results"


def test_tool_summary_preserves_raw_tool_result_text():
    executor = SubTaskExecutor(llm_service=None, locale="en-US")
    raw_text = "原始证据必须保持原文: revenue grew 12%."

    summary = executor._summarize_with_llm(
        [{"success": True, "result": raw_text}],
        goal="Summarize the evidence",
    )

    assert summary == raw_text


def test_execute_subtask_rejects_tool_outside_empty_allowlist():
    tool_registry = MagicMock()
    executor = SubTaskExecutor(tool_registry=tool_registry, allowed_tools=[])
    subtask = {
        "id": "subtask_1",
        "goal": "执行命令",
        "tools": ["bash"],
        "status": "pending",
        "result": "",
    }

    result = executor.execute_subtask(
        subtask=subtask,
        runtime=MagicMock(),
        task_context="任务",
        session_id=1,
    )

    assert result["status"] == "skipped"
    assert "not allowed" in next(iter(result["raw_tool_results"].values()))["error"]
    tool_registry.execute_tool.assert_not_called()


def test_execute_subtask_allows_wildcard_and_mapped_tool_name():
    tool_registry = MagicMock()
    tool_registry.execute_tool.return_value = {"success": True, "result": "ok"}
    executor = SubTaskExecutor(
        tool_registry=tool_registry,
        allowed_tools=["write_file", "mcp__exa__*"],
    )

    assert executor._is_tool_allowed("file_write") is True
    assert executor._is_tool_allowed("mcp__exa__search") is True
    assert executor._is_tool_allowed("bash") is False
