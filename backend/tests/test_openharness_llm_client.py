"""
Tests for OpenHarnessLLMClient
"""
import pytest
import asyncio
from unittest.mock import Mock, MagicMock, patch

from services.harness.openharness_llm_client import OpenHarnessLLMClient
from openharness.api.client import ApiMessageRequest, ApiTextDeltaEvent, ApiMessageCompleteEvent
from openharness.engine.messages import ConversationMessage


@pytest.fixture
def mock_llm_service():
    """创建 Mock LLM Service"""
    service = Mock()
    service.model = "test-model"

    # 模拟流式响应
    def mock_call_stream(*args, **kwargs):
        # 返回文本块
        yield {"type": "text", "content": "Hello "}
        yield {"type": "text", "content": "World!"}
        yield {"type": "done"}

    service.call_stream = mock_call_stream
    return service


def test_client_initialization(mock_llm_service):
    """测试客户端初始化"""
    client = OpenHarnessLLMClient(mock_llm_service)

    assert client.llm_service is mock_llm_service
    assert client.model == "test-model"


def test_client_custom_model(mock_llm_service):
    """测试自定义模型名称"""
    client = OpenHarnessLLMClient(mock_llm_service, model="custom-model")

    assert client.model == "custom-model"


@pytest.mark.asyncio
async def test_stream_message_basic(mock_llm_service):
    """测试基本流式消息"""
    client = OpenHarnessLLMClient(mock_llm_service)

    # 构建请求（使用 from_user_text 方法）
    request = ApiMessageRequest(
        model="test-model",
        messages=[ConversationMessage.from_user_text("Hello")],
        system_prompt="You are a helpful assistant.",
        max_tokens=100
    )

    # 收集流式事件
    events = []
    async for event in client.stream_message(request):
        events.append(event)

    # 验证事件类型
    text_events = [e for e in events if isinstance(e, ApiTextDeltaEvent)]
    complete_events = [e for e in events if isinstance(e, ApiMessageCompleteEvent)]

    assert len(text_events) == 2
    assert len(complete_events) == 1

    # 验证文本内容
    full_text = "".join(e.text for e in text_events)
    assert full_text == "Hello World!"

    # 验证完成事件
    complete_event = complete_events[0]
    assert complete_event.stop_reason == "end_turn"
    assert complete_event.message is not None


@pytest.mark.asyncio
async def test_convert_messages(mock_llm_service):
    """测试消息格式转换"""
    client = OpenHarnessLLMClient(mock_llm_service)

    # 测试简单文本消息（使用 from_user_text 方法）
    messages = [
        ConversationMessage.from_user_text("Hello"),
        ConversationMessage.from_user_text("Hi there!")
    ]
    # 修改第二条消息的角色为 assistant
    messages[1].role = "assistant"

    converted = client._convert_messages(messages)

    assert len(converted) == 2
    assert converted[0]["role"] == "user"
    assert converted[0]["content"] == "Hello"
    assert converted[1]["role"] == "assistant"
    assert converted[1]["content"] == "Hi there!"


def test_extract_agent_name(mock_llm_service):
    """测试 Agent 名称提取"""
    client = OpenHarnessLLMClient(mock_llm_service)

    # 测试带冒号的系统提示
    name1 = client._extract_agent_name("Cardiology Expert: You are a heart specialist.")
    assert name1 == "Cardiology Expert"

    # 测试空系统提示
    name2 = client._extract_agent_name(None)
    assert name2 == "default"

    # 测试无冒号的系统提示
    name3 = client._extract_agent_name("You are a helpful assistant.")
    assert name3 == "default"


@pytest.mark.asyncio
async def test_stream_message_with_retry(mock_llm_service):
    """测试重试事件处理"""
    # 创建带重试的 Mock
    def mock_call_stream_with_retry(*args, **kwargs):
        # 第一次尝试失败
        yield {"type": "api_retry", "attempt": 1, "max_attempts": 3, "message": "Retrying..."}
        # 第二次尝试成功
        yield {"type": "text", "content": "Success"}
        yield {"type": "done"}

    mock_llm_service.call_stream = mock_call_stream_with_retry

    client = OpenHarnessLLMClient(mock_llm_service)

    request = ApiMessageRequest(
        model="test-model",
        messages=[ConversationMessage.from_user_text("Test")],
        max_tokens=100
    )

    # 收集事件
    events = []
    async for event in client.stream_message(request):
        events.append(event)

    # 验证包含重试事件
    from openharness.api.client import ApiRetryEvent
    retry_events = [e for e in events if isinstance(e, ApiRetryEvent)]
    assert len(retry_events) == 1
    assert retry_events[0].attempt == 1


@pytest.mark.asyncio
async def test_stream_message_error(mock_llm_service):
    """测试错误事件处理"""
    # 创建抛出错误的 Mock
    def mock_call_stream_error(*args, **kwargs):
        yield {"type": "error", "message": "API Error"}

    mock_llm_service.call_stream = mock_call_stream_error

    client = OpenHarnessLLMClient(mock_llm_service)

    request = ApiMessageRequest(
        model="test-model",
        messages=[ConversationMessage.from_user_text("Test")],
        max_tokens=100
    )

    # 验证抛出异常
    with pytest.raises(Exception, match="API Error"):
        async for _ in client.stream_message(request):
            pass