"""
SSE Streamer - LangGraph streaming → SSE 适配器

将 LangGraph streaming events 转换为 SSE 事件格式
兼容现有 SSE 协议
"""
import asyncio
import json
import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import Dict, Generator, Any, List

from .workflow_state import LeaderWorkflowState

logger = logging.getLogger(__name__)

# ==================== 后台任务注册表 ====================
# SSE 断开后，LangGraph 任务继续在后台运行
# key: session_id, value: _BackgroundTask
_background_tasks: Dict[int, '_BackgroundTask'] = {}


@dataclass
class _BackgroundTask:
    """独立于 SSE 连接运行的 LangGraph 后台任务"""
    session_id: int
    task: asyncio.Task
    created_at: float


def register_background_task(session_id: int, task: asyncio.Task) -> None:
    """注册后台任务，SSE 断开后继续运行"""
    _bg = _BackgroundTask(session_id=session_id, task=task, created_at=time.time())
    _background_tasks[session_id] = _bg
    task.add_done_callback(lambda t: _on_background_task_done(session_id, t))
    logger.info(f"[BG] Registered background task for session {session_id}")


def is_background_task_running(session_id: int) -> bool:
    """检查后台任务是否仍在运行"""
    bg = _background_tasks.get(session_id)
    return bg is not None and not bg.task.done()


def cancel_background_task(session_id: int) -> bool:
    """取消指定 session 在**本进程**中的后台任务（删除会话联动停止用）

    asyncio.Task.cancel() 会向 LangGraph 工作流注入 CancelledError，使其尽快退出，
    立即停止 token 消耗。局限：仅对当前进程内注册的任务有效；
    多 worker 部署下后台任务可能在其它进程，需配合 DB 的 stop_requested
    在下一检查点停止，并由「session 缺失时优雅降级」兜底。
    """
    bg = _background_tasks.get(session_id)
    if bg is None or bg.task.done():
        return False
    bg.task.cancel()
    logger.info(f"[BG] Session {session_id}: 已请求取消后台任务（会话删除联动）")
    return True


def _on_background_task_done(session_id: int, task: asyncio.Task) -> None:
    """后台任务完成回调"""
    _background_tasks.pop(session_id, None)
    try:
        task.result()
        logger.info(f"[BG] Session {session_id} task completed successfully")
    except asyncio.CancelledError:
        logger.info(f"[BG] Session {session_id} task cancelled")
    except Exception as e:
        logger.error(f"[BG] Session {session_id} task failed: {e}")
    # 确保终态（在独立线程中执行，避免阻塞事件循环）
    try:
        from .terminal_state import ensure_terminal_state_sync
        threading.Thread(target=ensure_terminal_state_sync, args=(session_id,), daemon=True).start()
    except Exception as e:
        logger.error(f"[BG] Failed to ensure terminal state for session {session_id}: {e}")


@dataclass
class _RealtimeEventChannel:
    """跨线程安全投递的实时事件通道。"""

    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue


# 全局事件队列：节点执行期间实时推送事件，streamer 读取并 yield
# key: session_id, value: _RealtimeEventChannel
_realtime_event_queues: Dict[int, _RealtimeEventChannel] = {}


def push_sse_event(session_id: int, event: Dict) -> None:
    """节点执行期间实时推送 SSE 事件

    在 workflow_nodes 中调用，事件立即进入队列，
    不等节点结束才通过 sse_events 返回。

    Args:
        session_id: LeaderSession ID
        event: SSE 事件字典
    """
    channel = _realtime_event_queues.get(session_id)
    if channel is not None:
        try:
            channel.loop.call_soon_threadsafe(channel.queue.put_nowait, event)
        except RuntimeError:
            logger.warning(f"Realtime queue loop is closed for session {session_id}, dropping event {event.get('type')}")
        except Exception:
            logger.warning(f"Failed to push realtime event for session {session_id}")
    else:
        logger.debug(f"No realtime queue for session {session_id}, event dropped: {event.get('type')}")


def _get_or_create_queue(session_id: int):
    """获取或创建 session 的实时事件队列"""
    if session_id not in _realtime_event_queues:
        loop = asyncio.get_running_loop()
        _realtime_event_queues[session_id] = _RealtimeEventChannel(
            loop=loop,
            queue=asyncio.Queue(),
        )
    return _realtime_event_queues[session_id].queue


def _cleanup_queue(session_id: int) -> None:
    """清理 session 的事件队列"""
    _realtime_event_queues.pop(session_id, None)


