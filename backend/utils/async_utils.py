"""
异步执行工具

提供安全的异步协程执行机制，处理事件循环冲突问题。
"""
import asyncio
import concurrent.futures
import logging

logger = logging.getLogger(__name__)


def safe_async_run(coro):
    """
    安全执行异步协程，处理事件循环冲突

    在以下场景中正常工作：
    1. 无事件循环：创建新事件循环执行
    2. 有运行中的事件循环：在新线程中执行（避免冲突）

    Args:
        coro: 异步协程对象

    Returns:
        协程的返回值

    Raises:
        Exception: 协程执行中的异常
    """
    try:
        # 尝试获取当前运行的事件循环
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # 场景1：没有运行中的事件循环，直接使用 asyncio.run()
        logger.debug("No running event loop, using asyncio.run()")
        return asyncio.run(coro)
    else:
        # 场景2：已有运行中的事件循环
        # 在新线程中执行，避免 "This event loop is already running" 错误
        logger.debug(
            "Event loop already running, executing in separate thread"
        )

        def run_in_new_loop():
            """在新线程中创建新事件循环并执行协程"""
            return asyncio.run(coro)

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(run_in_new_loop)
            return future.result()


