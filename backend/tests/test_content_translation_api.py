import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from api import content_translation_api as api
from app import _rate_limit_exceeded_handler, app
from schemas.content_translation import ResolveTranslationsRequest


def _source(source_id=11, source_locale='zh-CN', source_hash='a' * 64):
    return SimpleNamespace(
        source_type='message',
        source_id=source_id,
        user_id=7,
        conversation_id=9,
        source_locale=source_locale,
        normalized=SimpleNamespace(
            source_hash=source_hash,
            payload={'text': '原文'},
        ),
    )


def _resolve(body, monkeypatch, *, sources=None, errors=None, cache_result=None):
    db_session = MagicMock()
    monkeypatch.setattr(
        api.TranslationSourceRegistry,
        'load_owned_many',
        lambda *args: (sources or {}, errors or {}),
    )
    if cache_result is not None:
        monkeypatch.setattr(api, 'resolve_translation_cache', lambda *args: cache_result)
    return db_session, asyncio.run(
        api.resolve_translations.__wrapped__(
            request=MagicMock(),
            body=body,
            user=SimpleNamespace(id=7),
            db_session=db_session,
        )
    )


@pytest.mark.parametrize(
    ('body', 'status_code', 'code'),
    [
        (
            ResolveTranslationsRequest(target_locale='fr-FR', sources=[]),
            400,
            'UNSUPPORTED_LOCALE',
        ),
        (
            ResolveTranslationsRequest(target_locale=[], sources=[]),
            400,
            'UNSUPPORTED_LOCALE',
        ),
        (
            ResolveTranslationsRequest(target_locale='en-US', sources=[]),
            400,
            'EMPTY_SOURCES',
        ),
        (
            ResolveTranslationsRequest(
                target_locale='en-US',
                sources=[{'type': 'message', 'id': index + 1} for index in range(21)],
            ),
            422,
            'TOO_MANY_SOURCES',
        ),
    ],
)
def test_resolve_request_errors_are_stable(body, status_code, code):
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            api.resolve_translations.__wrapped__(
                request=MagicMock(),
                body=body,
                user=SimpleNamespace(id=7),
                db_session=MagicMock(),
            )
        )

    assert exc_info.value.status_code == status_code
    assert exc_info.value.detail['code'] == code


def test_resolve_deduplicates_refs_preserves_first_order_and_schedules_after_commit(
    monkeypatch,
):
    source = _source()
    entry = SimpleNamespace(
        id=31,
        status='pending',
        source_hash='a' * 64,
        source_locale='zh-CN',
        target_locale='en-US',
        translated_payload=None,
    )
    scheduled = []
    monkeypatch.setattr(api, 'schedule_translation', scheduled.append)
    body = ResolveTranslationsRequest(
        target_locale='en-US',
        sources=[
            {'type': 'message', 'id': 11},
            {'type': 'message', 'id': 11},
            {'type': 'message', 'id': 12},
            {'type': 'message', 'id': 'bad'},
        ],
    )
    db_session, response = _resolve(
        body,
        monkeypatch,
        sources={('message', 11): source},
        errors={('message', 12): 'FORBIDDEN'},
        cache_result=(entry, True),
    )

    assert [item.source.id for item in response.items] == [11, 12, 0]
    assert [item.error_code for item in response.items] == [
        None,
        'FORBIDDEN',
        'SOURCE_NOT_FOUND',
    ]
    assert scheduled == [31]
    db_session.commit.assert_called_once()


def test_same_locale_returns_source_without_cache_or_schedule(monkeypatch):
    source = _source(source_locale='en-US')
    cache = MagicMock(return_value=(None, False))
    monkeypatch.setattr(api, 'resolve_translation_cache', cache)
    schedule = MagicMock()
    monkeypatch.setattr(api, 'schedule_translation', schedule)
    body = ResolveTranslationsRequest(
        target_locale='en-US',
        sources=[{'type': 'message', 'id': 11}],
    )

    _, response = _resolve(
        body,
        monkeypatch,
        sources={('message', 11): source},
    )

    item = response.items[0]
    assert item.translation_id is None
    assert item.status == 'ready'
    assert item.payload == {'text': '原文'}
    cache.assert_called_once()
    schedule.assert_not_called()


def test_request_rejects_undeclared_root_and_source_fields(monkeypatch):
    with pytest.raises(ValidationError):
        ResolveTranslationsRequest(
            target_locale='en-US',
            sources=[{'type': 'message', 'id': 11}],
            source_hash='client-controlled',
        )

    cache = MagicMock()
    monkeypatch.setattr(api, 'resolve_translation_cache', cache)
    body = ResolveTranslationsRequest(
        target_locale='en-US',
        sources=[{
            'type': 'message',
            'id': 11,
            'text': 'client-controlled',
        }],
    )
    _, response = _resolve(body, monkeypatch)

    assert response.items[0].error_code == 'SOURCE_NOT_FOUND'
    cache.assert_not_called()


def test_owner_get_rejects_stale_and_failed_falls_back_to_current_source(monkeypatch):
    entry = SimpleNamespace(
        id=31,
        user_id=7,
        conversation_id=9,
        source_type='message',
        source_id=11,
        source_hash='old-hash',
        source_locale='zh-CN',
        target_locale='en-US',
        status='ready',
        translated_payload={'text': 'Old'},
    )
    db_session = MagicMock()
    db_session.get.return_value = entry
    monkeypatch.setattr(
        api.TranslationSourceRegistry,
        'load_many',
        lambda *args: ({('message', 11): _source(source_hash='new-hash')}, {}),
    )
    with pytest.raises(HTTPException) as exc_info:
        api.get_translation(31, SimpleNamespace(id=7), db_session)
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail['code'] == 'STALE_SOURCE'

    entry.source_hash = 'new-hash'
    entry.status = 'failed'
    response = api.get_translation(31, SimpleNamespace(id=7), db_session)
    assert response.payload == {'text': '原文'}
    assert response.error_code == 'TRANSLATION_FAILED'


def test_translation_route_and_rate_limit_error_are_registered():
    assert any(
        getattr(route, 'path', '') == '/api/content-translations/resolve'
        for route in app.routes
    )
    response = _rate_limit_exceeded_handler(
        MagicMock(),
        SimpleNamespace(detail='RATE_LIMITED'),
    )
    assert response.status_code == 429
    assert b'RATE_LIMITED' in response.body
