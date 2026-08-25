from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock

from translation import worker


class FakeHeartbeat:
    def __init__(self, *args, **kwargs):
        pass

    def start(self):
        pass

    def join(self, timeout=None):
        pass


class FakeLLM:
    model = 'model-a'

    @contextmanager
    def capture_usage(self):
        yield {'input_tokens': 12, 'output_tokens': 6}


def _entry(source_hash='a' * 64, attempt_count=1):
    return SimpleNamespace(
        id=31,
        user_id=7,
        conversation_id=9,
        source_type='message',
        source_id=11,
        source_hash=source_hash,
        source_locale='zh-CN',
        target_locale='en-US',
        attempt_count=attempt_count,
    )


def _session(entry):
    session = MagicMock()
    session.get.return_value = entry
    return session


def _source(source_hash='a' * 64, source_locale='zh-CN'):
    return SimpleNamespace(
        source_type='message',
        source_id=11,
        user_id=7,
        conversation_id=9,
        source_locale=source_locale,
        normalized=SimpleNamespace(source_hash=source_hash),
    )


def test_worker_publishes_only_after_translation_completes(monkeypatch):
    entry = _entry()
    session = _session(entry)
    monkeypatch.setattr(worker, 'Thread', FakeHeartbeat)
    monkeypatch.setattr(worker, 'claim_translation_lease', lambda *args: True)
    monkeypatch.setattr(
        worker.TranslationSourceRegistry,
        'load_many',
        lambda *args: ({('message', 11): _source()}, {}),
    )
    monkeypatch.setattr(
        worker,
        'translate_normalized_payload',
        lambda *args: {'text': 'Translated'},
    )
    published = []
    monkeypatch.setattr(
        worker,
        'publish_translation',
        lambda *args: published.append(args) or True,
    )

    worker.run_translation_worker(
        31,
        session_factory=lambda: session,
        llm_factory=lambda db, conversation_id: FakeLLM(),
    )

    assert published[0][3] == {'text': 'Translated'}
    assert published[0][4:] == ('model-a', 12, 6)
    session.close.assert_called_once()


def test_worker_marks_changed_source_stale_without_llm(monkeypatch):
    entry = _entry(source_hash='old-hash')
    session = _session(entry)
    monkeypatch.setattr(worker, 'Thread', FakeHeartbeat)
    monkeypatch.setattr(worker, 'claim_translation_lease', lambda *args: True)
    monkeypatch.setattr(
        worker.TranslationSourceRegistry,
        'load_many',
        lambda *args: ({('message', 11): _source(source_hash='new-hash')}, {}),
    )
    failed = []
    monkeypatch.setattr(
        worker,
        'fail_translation',
        lambda *args, **kwargs: failed.append((args, kwargs)) or True,
    )
    llm_factory = MagicMock()

    worker.run_translation_worker(
        31,
        session_factory=lambda: session,
        llm_factory=llm_factory,
    )

    assert failed[0][0][3] == 'STALE_SOURCE'
    llm_factory.assert_not_called()


def test_worker_marks_changed_source_locale_stale_without_llm(monkeypatch):
    entry = _entry()
    session = _session(entry)
    monkeypatch.setattr(worker, 'Thread', FakeHeartbeat)
    monkeypatch.setattr(worker, 'claim_translation_lease', lambda *args: True)
    monkeypatch.setattr(
        worker.TranslationSourceRegistry,
        'load_many',
        lambda *args: ({
            ('message', 11): _source(source_locale='en-US'),
        }, {}),
    )
    failed = []
    monkeypatch.setattr(
        worker,
        'fail_translation',
        lambda *args, **kwargs: failed.append((args, kwargs)) or True,
    )
    llm_factory = MagicMock()

    worker.run_translation_worker(
        31,
        session_factory=lambda: session,
        llm_factory=llm_factory,
    )

    assert failed[0][0][3] == 'STALE_SOURCE'
    llm_factory.assert_not_called()


def test_worker_requeues_retryable_failure_until_attempt_limit(monkeypatch):
    entry = _entry(attempt_count=2)
    session = _session(entry)
    monkeypatch.setattr(worker, 'Thread', FakeHeartbeat)
    monkeypatch.setattr(worker, 'claim_translation_lease', lambda *args: True)
    monkeypatch.setattr(
        worker.TranslationSourceRegistry,
        'load_many',
        lambda *args: ({('message', 11): _source()}, {}),
    )
    monkeypatch.setattr(
        worker,
        'translate_normalized_payload',
        MagicMock(side_effect=RuntimeError('provider unavailable')),
    )
    released = []
    monkeypatch.setattr(
        worker,
        'release_translation_lease',
        lambda *args, **kwargs: released.append((args, kwargs)) or True,
    )

    worker.run_translation_worker(
        31,
        session_factory=lambda: session,
        llm_factory=lambda db, conversation_id: FakeLLM(),
    )

    assert released[0][1]['retry_after_seconds'] == worker.TRANSLATION_RETRY_SECONDS
    assert released[0][1]['model_id'] == 'model-a'


def test_worker_fails_retryable_error_at_attempt_limit(monkeypatch):
    entry = _entry(attempt_count=worker.TRANSLATION_MAX_ATTEMPTS)
    session = _session(entry)
    monkeypatch.setattr(worker, 'Thread', FakeHeartbeat)
    monkeypatch.setattr(worker, 'claim_translation_lease', lambda *args: True)
    monkeypatch.setattr(
        worker.TranslationSourceRegistry,
        'load_many',
        lambda *args: ({('message', 11): _source()}, {}),
    )
    monkeypatch.setattr(
        worker,
        'translate_normalized_payload',
        MagicMock(side_effect=RuntimeError('provider unavailable')),
    )
    failed = []
    monkeypatch.setattr(
        worker,
        'fail_translation',
        lambda *args, **kwargs: failed.append((args, kwargs)) or True,
    )

    worker.run_translation_worker(
        31,
        session_factory=lambda: session,
        llm_factory=lambda db, conversation_id: FakeLLM(),
    )

    assert failed[0][0][3] == 'TRANSLATION_FAILED'
    assert failed[0][1]['input_tokens'] == 12
