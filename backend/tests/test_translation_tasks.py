import asyncio

from translation import tasks


def test_schedule_translation_submits_only_translation_id(monkeypatch):
    calls = []

    async def fake_run(translation_id):
        calls.append(translation_id)

    monkeypatch.setattr(tasks, '_run_translation_async', fake_run)

    async def run_test():
        task = tasks.schedule_translation(42)
        await task

    asyncio.run(run_test())
    assert calls == [42]


def test_schedule_translation_deduplicates_id_and_limits_concurrency(monkeypatch):
    active = 0
    max_active = 0

    async def fake_run(translation_id):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1

    monkeypatch.setattr(tasks, '_run_translation_async', fake_run)

    async def run_test():
        first = tasks.schedule_translation(51)
        duplicate = tasks.schedule_translation(51)
        others = [tasks.schedule_translation(item) for item in (52, 53, 54)]
        assert duplicate is first
        await asyncio.gather(first, *others)

    asyncio.run(run_test())
    assert max_active == tasks.TRANSLATION_MAX_CONCURRENCY


def test_recovery_monitor_schedules_recoverable_ids(monkeypatch):
    scheduled = []
    sleep_calls = []
    monkeypatch.setattr(
        tasks,
        'find_recoverable_translation_ids',
        lambda: [5, 6],
    )
    monkeypatch.setattr(tasks, 'schedule_translation', scheduled.append)

    async def stop_after_one_scan(seconds):
        sleep_calls.append(seconds)
        raise asyncio.CancelledError

    monkeypatch.setattr(tasks.asyncio, 'sleep', stop_after_one_scan)

    async def run_test():
        try:
            await tasks._monitor_recoverable_translations()
        except asyncio.CancelledError:
            pass

    asyncio.run(run_test())
    assert scheduled == [5, 6]
    assert sleep_calls == [tasks.TRANSLATION_RECOVERY_SECONDS]
