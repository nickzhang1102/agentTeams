from types import SimpleNamespace
from unittest.mock import MagicMock

from sqlalchemy.dialects import postgresql

from models import ContentTranslation
from translation.cache import (
    TRANSLATION_RECOVERY_BATCH_SIZE,
    claim_translation_lease,
    fail_translation,
    publish_translation,
    release_translation_lease,
    requeue_failed_translation,
    resolve_translation_cache,
    translation_is_fresh,
    find_recoverable_translation_ids,
)


def _source(source_locale='zh-CN'):
    return SimpleNamespace(
        source_type='message',
        source_id=11,
        user_id=7,
        conversation_id=9,
        source_locale=source_locale,
        normalized=SimpleNamespace(source_hash='a' * 64, payload={'text': '正文'}),
    )


def test_same_locale_resolution_is_noop_without_database_write():
    db_session = MagicMock()

    entry, created = resolve_translation_cache(
        db_session,
        _source(source_locale='en-US'),
        'en-US',
    )

    assert entry is None
    assert created is False
    db_session.execute.assert_not_called()


def test_cache_creation_uses_postgresql_unique_conflict_boundary():
    db_session = MagicMock()
    db_session.execute.return_value.scalar_one_or_none.return_value = 31
    created_entry = SimpleNamespace(id=31)
    db_session.get.return_value = created_entry

    entry, created = resolve_translation_cache(db_session, _source(), 'en-US')

    statement = db_session.execute.call_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert 'ON CONFLICT ON CONSTRAINT' in sql
    assert 'uq_content_translation_source_target_hash' in sql
    assert entry is created_entry
    assert created is True


def test_cache_conflict_returns_existing_entry():
    db_session = MagicMock()
    db_session.execute.return_value.scalar_one_or_none.return_value = None
    existing = SimpleNamespace(id=32)
    db_session.query.return_value.filter_by.return_value.one.return_value = existing

    entry, created = resolve_translation_cache(db_session, _source(), 'en-US')

    assert entry is existing
    assert created is False
    db_session.query.return_value.filter_by.assert_called_once_with(
        source_type='message',
        source_id=11,
        target_locale='en-US',
        source_hash='a' * 64,
    )


def test_lease_claim_is_atomic_and_increments_attempt():
    query = MagicMock()
    query.filter.return_value = query
    query.update.return_value = 1
    db_session = MagicMock()
    db_session.query.return_value = query

    assert claim_translation_lease(db_session, 31, 'worker-a') is True

    values = query.update.call_args.args[0]
    claim_filters = ' '.join(str(item) for item in query.filter.call_args.args)
    assert 'content_translations.status' in claim_filters
    assert 'content_translations.lease_expires_at IS NULL' in claim_filters
    assert 'content_translations.lease_expires_at <=' in claim_filters
    assert ContentTranslation.lease_owner in values
    assert values[ContentTranslation.lease_owner] == 'worker-a'
    assert ContentTranslation.attempt_count in values
    db_session.commit.assert_called_once()


def test_terminal_updates_require_current_owner_and_never_publish_partial_failure():
    query = MagicMock()
    query.filter.return_value = query
    query.update.side_effect = [0, 1, 1]
    db_session = MagicMock()
    db_session.query.return_value = query

    assert publish_translation(
        db_session,
        31,
        'old-worker',
        {'text': 'stale result'},
        'model-a',
        10,
        5,
    ) is False
    publish_filters = ' '.join(str(item) for item in query.filter.call_args.args)
    assert 'content_translations.status' in publish_filters
    assert 'content_translations.lease_owner' in publish_filters
    assert fail_translation(
        db_session,
        31,
        'current-worker',
        'TRANSLATION_FAILED',
    ) is True
    failed_values = query.update.call_args_list[1].args[0]
    assert failed_values[ContentTranslation.translated_payload] is None
    assert failed_values[ContentTranslation.status] == 'failed'
    assert ContentTranslation.input_tokens in failed_values
    assert release_translation_lease(
        db_session,
        31,
        'current-worker',
    ) is True


def test_source_hash_and_conversation_define_freshness():
    source = _source()
    entry = SimpleNamespace(
        source_type='message',
        source_id=11,
        conversation_id=9,
        source_locale='zh-CN',
        source_hash='a' * 64,
    )
    assert translation_is_fresh(entry, source) is True
    entry.source_hash = 'b' * 64
    assert translation_is_fresh(entry, source) is False
    entry.source_hash = 'a' * 64
    entry.source_locale = 'en-US'
    assert translation_is_fresh(entry, source) is False


def test_only_cooled_down_provider_failure_can_be_requeued():
    query = MagicMock()
    query.filter.return_value = query
    query.update.return_value = 1
    db_session = MagicMock()
    db_session.query.return_value = query
    entry = SimpleNamespace(id=31)

    assert requeue_failed_translation(db_session, entry) is True

    filters = ' '.join(str(item) for item in query.filter.call_args.args)
    values = query.update.call_args.args[0]
    assert 'content_translations.status' in filters
    assert 'content_translations.error_code' in filters
    assert 'content_translations.updated_at <=' in filters
    assert values[ContentTranslation.status] == 'pending'
    assert values[ContentTranslation.attempt_count] == 0
    db_session.refresh.assert_called_once_with(entry)


def test_recovery_scan_is_pending_lease_aware_and_bounded():
    query = MagicMock()
    query.filter.return_value = query
    query.order_by.return_value = query
    query.limit.return_value = query
    query.all.return_value = [(5,), (6,)]
    session = MagicMock()
    session.query.return_value = query

    assert find_recoverable_translation_ids(lambda: session) == [5, 6]

    filters = ' '.join(str(item) for item in query.filter.call_args.args)
    assert 'content_translations.status' in filters
    assert 'content_translations.lease_expires_at IS NULL' in filters
    query.limit.assert_called_once_with(TRANSLATION_RECOVERY_BATCH_SIZE)
    session.close.assert_called_once()
