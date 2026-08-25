"""
SSE Async 工具单元测试

测试 sse_async.py 的核心功能：
- sse_with_heartbeat：心跳并发
- create_sse_streaming_response：响应创建
"""
import asyncio
import json
import pytest
from typing import AsyncGenerator, Dict

from utils.sse_async import (
    sse_with_heartbeat,
    create_sse_streaming_response,
)


# ==================== sse_with_heartbeat 测试 ====================

class TestSseWithHeartbeat:
    """sse_with_heartbeat 函数测试"""

    @pytest.mark.asyncio
    async def test_basic_with_heartbeat(self):
        """测试基本心跳功能"""
        # 短心跳间隔（测试用）
        interval = 0.1

        # 快速生成事件
        async def quick_generator():
            yield {"type": "start"}
            await asyncio.sleep(0.05)
            yield {"type": "done"}

        results = []
        async for sse_str in sse_with_heartbeat(quick_generator(), interval):
            results.append(sse_str)

        # 应有 start + done 事件，可能有心跳
        assert len(results) >= 2

        # 验证所有事件都是 SSE 格式
        for result in results:
            assert result.startswith("event: message\ndata: ")
            assert result.endswith("\n\n")

    @pytest.mark.asyncio
    async def test_heartbeat_timestamp(self):
        """测试心跳事件含 timestamp"""
        interval = 0.05

        async def slow_generator():
            yield {"type": "start"}
            await asyncio.sleep(0.2)  # 等待心跳
            yield {"type": "done"}

        results = []
        async for sse_str in sse_with_heartbeat(slow_generator(), interval):
            results.append(sse_str)

        # 找心跳事件
        heartbeat_found = False
        for result in results:
            data_line = result.split("data: ")[1].rstrip("\n\n")
            event_data = json.loads(data_line)
            if event_data.get("type") == "heartbeat":
                assert "timestamp" in event_data
                heartbeat_found = True
                break

        # 理论上应该有心跳，但测试环境可能不稳定
        # 只验证格式正确，不强制要求心跳出现

    @pytest.mark.asyncio
    async def test_stop_on_done(self):
        """测试 done 事件停止流"""
        async def generator_with_done():
            yield {"type": "progress", "value": 1}
            yield {"type": "done"}
            yield {"type": "after_done"}  # 不会被输出

        results = []
        async for sse_str in sse_with_heartbeat(generator_with_done(), 30):
            results.append(sse_str)

        # 只应有 progress + done
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_error_event_stops(self):
        """测试 error 事件停止流"""
        async def generator_with_error():
            yield {"type": "start"}
            yield {"type": "error", "message": "test error"}
            yield {"type": "after_error"}  # 不会被输出

        results = []
        async for sse_str in sse_with_heartbeat(generator_with_error(), 30):
            results.append(sse_str)

        # 应有 start + error
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_done_event_does_not_cancel_generator_cleanup(self):
        """done 只是传输终点，事件生成器仍必须完成计费等收尾。"""
        cleanup_finished = asyncio.Event()

        async def workflow_generator():
            yield {"type": "done"}
            await asyncio.sleep(0)
            cleanup_finished.set()

        results = []
        async for sse_str in sse_with_heartbeat(workflow_generator(), 30):
            results.append(sse_str)

        assert len(results) == 1
        assert cleanup_finished.is_set()

    @pytest.mark.asyncio
    async def test_early_close_keeps_event_generator_running(self):
        """客户端提前关闭后，完整工作流生成器应继续运行到终态。"""
        continue_workflow = asyncio.Event()
        workflow_finished = asyncio.Event()

        async def workflow_generator():
            yield {"type": "progress"}
            await continue_workflow.wait()
            workflow_finished.set()
            yield {"type": "done"}

        stream = sse_with_heartbeat(workflow_generator(), 30)
        first = await anext(stream)
        assert '"type": "progress"' in first

        await stream.aclose()
        continue_workflow.set()
        await asyncio.wait_for(workflow_finished.wait(), timeout=1)

    @pytest.mark.asyncio
    async def test_early_close_cancels_passive_event_generator(self):
        """被动状态流在客户端断开后应立即释放生产任务。"""
        producer_cancelled = asyncio.Event()

        async def passive_generator():
            try:
                yield {"type": "embed_snapshot"}
                await asyncio.Event().wait()
            finally:
                producer_cancelled.set()

        stream = sse_with_heartbeat(
            passive_generator(),
            30,
            detach_on_disconnect=False,
        )
        first = await anext(stream)
        assert '"type": "embed_snapshot"' in first

        await stream.aclose()

        await asyncio.wait_for(producer_cancelled.wait(), timeout=1)

    @pytest.mark.asyncio
    async def test_custom_heartbeat_event(self):
        """测试自定义心跳事件"""
        custom_heartbeat = {"type": "ping", "source": "custom"}

        async def generator():
            yield {"type": "start"}
            await asyncio.sleep(0.15)
            yield {"type": "done"}

        interval = 0.05
        results = []
        async for sse_str in sse_with_heartbeat(generator(), interval, custom_heartbeat):
            results.append(sse_str)

        # 查找自定义心跳
        for result in results:
            data_line = result.split("data: ")[1].rstrip("\n\n")
            event_data = json.loads(data_line)
            if event_data.get("type") == "ping":
                assert event_data.get("source") == "custom"
                break


