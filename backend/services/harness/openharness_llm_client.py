"""
OpenHarness LLM Client Adapter

适配现有 LLMService 到 OpenHarness SupportsStreamingMessages 接口
"""
import asyncio
import json
import logging
from typing import AsyncIterator, Any

from openharness.api.client import (
    ApiMessageRequest,
    ApiTextDeltaEvent,
    ApiMessageCompleteEvent,
    ApiRetryEvent,
    ApiStreamEvent,
    SupportsStreamingMessages,
)
from openharness.api.usage import UsageSnapshot
from openharness.engine.messages import (
    ConversationMessage,
    TextBlock,
    ToolUseBlock,
    ToolResultBlock,
    assistant_message_from_api,
)

logger = logging.getLogger(__name__)


class OpenHarnessLLMClient(SupportsStreamingMessages):
    """适配 LLMService 到 OpenHarness SupportsStreamingMessages 接口"""

    def __init__(self, llm_service, model: str = None):
        """
        初始化适配器

        Args:
            llm_service: 现有的 LLMService 实例
            model: 模型名称（可选）
        """
        self.llm_service = llm_service
        self.model = model or llm_service.model

    async def stream_message(
        self,
        request: ApiMessageRequest
    ) -> AsyncIterator[ApiStreamEvent]:
        """
        流式调用 LLM API，支持工具调用

        Args:
            request: API 请求对象

        Yields:
            ApiStreamEvent: 流式事件
        """
        # 转换 OpenHarness 消息格式到 OpenAI 格式
        openai_messages = self._convert_messages(request.messages)

        # 提取最后一条用户消息
        user_message = ""
        for msg in reversed(openai_messages):
            if msg.get("role") == "user":
                user_message = msg.get("content", "")
                break

        # 构建对话历史：system_prompt + 之前的消息（排除最后一条用户消息）
        conversation_history = []
        # 将 agent 角色定义作为 system 消息传入（最重要）
        if request.system_prompt:
            conversation_history.append({
                "role": "system",
                "content": request.system_prompt
            })
        # 添加之前的对话消息（排除 system 和最后一条 user）
        for msg in openai_messages[:-1] if len(openai_messages) > 1 else []:
            role = msg.get("role", "")
            if role in ("user", "assistant", "tool"):
                conversation_history.append(msg)

        # 转换工具定义为 OpenAI function calling 格式
        tools = self._convert_tools(request.tools) if request.tools else None
        tool_names = [t.get('function', {}).get('name', '?') for t in tools] if tools else []
        logger.info(f"stream_message: {len(request.tools) if request.tools else 0} tools in request, "
                     f"{len(tools) if tools else 0} converted for OpenAI, names={tool_names[:10]}")

        # Token 统计
        total_input_tokens = 0
        total_output_tokens = 0

        try:
            # 调用现有的 LLM 服务（同步 Generator）
            # 使用 asyncio.to_thread 在后台线程运行同步代码
            def call_sync():
                return list(self.llm_service.call_stream(
                    message=user_message,
                    conversation_history=conversation_history,
                    extra_command=None,
                    agent_name=self._extract_agent_name(request.system_prompt),
                    max_tokens=request.max_tokens,
                    tools=tools,
                    skip_agent_list=True,
                ))

            # 在后台线程执行同步调用
            chunks = await asyncio.to_thread(call_sync)

            # 处理流式响应：收集文本和工具调用
            content_parts = []
            # OpenAI 流式 tool_calls 格式：每个 delta 包含 index, id, name, arguments 片段
            tool_calls_accum = {}  # index -> {id, name, arguments}

            for chunk in chunks:
                if chunk.get("type") == "text":
                    content = chunk.get("content", "")
                    content_parts.append(content)
                    yield ApiTextDeltaEvent(text=content)

                elif chunk.get("type") == "tool_call_delta":
                    # 工具调用增量片段
                    tc = chunk.get("tool_call", {})
                    idx = tc.get("index", 0)
                    if idx not in tool_calls_accum:
                        tool_calls_accum[idx] = {
                            "id": tc.get("id", ""),
                            "name": tc.get("name", ""),
                            "arguments": "",
                        }
                    if tc.get("id"):
                        tool_calls_accum[idx]["id"] = tc["id"]
                    if tc.get("name"):
                        tool_calls_accum[idx]["name"] = tc["name"]
                    if tc.get("arguments"):
                        tool_calls_accum[idx]["arguments"] += tc["arguments"]

                elif chunk.get("type") == "api_retry":
                    yield ApiRetryEvent(
                        message=chunk.get("message", "Retrying..."),
                        attempt=chunk.get("attempt", 1),
                        max_attempts=chunk.get("max_attempts", 10),
                        delay_seconds=10.0
                    )

                elif chunk.get("type") == "usage":
                    total_input_tokens = chunk.get("input_tokens", 0)
                    total_output_tokens = chunk.get("output_tokens", 0)

                elif chunk.get("type") == "done":
                    break

                elif chunk.get("type") == "error":
                    raise Exception(chunk.get("message", "Unknown error"))

            # 构建最终消息的 content blocks
            content_blocks = []

            # 文本内容
            full_text = "".join(content_parts)
            if full_text:
                content_blocks.append(TextBlock(text=full_text))

            # 工具调用
            logger.info(f"LLM client: text_len={len(full_text)}, tool_calls={len(tool_calls_accum)}, "
                        f"tool_names={[v['name'] for v in tool_calls_accum.values()]}")
            for idx in sorted(tool_calls_accum.keys()):
                tc_data = tool_calls_accum[idx]
                try:
                    tc_input = json.loads(tc_data["arguments"]) if tc_data["arguments"] else {}
                except json.JSONDecodeError:
                    tc_input = {"raw_arguments": tc_data["arguments"]}

                content_blocks.append(ToolUseBlock(
                    id=tc_data["id"] or f"toolu_{idx}",
                    name=tc_data["name"],
                    input=tc_input,
                ))

            # 构建 ConversationMessage
            final_message = ConversationMessage(
                role="assistant",
                content=content_blocks,
            )

            # 构建使用快照
            usage = UsageSnapshot(
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
                total_tokens=total_input_tokens + total_output_tokens
            )

            # 发送完成事件
            yield ApiMessageCompleteEvent(
                message=final_message,
                usage=usage,
                stop_reason="tool_use" if tool_calls_accum else "end_turn"
            )

        except Exception as e:
            logger.error(f"OpenHarness LLM client stream error: {e}", exc_info=True)
            raise

    def _convert_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
        """
        转换 OpenHarness 工具定义为 OpenAI function calling 格式

        OpenHarness schema 格式: {"name": ..., "description": ..., "input_schema": {...}}
        OpenAI 格式: {"type": "function", "function": {"name": ..., "description": ..., "parameters": {...}}}
        """
        if not tools:
            return None

        openai_tools = []
        for tool in tools:
            # 已经是 OpenAI 格式
            if tool.get("type") == "function":
                openai_tools.append(tool)
                continue

            # OpenHarness/Anthropic 格式转换
            name = tool.get("name", "")
            description = tool.get("description", "")
            input_schema = tool.get("input_schema", tool.get("parameters", {}))

            openai_tools.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": input_schema,
                }
            })

        return openai_tools if openai_tools else None

    def _convert_messages(
        self,
        messages: list[ConversationMessage]
    ) -> list[dict[str, Any]]:
        """
        转换 OpenHarness 消息格式到 OpenAI 格式

        Args:
            messages: OpenHarness 消息列表

        Returns:
            OpenAI 格式的消息列表
        """
        openai_messages = []

        for msg in messages:
            # 使用 ConversationMessage 的 text 属性获取文本内容
            if hasattr(msg, 'text') and msg.text:
                openai_messages.append({
                    "role": msg.role,
                    "content": msg.text
                })
            # 备用：直接处理 content 列表
            elif hasattr(msg, 'content') and isinstance(msg.content, list):
                text_parts = []
                tool_calls_list = []
                tool_results = []

                for part in msg.content:
                    if isinstance(part, TextBlock):
                        text_parts.append(part.text)
                    elif isinstance(part, ToolUseBlock):
                        tool_calls_list.append({
                            "id": part.id,
                            "type": "function",
                            "function": {
                                "name": part.name,
                                "arguments": json.dumps(part.input, ensure_ascii=False)
                            }
                        })
                    elif isinstance(part, ToolResultBlock):
                        # OpenAI 格式：每条工具结果为独立的 role="tool" 消息
                        tool_results.append({
                            "role": "tool",
                            "tool_call_id": part.tool_use_id,
                            "content": part.content,
                        })

                # 工具结果：每条作为独立消息
                if tool_results:
                    openai_messages.extend(tool_results)
                    continue

                # assistant 消息（可能包含 tool_calls）
                if text_parts or not tool_calls_list:
                    openai_messages.append({
                        "role": msg.role,
                        "content": "\n".join(text_parts) if text_parts else None,
                        **({"tool_calls": tool_calls_list} if tool_calls_list else {})
                    })
                elif tool_calls_list:
                    openai_messages.append({
                        "role": msg.role,
                        "content": None,
                        "tool_calls": tool_calls_list
                    })

        return openai_messages

    def _extract_agent_name(self, system_prompt: str | None) -> str:
        """
        从系统提示中提取 Agent 名称

        Args:
            system_prompt: 系统提示

        Returns:
            Agent 名称或默认值
        """
        if not system_prompt:
            return "default"

        # 简单提取：查找第一行中的名称
        first_line = system_prompt.split("\n")[0]
        if ":" in first_line:
            return first_line.split(":")[0].strip()

        return "default"