# SSE 事件类型定义（兼容现有协议 + roadmap §4.4 补齐 + task orchestration）
SSE_EVENT_TYPES = {
    # 需求评估阶段
    "leader_thinking": {"phase", "content", "content_locale", "message_key", "message_params", "message"},
    "assessment_result": {"score", "details", "passed", "risk_level", "content_locale"},
    "leader_question": {"questions", "content_locale"},

    # 团队组建阶段
    "team_forming": {"phase", "content", "content_locale", "selected_agents", "message_key", "message_params", "message"},
    "team_ready": {"team", "content_locale"},

    # Agent 执行阶段
    "agent_status": {"agent_id", "agent_name", "status", "content"},
    "agent_result": {"agent_id", "agent_name", "content", "content_locale", "summary", "structured_report", "evidence_map", "status", "tool_calls"},
    "agent_error": {"agent_id", "agent_name", "error"},
    "execution_status": {"phase", "content", "message_key", "message_params", "message"},
    "execution_complete": {"content", "message_key", "message_params", "message"},

    # 汇总阶段
    "leader_summarizing": {"content", "message_key", "message_params", "message"},
    "final_report": {"id", "report", "content_locale", "summary", "structured_report", "evidence_map", "total_time"},

    # 流程控制
    "execution_stopped": {"reason", "message_key", "message_params", "message"},
    "error": {"message_key", "message_params", "message"},
    "done": {"session_id", "message_key", "message_params", "message"},

    # === 任务编排事件（2026-06-10-agent-step-orchestration）===
    "task_decomposition": {"agent_id", "agent_name", "subtasks"},
    "subtask_started": {"agent_id", "agent_name", "subtask_id", "goal", "tools"},
    "subtool_call": {"agent_id", "agent_name", "subtask_id", "tool_name", "tool_input"},
    "subtask_result": {"agent_id", "agent_name", "subtask_id", "result", "evidence"},
    "subtask_completed": {"agent_id", "agent_name", "subtask_id", "goal", "status"},
    "task_adjusted": {"agent_id", "agent_name", "action", "reason", "new_subtasks"},
}


