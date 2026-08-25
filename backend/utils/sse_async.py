"""
SSE 流式响应辅助工具

提供 SSE（Server-Sent Events）流式响应的异步组件，包括：
- SSE 格式化异步生成器
- 心跳并发处理
- StreamingResponse 构建
"""
import asyncio
import json
import logging
import time
from typing import AsyncGenerator, Dict, Any

from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)

_detached_event_tasks: set[asyncio.Task] = set()


def _keep_event_producer_running(task: asyncio.Task) -> None:
    """保留提前关闭的 SSE 生产器，直到其完成业务收尾。"""
    _detached_event_tasks.add(task)

    def _on_done(done_task: asyncio.Task) -> None:
        _detached_event_tasks.discard(done_task)
        try:
            done_task.result()
        except asyncio.CancelledError:
            logger.info("[SSE] Detached event producer was cancelled")
        except Exception:
            logger.exception("[SSE] Detached event producer failed")

    task.add_done_callback(_on_done)

# 默认心跳间隔（秒）
DEFAULT_HEARTBEAT_INTERVAL = 30

# SSE 最大连接时长（秒），超过后强制关闭
MAX_SSE_DURATION = 600  # 10 分钟


async def sse_with_heartbeat(
    events: AsyncGenerator[Dict, None],
    interval: float = DEFAULT_HEARTBEAT_INTERVAL,
    heartbeat_event: Dict = None,
    max_duration: float = MAX_SSE_DURATION,
    detach_on_disconnect: bool = True,
) -> AsyncGenerator[str, None]:
    """带心跳和超时保护的 SSE 流

    使用 asyncio.create_task 并发发送心跳事件，保持连接活跃。
    超过 max_duration 后强制关闭连接并发送超时错误事件。

    Args:
        events: 异步事件生成器
        interval: 心跳间隔（秒）
        heartbeat_event: 心跳事件内容，默认 {"type": "heartbeat", "timestamp": ...}
        max_duration: 最大连接时长（秒），默认 600s
        detach_on_disconnect: 客户端断开后是否让事件生产器继续完成业务收尾

    Yields:
        SSE 格式字符串（含心跳事件）
    """
    if heartbeat_event is None:
        heartbeat_event = {"type": "heartbeat"}

    event_queue: asyncio.Queue = asyncio.Queue()
    stop_flag = asyncio.Event()
    client_active = asyncio.Event()
    client_active.set()

    async def heartbeat_producer():
        """心跳生产者：定时发送心跳事件"""
        while not stop_flag.is_set():
            await asyncio.sleep(interval)
            if not stop_flag.is_set():
                heartbeat = dict(heartbeat_event)
                heartbeat["timestamp"] = time.time()
                await event_queue.put(heartbeat)
                logger.debug("[SSE Heartbeat] Sending ping")

    async def event_producer():
        """事件生产者：从原始生成器读取事件"""
        try:
            async for event in events:
                if client_active.is_set():
                    await event_queue.put(event)
        except Exception as e:
            logger.error(f"[SSE] Event producer failed: {e}", exc_info=True)
            await event_queue.put({"type": "error", "message": str(e)})
        finally:
            stop_flag.set()
            logger.debug("[SSE] Event producer finished")

    # 启动并发任务
    heartbeat_task = asyncio.create_task(heartbeat_producer())
    event_task = asyncio.create_task(event_producer())
    start_time = time.time()
    wait_for_event_task = False

    try:
        while not stop_flag.is_set() or not event_queue.empty():
            # 检查最大时长
            elapsed = time.time() - start_time
            if elapsed > max_duration:
                logger.warning("[SSE] Max duration (%ds) exceeded after %.1fs, forcing close", max_duration, elapsed)
                yield f"event: message\ndata: {json.dumps({'type': 'error', 'message': '请求超时，请重试'}, ensure_ascii=False)}\n\n"
                break

            try:
                remaining = max_duration - elapsed
                event = await asyncio.wait_for(event_queue.get(), timeout=min(1.0, remaining))
                yield f"event: message\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

                # 检查是否是终止事件
                if event.get("type") == "done" or event.get("type") == "error":
                    stop_flag.set()
                    wait_for_event_task = True
                    break
            except asyncio.TimeoutError:
                continue
        else:
            wait_for_event_task = True
    except asyncio.CancelledError:
        logger.info("[SSE] Client disconnected")
        stop_flag.set()
    finally:
        client_active.clear()
        stop_flag.set()
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass

        if event_task.done() or wait_for_event_task:
            await event_task
        elif not detach_on_disconnect:
            event_task.cancel()
            try:
                await event_task
            except asyncio.CancelledError:
                pass
            logger.info("[SSE] Event producer cancelled after stream closed")
        else:
            _keep_event_producer_running(event_task)
            logger.info("[SSE] Event producer continues after stream closed")
        logger.debug("[SSE] All producers stopped")


def create_sse_streaming_response(
    event_generator: AsyncGenerator[Dict, None],
    heartbeat_interval: float = DEFAULT_HEARTBEAT_INTERVAL,
    heartbeat_event: Dict = None,
    max_duration: float = MAX_SSE_DURATION,
    detach_on_disconnect: bool = True,
) -> StreamingResponse:
    """创建 FastAPI SSE StreamingResponse

    将异步事件生成器包装为完整的 SSE 响应，包括心跳机制和超时保护。

    Args:
        event_generator: 异步事件生成器，yield dict 格式的事件
        heartbeat_interval: 心跳间隔（秒）
        heartbeat_event: 心跳事件内容
        max_duration: 最大连接时长（秒）
        detach_on_disconnect: 客户端断开后是否让事件生成器继续完成业务收尾

    Returns:
        FastAPI StreamingResponse 对象，media_type='text/event-stream'
    """
    return StreamingResponse(
        sse_with_heartbeat(
            event_generator,
            heartbeat_interval,
            heartbeat_event,
            max_duration,
            detach_on_disconnect,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive"
        }
    )
