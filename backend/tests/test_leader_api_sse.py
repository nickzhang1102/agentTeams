import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from api import leader_api
from leader import langgraph_entry
from services.llm_service import LLMConfigurationError


@pytest.mark.asyncio
async def test_start_leader_workflow_uses_extended_sse_timeout():
    user = MagicMock()
    user.id = 1
    user.preferred_locale = "zh-CN"

    db_session = MagicMock()
    conversation = MagicMock()
    conversation.user_id = user.id
    conversation.default_locale = "zh-CN"
    db_session.get.return_value = conversation

    query_mock = MagicMock()
    filter_mock = MagicMock()
    filter_mock.all.return_value = []
    filter_mock.first.return_value = None
    with_for_update_mock = MagicMock()
    with_for_update_mock.first.return_value = conversation
    filter_mock.with_for_update.return_value = with_for_update_mock
    query_mock.filter.return_value = filter_mock
    query_mock.filter_by.return_value.first.return_value = conversation
    db_session.query.return_value = query_mock

    reserved_session = MagicMock(id=88)

    with patch.object(leader_api.Config, "AGENTS_DIR", ""), \
         patch.object(leader_api.Config, "WORKSPACE_DIR", ""), \
         patch.object(leader_api.Config, "OPENHARNESS_ENABLED", False), \
         patch("api.leader_api.resolve_model_info", return_value={
             "model_id": "m",
             "api_key": "k",
             "base_url": "http://example.com",
             "max_output_tokens": 16384,
         }), \
         patch("api.leader_api.FileStorage"), \
         patch("api.leader_api.ContextBuilder") as mock_context_builder, \
         patch("api.leader_api.Message") as mock_message_model, \
         patch("api.leader_api.create_leader_session", return_value=reserved_session) as mock_create_session, \
         patch("api.leader_api.async_run_leader_workflow"), \
         patch("api.leader_api.create_sse_streaming_response") as mock_create_response:
        mock_create_response.return_value = "stream"
        mock_context_builder.build.return_value = MagicMock(task_description="task", shared_evidence=[])
        mock_message_model.create_normal_message.return_value = MagicMock(id=1)

        result = await leader_api._start_leader_workflow(
            conversation_id=1,
            message="test",
            file_ids=[],
            user=user,
            db_session=db_session,
            explicit_locale="en-US",
            accept_language="zh-CN",
        )

    assert result == "stream"
    _, kwargs = mock_create_response.call_args
    assert kwargs["heartbeat_interval"] == leader_api.HEARTBEAT_INTERVAL
    assert kwargs["max_duration"] == leader_api.LEADER_SSE_MAX_DURATION
    assert filter_mock.with_for_update.called
    mock_create_session.assert_called_once_with(
        db_session=db_session,
        conversation_id=1,
        message="test",
        assessment_threshold=60,
        system_prompt_addition=None,
        locale="en-US",
        auto_commit=False,
    )
    assert conversation.default_locale == "en-US"


@pytest.mark.asyncio
async def test_start_leader_workflow_rejects_invalid_explicit_locale_before_side_effects():
    user = MagicMock(id=1, preferred_locale="zh-CN")
    conversation = MagicMock(user_id=1, default_locale="zh-CN")
    db_session = MagicMock()
    db_session.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = conversation

    with patch("api.leader_api.create_leader_session") as mock_create_session:
        with pytest.raises(leader_api.HTTPException) as exc_info:
            await leader_api._start_leader_workflow(
                conversation_id=1,
                message="test",
                file_ids=[],
                user=user,
                db_session=db_session,
                explicit_locale="fr-FR",
            )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "UNSUPPORTED_LOCALE"
    assert conversation.default_locale == "zh-CN"
    mock_create_session.assert_not_called()


@pytest.mark.asyncio
async def test_start_leader_workflow_rejects_missing_model_before_persistent_side_effects():
    user = MagicMock(id=1, preferred_locale="zh-CN")
    conversation = MagicMock(user_id=1, default_locale="zh-CN", model_override="disabled-model")
    db_session = MagicMock()
    db_session.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = conversation

    with patch(
        "api.leader_api.resolve_model_info",
        side_effect=LLMConfigurationError("LLM model 'disabled-model' is not configured in the admin database"),
    ), patch("api.leader_api.create_leader_session") as mock_create_session, \
         patch("api.leader_api.Message.create_normal_message") as mock_create_message:
        with pytest.raises(leader_api.HTTPException) as exc_info:
            await leader_api._start_leader_workflow(
                conversation_id=1,
                message="test",
                file_ids=[],
                user=user,
                db_session=db_session,
            )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["code"] == "LLM_NOT_CONFIGURED"
    mock_create_session.assert_not_called()
    mock_create_message.assert_not_called()
    db_session.add.assert_not_called()
    db_session.flush.assert_not_called()
    db_session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_existing_session_locale_overrides_workflow_argument():
    session = MagicMock(id=88, locale="en-US")
    captured_state = {}

    async def stream_events(_graph, state):
        captured_state.update(state)
        if False:
            yield None

    streamer = MagicMock()
    streamer.astream_graph_events = stream_events

    with patch("db.db.get", return_value=session), \
         patch("leader.langgraph_entry._initialize_services", new_callable=AsyncMock), \
         patch("leader.langgraph_entry.DecisionRunService") as decision_run_service, \
         patch("leader.langgraph_entry.create_leader_session") as create_session, \
         patch("leader.langgraph_entry.create_leader_workflow_graph", return_value=MagicMock()), \
         patch("leader.langgraph_entry.SSEStreamer", return_value=streamer), \
         patch("leader.langgraph_entry.ensure_terminal_state_sync"):
        events = [event async for event in langgraph_entry.async_run_leader_workflow(
            conversation_id=1,
            message="test",
            history=[],
            config={},
            locale="zh-CN",
            existing_session_id=88,
        )]

        decision_run_service.return_value.mark_started.assert_called_once_with(88, stage='assessment')

    assert captured_state["locale"] == "en-US"
    assert events == [{
        "type": "done",
        "session_id": 88,
        "message_key": "leader.status.done",
        "message_params": {},
        "message": "Workflow completed",
    }]
    create_session.assert_not_called()


def test_stale_session_timeout_cannot_expire_a_valid_sse_workflow(monkeypatch):
    monkeypatch.setattr(leader_api, "LEADER_SSE_MAX_DURATION", 3600)
    monkeypatch.setattr(leader_api, "STALE_SESSION_TIMEOUT_MINUTES", 30)
    monkeypatch.setattr(leader_api, "STALE_SESSION_GRACE_SECONDS", 300)

    assert leader_api._effective_stale_session_timeout_minutes() == 65