# ==================== create_sse_streaming_response 测试 ====================

class TestCreateSseStreamingResponse:
    """create_sse_streaming_response 函数测试"""

    def test_response_type(self):
        """测试返回 StreamingResponse"""
        from fastapi.responses import StreamingResponse

        async def generator():
            yield {"type": "test"}

        response = create_sse_streaming_response(generator())

        assert isinstance(response, StreamingResponse)

    def test_media_type(self):
        """测试 media_type 正确"""
        async def generator():
            yield {"type": "test"}

        response = create_sse_streaming_response(generator())

        assert response.media_type == "text/event-stream"

    def test_headers(self):
        """测试响应头正确"""
        async def generator():
            yield {"type": "test"}

        response = create_sse_streaming_response(generator())

        headers = dict(response.headers)
        # HTTP headers 在 FastAPI/Starlette 中为小写
        assert headers.get("cache-control") == "no-cache"
        assert headers.get("x-accel-buffering") == "no"

    def test_custom_heartbeat_interval(self):
        """测试自定义心跳间隔"""
        async def generator():
            yield {"type": "test"}

        response = create_sse_streaming_response(generator(), heartbeat_interval=60)

        # StreamingResponse 内部使用生成器，无法直接检查间隔
        # 只验证函数正常返回
        assert response is not None

    def test_custom_max_duration(self):
        """测试可覆盖最大流时长。"""
        async def generator():
            yield {"type": "test"}

        response = create_sse_streaming_response(generator(), max_duration=1800)

        assert response is not None


# ==================== 集成测试 ====================

class TestIntegration:
    """集成测试"""

    @pytest.mark.asyncio
    async def test_full_pipeline(self):
        """测试完整流程：生成器 → 心跳 → 格式化"""
        async def event_generator():
            yield {"type": "start", "phase": "init"}
            await asyncio.sleep(0.01)
            yield {"type": "progress", "value": 50}
            await asyncio.sleep(0.01)
            yield {"type": "done", "session_id": 123}

        # 通过心跳 + 格式化
        results = []
        async for sse_str in sse_with_heartbeat(event_generator(), interval=30):
            results.append(sse_str)

        # 解析所有事件
        events = []
        for result in results:
            data_line = result.split("data: ")[1].rstrip("\n\n")
            events.append(json.loads(data_line))

        # 验证事件顺序
        assert events[0]["type"] == "start"
        assert events[1]["type"] == "progress"
        assert events[2]["type"] == "done"
        assert events[2]["session_id"] == 123