class SSEStreamer:
    """LangGraph streaming → SSE 适配器

    负责将 LangGraph astream_events 输出转换为 SSE 事件格式
    """

    def __init__(self, session_id: int = None):
        """初始化 SSE Streamer

        Args:
            session_id: LeaderSession ID（用于 SSE 事件）
        """
        self.session_id = session_id

    def langgraph_event_to_sse(self, event: Dict) -> List[Dict]:
        """将 LangGraph streaming event 转换为 SSE 事件列表

        LangGraph event 格式:
        {
            "event": "on_chain_start" | "on_chain_end" | "on_tool_start" | "on_tool_end" | ...,
            "name": "node_name" | "tool_name",
            "data": {...}
        }

        Args:
            event: LangGraph streaming event

        Returns:
            SSE 格式事件字典列表（一个节点可能产生多个 SSE 事件）
        """
        event_type = event.get("event", "")
        node_name = event.get("name", "")
        data = event.get("data", {})

        # === on_chain_start：节点开始执行 ===
        if event_type == "on_chain_start":
            # 跳过内部节点和条件路由函数
            if node_name in ("__start__",) or node_name.startswith("route_after"):
                return []
            # 不生成框架级 leader_thinking 事件——节点自身会发送有实质内容的事件
            return []

        # === on_chain_end：节点执行完成 ===
        if event_type == "on_chain_end":
            # 不转发 state 里的 sse_events：各节点在产生事件时已通过
            # _emit/push_sse_event 实时推送，而 state.sse_events 是"历史累计值"，
            # 在每个节点结束（含图级 LangGraph 链结束）时重复转发会造成
            # 同一事件被投递 O(节点数) 次（前端被迫做客户端去重）。
            # 事件只走实时通道；此分支仅保留占位以说明设计。
            return []

        # === on_tool_start：工具开始调用（Agent 执行） ===
        if event_type == "on_tool_start":
            agent_id = self._extract_agent_id(node_name, data)
            return [{
                "type": "agent_status",
                "session_id": self.session_id,
                "agent_id": agent_id,
                "agent_name": node_name,
                "status": "started",
                "content": f"开始调用工具 {node_name}"
            }]

        # === on_tool_end：工具调用完成 ===
        if event_type == "on_tool_end":
            agent_id = self._extract_agent_id(node_name, data)
            output = data.get("output", "")
            return [{
                "type": "agent_result",
                "session_id": self.session_id,
                "agent_id": agent_id,
                "agent_name": node_name,
                "content": output if isinstance(output, str) else str(output),
                "status": "success",
                "tool_calls": [node_name]
            }]

        # === 其他 event 类型：忽略，避免泄露内部信息 ===
        return []

    def _extract_agent_id(self, name: str, data: Dict) -> str:
        """从 LangGraph event 提取 agent_id

        Args:
            name: event name（可能是 node name 或 tool name）
            data: event data

        Returns:
            agent_id 字符串
        """
        # 尝试从 data 提取
        if "agent_id" in data:
            return data["agent_id"]
        # 使用 name 作为 fallback
        return name or "unknown"

    def yield_sse_from_state(self, state: LeaderWorkflowState) -> Generator[Dict, None, None]:
        """从 state.sse_events 队列 yield SSE 事件

        每次节点执行后调用，清空事件队列

        Args:
            state: LangGraph 状态

        Yields:
            SSE 格式事件字典
        """
        sse_events = state.get("sse_events", [])
        for event in sse_events:
            # 确保 session_id 存在
            if "session_id" not in event:
                event["session_id"] = self.session_id
            yield event

    async def astream_graph_events(
        self,
        graph: Any,
        initial_state: LeaderWorkflowState
    ):
        """异步执行 graph 并逐事件 yield SSE（实时流式）

        双通道事件源：
        1. LangGraph on_chain_start/end 事件（节点开始/结束）
        2. 实时队列事件（节点执行期间通过 push_sse_event 推送）

        保证前端在节点执行期间就能收到进度，不等节点结束。

        Args:
            graph: Compiled LangGraph
            initial_state: 初始状态

        Yields:
            SSE 格式事件字典
        """
        session_id = self.session_id
        realtime_queue = _get_or_create_queue(session_id)

        async def _drain_langgraph():
            """从 LangGraph astream_events 读取并转换"""
            try:
                async for event in graph.astream_events(initial_state, version="v2"):
                    sse_event_list = self.langgraph_event_to_sse(event)
                    for sse_event in sse_event_list:
                        await realtime_queue.put(sse_event)
            except Exception as e:
                logger.error(f"LangGraph async streaming error: {e}")
                raise
            finally:
                # 流结束标记
                await realtime_queue.put(None)

        # 后台任务驱动 LangGraph
        lg_task = asyncio.create_task(_drain_langgraph())

        try:
            while True:
                event = await realtime_queue.get()
                if event is None:
                    break
                yield event
            # _drain_langgraph 的异常必须回到 workflow 入口，由入口统一失败和发 error。
            await lg_task
        finally:
            _cleanup_queue(session_id)
            if not lg_task.done():
                # SSE 断开但任务仍在运行 — 分离而非取消
                # 后台任务会继续执行，结果持久化到 DB
                logger.info(
                    f"[SSE] Session {session_id}: SSE disconnected, "
                    f"LangGraph task continues in background"
                )
                register_background_task(session_id, lg_task)
            # 不再 cancel lg_task

    def stream_graph_events(
        self,
        graph: Any,
        initial_state: LeaderWorkflowState
    ) -> Generator[Dict, None, None]:
        """执行 graph 并 yield SSE 事件（同步包装异步，实时流式）

        使用 Queue 桥接 async→sync，保证事件产生后立即 yield，
        避免收集所有事件后再返回导致前端显示时序错乱。

        Args:
            graph: Compiled LangGraph
            initial_state: 初始状态

        Yields:
            SSE 格式事件字典
        """
        import asyncio
        import queue
        import threading

        event_queue: queue.Queue = queue.Queue()

        async def _stream_async():
            """异步执行图，事件实时放入队列

            委托 astream_graph_events（生产路径）：实时队列 + LangGraph 事件
            双通道在那一层统一桥接，避免本同步包装自建一条只消费
            state.sse_events 的孤立通道（节点 _emit 事件对其不可见）。
            """
            try:
                async for sse_event in self.astream_graph_events(graph, initial_state):
                    event_queue.put(sse_event)
            except Exception as e:
                # 原始异常仅入日志；SSE 通道只暴露通用文案，避免内部细节外泄
                logger.error(f"LangGraph streaming error: {e}", exc_info=True)
                event_queue.put({
                    "type": "error",
                    "session_id": self.session_id,
                    "message": "处理请求时发生内部错误，请稍后重试"
                })
            finally:
                event_queue.put(None)  # 流结束信号

        # 后台线程执行异步图，主线程实时 yield
        # 捕获调用方 contextvars（NodeServices），在后台线程中恢复，
        # 否则图节点内 get_services() 拿不到服务实例（contextvars 不自动跨线程）。
        import contextvars
        worker_ctx = contextvars.copy_context()
        thread = threading.Thread(
            target=lambda: worker_ctx.run(asyncio.run, _stream_async()),
            daemon=True,
        )
        thread.start()

        try:
            while True:
                event = event_queue.get()
                if event is None:
                    break
                yield event
        finally:
            thread.join(timeout=5)
