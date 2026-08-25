"""In-process scheduling backed by durable PostgreSQL translation leases."""
from __future__ import annotations

import asyncio
import logging

from .cache import find_recoverable_translation_ids


logger = logging.getLogger(__name__)

TRANSLATION_RECOVERY_SECONDS = 30
TRANSLATION_MAX_CONCURRENCY = 2

_active_translation_tasks: set[asyncio.Task] = set()
_translation_tasks_by_id: dict[int, asyncio.Task] = {}
_recovery_monitor_task: asyncio.Task | None = None
_translation_semaphore = asyncio.Semaphore(TRANSLATION_MAX_CONCURRENCY)


async def _run_translation_async(translation_id: int) -> None:
    from .worker import run_translation_worker

    await asyncio.to_thread(run_translation_worker, translation_id)


async def _run_translation_with_limit(translation_id: int) -> None:
    async with _translation_semaphore:
        await _run_translation_async(translation_id)


def schedule_translation(translation_id: int) -> asyncio.Task:
    """Schedule a translation id; the database lease decides execution owner."""
    existing = _translation_tasks_by_id.get(translation_id)
    if existing is not None and not existing.done():
        return existing
    task = asyncio.create_task(
        _run_translation_with_limit(translation_id),
        name=f'content-translation-{translation_id}',
    )
    _active_translation_tasks.add(task)
    _translation_tasks_by_id[translation_id] = task

    def discard(completed: asyncio.Task) -> None:
        _active_translation_tasks.discard(completed)
        if _translation_tasks_by_id.get(translation_id) is completed:
            _translation_tasks_by_id.pop(translation_id, None)

    task.add_done_callback(discard)
    return task


async def _monitor_recoverable_translations() -> None:
    while True:
        try:
            for translation_id in find_recoverable_translation_ids():
                schedule_translation(translation_id)
        except Exception:
            logger.warning('Translation recovery scan failed', exc_info=True)
        await asyncio.sleep(TRANSLATION_RECOVERY_SECONDS)


def start_translation_recovery_monitor() -> asyncio.Task:
    global _recovery_monitor_task
    if _recovery_monitor_task is not None and not _recovery_monitor_task.done():
        return _recovery_monitor_task
    _recovery_monitor_task = asyncio.create_task(
        _monitor_recoverable_translations(),
        name='content-translation-recovery',
    )
    _active_translation_tasks.add(_recovery_monitor_task)
    _recovery_monitor_task.add_done_callback(_active_translation_tasks.discard)
    return _recovery_monitor_task


async def shutdown_translation_tasks() -> None:
    global _recovery_monitor_task
    tasks = list(_active_translation_tasks)
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    _translation_tasks_by_id.clear()
    _recovery_monitor_task = None
