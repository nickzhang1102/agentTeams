import asyncio
import threading

import pytest

from leader.sse_streamer import SSEStreamer, _cleanup_queue, _get_or_create_queue, push_sse_event


def test_push_sse_event_delivers_from_worker_thread():
    """子任务线程推送的实时事件必须能进入 async 队列。"""

    async def run_test():
        session_id = 99901
        queue = _get_or_create_queue(session_id)
        payload = {"type": "subtask_started", "session_id": session_id, "subtask_id": "subtask_1"}

        worker = threading.Thread(target=lambda: push_sse_event(session_id, payload))
        worker.start()

        received = await asyncio.wait_for(queue.get(), timeout=1)
        worker.join(timeout=1)
        _cleanup_queue(session_id)

        assert received == payload

    asyncio.run(run_test())


@pytest.mark.asyncio
async def test_astream_graph_events_propagates_graph_failure():
    """图异常不能被降级成正常结束，否则外层会确认计费。"""

    class FailingGraph:
        async def astream_events(self, _state, version):
            if False:
                yield None
            raise RuntimeError("graph boom")

    streamer = SSEStreamer(session_id=99902)

    with pytest.raises(RuntimeError, match="graph boom"):
        async for _event in streamer.astream_graph_events(FailingGraph(), {}):
            pass
