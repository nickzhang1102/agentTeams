from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from api import content_translation_api as api
from schemas.content_translation import ResolveTranslationsRequest


def _source(source_id=11, conversation_id=9, source_locale='zh-CN'):
    return SimpleNamespace(
        source_type='message',
        source_id=source_id,
        user_id=7,
        conversation_id=conversation_id,
        source_locale=source_locale,
        normalized=SimpleNamespace(
            source_hash='a' * 64,
            payload={'text': '原文'},
        ),
    )


def test_share_lookup_returns_only_fresh_ready_cache_without_writes(monkeypatch):
    conversation = SimpleNamespace(id=9)
    source = _source()
    ready_entry = SimpleNamespace(
        source_type='message',
        source_id=11,
        source_hash='a' * 64,
        source_locale='zh-CN',
        target_locale='en-US',
        status='ready',
        translated_payload={'text': 'Translated'},
    )
    db_session = MagicMock()
    conversation_query = MagicMock()
    conversation_query.filter_by.return_value = conversation_query
    conversation_query.first.return_value = conversation
    translation_query = MagicMock()
    translation_query.filter.return_value = translation_query
    translation_query.all.return_value = [ready_entry]
    db_session.query.side_effect = [conversation_query, translation_query]
    monkeypatch.setattr(
        api.TranslationSourceRegistry,
        'load_many',
        lambda *args, **kwargs: ({('message', 11): source}, {}),
    )
    schedule = MagicMock()
    monkeypatch.setattr(api, 'schedule_translation', schedule)

    response = api.lookup_shared_translations.__wrapped__(
        share_token='share-token',
        request=MagicMock(),
        body=ResolveTranslationsRequest(
            target_locale='en-US',
            sources=[
                {'type': 'message', 'id': 11},
                {'type': 'message', 'id': 12},
                {'type': 'message', 'id': 11},
            ],
        ),
        db_session=db_session,
    )

    assert len(response.items) == 1
    assert response.items[0].translation_id is None
    assert response.items[0].payload == {'text': 'Translated'}
    assert [ref.id for ref in response.missing_sources] == [12]
    db_session.add.assert_not_called()
    db_session.commit.assert_not_called()
    schedule.assert_not_called()


def test_share_lookup_hides_pending_failed_stale_and_other_conversation_sources(monkeypatch):
    conversation = SimpleNamespace(id=9)
    source = _source()
    db_session = MagicMock()
    conversation_query = MagicMock()
    conversation_query.filter_by.return_value = conversation_query
    conversation_query.first.return_value = conversation
    translation_query = MagicMock()
    translation_query.filter.return_value = translation_query
    translation_query.all.return_value = []
    db_session.query.side_effect = [conversation_query, translation_query]
    monkeypatch.setattr(
        api.TranslationSourceRegistry,
        'load_many',
        lambda *args, **kwargs: ({('message', 11): source}, {
            ('message', 12): 'SOURCE_NOT_FOUND',
        }),
    )

    response = api.lookup_shared_translations.__wrapped__(
        share_token='share-token',
        request=MagicMock(),
        body=ResolveTranslationsRequest(
            target_locale='en-US',
            sources=[
                {'type': 'message', 'id': 11},
                {'type': 'message', 'id': 12},
            ],
        ),
        db_session=db_session,
    )

    assert response.items == []
    assert [ref.id for ref in response.missing_sources] == [11, 12]
    db_session.add.assert_not_called()
    db_session.commit.assert_not_called()


def test_share_lookup_hides_cache_after_source_locale_changes(monkeypatch):
    conversation = SimpleNamespace(id=9)
    source = _source(source_locale='zh-CN')
    stale_entry = SimpleNamespace(
        source_type='message',
        source_id=11,
        source_hash='a' * 64,
        source_locale='en-US',
        target_locale='en-US',
        status='ready',
        translated_payload={'text': 'Stale'},
    )
    db_session = MagicMock()
    conversation_query = MagicMock()
    conversation_query.filter_by.return_value = conversation_query
    conversation_query.first.return_value = conversation
    translation_query = MagicMock()
    translation_query.filter.return_value = translation_query
    translation_query.all.return_value = [stale_entry]
    db_session.query.side_effect = [conversation_query, translation_query]
    monkeypatch.setattr(
        api.TranslationSourceRegistry,
        'load_many',
        lambda *args, **kwargs: ({('message', 11): source}, {}),
    )

    response = api.lookup_shared_translations.__wrapped__(
        share_token='share-token',
        request=MagicMock(),
        body=ResolveTranslationsRequest(
            target_locale='en-US',
            sources=[{'type': 'message', 'id': 11}],
        ),
        db_session=db_session,
    )

    assert response.items == []
    assert [ref.id for ref in response.missing_sources] == [11]
    db_session.add.assert_not_called()
    db_session.commit.assert_not_called()


def test_share_lookup_rejects_unknown_token_without_source_details():
    db_session = MagicMock()
    query = MagicMock()
    query.filter_by.return_value = query
    query.first.return_value = None
    db_session.query.return_value = query

    with pytest.raises(HTTPException) as exc_info:
        api.lookup_shared_translations.__wrapped__(
            share_token='invalid',
            request=MagicMock(),
            body=ResolveTranslationsRequest(
                target_locale='en-US',
                sources=[{'type': 'message', 'id': 11}],
            ),
            db_session=db_session,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail['code'] == 'TRANSLATION_NOT_FOUND'
