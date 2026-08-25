"""
LLMService 安全测试
"""
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

from services.llm_service import ContextWindowExceededError, LLMService


def test_context_overflow_never_drops_the_current_prompt():
    service = LLMService(api_key='test-key', model='ep-default')
    service.get_context_limit = lambda: 32768
    service.get_max_output_tokens = lambda: 4096

    with pytest.raises(ContextWindowExceededError, match='context_window_exceeded'):
        service._compress_if_needed([
            {'role': 'system', 'content': 'system'},
            {'role': 'user', 'content': 'BEGIN-PATIENT-CONTEXT\n' + ('病' * 61000) + '\nEND-PATIENT-CONTEXT'},
        ], max_tokens=4096)


def test_llm_service_initialization_log_does_not_expose_api_key(caplog):
    """初始化日志不应包含 API Key 前缀或完整值"""
    secret_key = 'sk-test-secret-value'

    with caplog.at_level(logging.INFO, logger='services.llm_service'):
        LLMService(api_key=secret_key, base_url='http://example.com', model='ep-default')

    log_text = caplog.text
    assert secret_key not in log_text
    assert secret_key[:4] not in log_text
    assert 'api_key=' not in log_text


@patch("services.llm_service.OpenAI")
def test_openai_sdk_retries_disabled(mock_openai):
    LLMService(api_key="test-key", base_url="http://example.com", model="ep-default")

    assert mock_openai.call_args.kwargs["max_retries"] == 0


@patch("services.llm_service.OpenAI")
def test_capture_usage_records_actual_sync_tokens(mock_openai):
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="完成"))],
        usage=SimpleNamespace(prompt_tokens=12, completion_tokens=5),
    )
    mock_openai.return_value.chat.completions.create.return_value = response
    service = LLMService(api_key="test-key", model="ep-default")

    with service.capture_usage() as metrics:
        result = service.call_sync("测试", max_tokens=100, max_attempts=1)

    assert result == "完成"
    assert metrics["input_tokens"] == 12
    assert metrics["output_tokens"] == 5
    assert metrics["total_tokens"] == 17
    assert metrics["call_count"] == 1
    assert metrics["failure_count"] == 0
    assert metrics["elapsed"] >= 0


@patch("services.llm_service.OpenAI")
def test_call_sync_rejects_provider_truncation_when_requested(mock_openai):
    response = SimpleNamespace(
        choices=[SimpleNamespace(
            message=SimpleNamespace(content='{"partial": true}'),
            finish_reason='length',
        )],
        usage=SimpleNamespace(prompt_tokens=12, completion_tokens=100),
    )
    mock_openai.return_value.chat.completions.create.return_value = response
    service = LLMService(api_key="test-key", model="ep-default")

    with pytest.raises(RuntimeError, match='response truncated'):
        service.call_sync(
            '测试',
            max_tokens=100,
            max_attempts=1,
            reject_truncated=True,
        )


@patch("services.llm_service.OpenAI")
def test_call_sync_allows_optional_empty_content_without_recording_failure(mock_openai, caplog):
    response = SimpleNamespace(
        choices=[SimpleNamespace(
            message=SimpleNamespace(content=''),
            finish_reason='stop',
        )],
        usage=SimpleNamespace(prompt_tokens=12, completion_tokens=0),
    )
    mock_openai.return_value.chat.completions.create.return_value = response
    service = LLMService(api_key="test-key", model="ep-default")

    with caplog.at_level(logging.INFO, logger='services.llm_service'):
        with service.capture_usage() as metrics:
            result = service.call_sync(
                '测试',
                max_tokens=100,
                max_attempts=1,
                empty_content_ok=True,
            )

    assert result == ''
    assert metrics['failure_count'] == 0
    assert 'non-fatal fallback' in caplog.text
    assert 'failed after' not in caplog.text


@patch("services.llm_service.OpenAI")
def test_capture_usage_estimates_structured_tokens(mock_openai):
    class StructuredResult(BaseModel):
        answer: str

    service = LLMService(api_key="test-key", model="ep-default")
    service._structured_client = MagicMock()
    service._structured_client.chat.completions.create.return_value = StructuredResult(answer="结构化结果")

    with service.capture_usage() as metrics:
        result = asyncio.run(service.call_structured(
            messages=[{"role": "user", "content": "请返回结构化结果"}],
            response_model=StructuredResult,
            max_tokens=100,
            max_retries=1,
        ))

    assert result.answer == "结构化结果"
    assert metrics["input_tokens"] > 0
    assert metrics["output_tokens"] > 0
    assert metrics["call_count"] == 1
    assert metrics["failure_count"] == 0


@patch("services.llm_service.OpenAI")
def test_capture_usage_isolated_between_parallel_contexts(mock_openai):
    service = LLMService(api_key="test-key", model="ep-default")

    def capture(value):
        with service.capture_usage() as metrics:
            service._record_usage(value, value + 1, 0.01)
            return dict(metrics)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = executor.map(capture, (10, 20))

    assert first["total_tokens"] == 21
    assert second["total_tokens"] == 41
