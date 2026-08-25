"""Authenticated historical content translation endpoints."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from database import get_db
from models import ContentTranslation, Conversation, User
from schemas.content_translation import (
    EMPTY_SOURCES,
    FORBIDDEN,
    SOURCE_NOT_FOUND,
    STALE_SOURCE,
    TOO_MANY_SOURCES,
    TRANSLATION_FAILED,
    TRANSLATION_NOT_FOUND,
    UNSUPPORTED_LOCALE,
    ResolveTranslationsRequest,
    ResolveTranslationsResponse,
    TranslationItemResponse,
    TranslationResponse,
    TranslationLookupResponse,
    TranslationSourceRef,
)
from translation.cache import (
    requeue_failed_translation,
    resolve_translation_cache,
    translation_is_fresh,
)
from translation.payload import SUPPORTED_LOCALES
from translation.source import TranslationSource, TranslationSourceRegistry
from translation.tasks import schedule_translation
from utils.rate_limit import get_limit, limiter
from .deps import get_current_user


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix='/api/content-translations',
    tags=['content-translations'],
)

MAX_TRANSLATION_SOURCES = 20


@router.post('/share/{share_token}/lookup', response_model=TranslationLookupResponse)
@limiter.limit(get_limit('query'), error_message='RATE_LIMITED')
def lookup_shared_translations(
    share_token: str,
    request: Request,
    body: ResolveTranslationsRequest,
    db_session: Session = Depends(get_db),
) -> TranslationLookupResponse:
    target_locale = body.target_locale
    if not isinstance(target_locale, str) or target_locale not in SUPPORTED_LOCALES:
        _raise_api_error(400, UNSUPPORTED_LOCALE, '不支持的语言')
    if not isinstance(body.sources, list) or not body.sources:
        _raise_api_error(400, EMPTY_SOURCES, '翻译源不能为空')
    if len(body.sources) > MAX_TRANSLATION_SOURCES:
        _raise_api_error(422, TOO_MANY_SOURCES, '单次最多提交 20 个翻译源')

    conversation = db_session.query(Conversation).filter_by(
        share_token=share_token,
    ).first()
    if conversation is None:
        _raise_api_error(404, TRANSLATION_NOT_FOUND, '分享内容不存在')

    ordered_refs = _parse_source_refs(body.sources)
    valid_references = [
        reference
        for _, reference in ordered_refs
        if reference is not None
    ]
    sources, errors = TranslationSourceRegistry.load_many(
        db_session,
        valid_references,
        conversation_id=conversation.id,
    )

    eligible_sources = {
        reference: source
        for reference, source in sources.items()
        if source.source_locale != target_locale
    }
    if eligible_sources:
        source_types = {source.source_type for source in eligible_sources.values()}
        source_ids = {source.source_id for source in eligible_sources.values()}
        ready_entries = db_session.query(ContentTranslation).filter(
            ContentTranslation.conversation_id == conversation.id,
            ContentTranslation.target_locale == target_locale,
            ContentTranslation.status == 'ready',
            ContentTranslation.source_type.in_(source_types),
            ContentTranslation.source_id.in_(source_ids),
        ).all()
        ready_by_reference = {
            (
                entry.source_type,
                entry.source_id,
                entry.source_hash,
                entry.source_locale,
            ): entry
            for entry in ready_entries
        }
    else:
        ready_by_reference = {}

    items: list[TranslationItemResponse] = []
    missing_sources: list[TranslationSourceRef] = []
    for source_ref, reference in ordered_refs:
        source = eligible_sources.get(reference) if reference is not None else None
        entry = (
            ready_by_reference.get(
                (
                    reference[0],
                    reference[1],
                    source.normalized.source_hash,
                    source.source_locale,
                )
            )
            if source is not None
            else None
        )
        if source is None or entry is None:
            missing_sources.append(source_ref)
            continue
        items.append(TranslationItemResponse(
            source=source_ref,
            translation_id=None,
            status='ready',
            source_hash=entry.source_hash,
            source_locale=entry.source_locale,
            target_locale=entry.target_locale,
            payload=entry.translated_payload,
        ))

    logger.info(
        'Shared translation lookup: conversation_id=%s target_locale=%s '
        'ready_items=%s missing_items=%s',
        conversation.id,
        target_locale,
        len(items),
        len(missing_sources),
    )
    return TranslationLookupResponse(
        items=items,
        missing_sources=missing_sources,
    )


@router.post('/resolve', response_model=ResolveTranslationsResponse)
@limiter.limit(get_limit('translation'), error_message='RATE_LIMITED')
async def resolve_translations(
    request: Request,
    body: ResolveTranslationsRequest,
    user: User = Depends(get_current_user),
    db_session: Session = Depends(get_db),
) -> ResolveTranslationsResponse:
    target_locale = body.target_locale
    if not isinstance(target_locale, str) or target_locale not in SUPPORTED_LOCALES:
        _raise_api_error(400, UNSUPPORTED_LOCALE, '不支持的语言')
    if not isinstance(body.sources, list) or not body.sources:
        _raise_api_error(400, EMPTY_SOURCES, '翻译源不能为空')
    if len(body.sources) > MAX_TRANSLATION_SOURCES:
        _raise_api_error(422, TOO_MANY_SOURCES, '单次最多提交 20 个翻译源')

    ordered_refs = _parse_source_refs(body.sources)
    valid_references = [
        reference
        for _, reference in ordered_refs
        if reference is not None
    ]
    sources, errors = TranslationSourceRegistry.load_owned_many(
        db_session,
        valid_references,
        user.id,
    )

    items: list[TranslationItemResponse] = []
    pending_ids: set[int] = set()
    for source_ref, reference in ordered_refs:
        if reference is None:
            items.append(_error_item(source_ref, target_locale, SOURCE_NOT_FOUND))
            continue
        if reference in errors:
            items.append(_error_item(source_ref, target_locale, errors[reference]))
            continue

        source = sources[reference]
        entry, created = resolve_translation_cache(
            db_session,
            source,
            target_locale,
        )
        if entry is None:
            items.append(_no_op_item(source_ref, source, target_locale))
            logger.info(
                'Translation no-op: source_type=%s source_id=%s '
                'target_locale=%s status=ready',
                source.source_type,
                source.source_id,
                target_locale,
            )
            continue

        requeued = False
        if entry.status == 'failed':
            requeued = requeue_failed_translation(db_session, entry)
        if entry.status == 'pending':
            pending_ids.add(entry.id)
        items.append(_cache_item(source_ref, source, entry))
        logger.info(
            'Translation cache resolved: translation_id=%s source_type=%s '
            'source_id=%s target_locale=%s status=%s created=%s requeued=%s',
            entry.id,
            source.source_type,
            source.source_id,
            target_locale,
            entry.status,
            created,
            requeued,
        )

    db_session.commit()
    for translation_id in pending_ids:
        try:
            schedule_translation(translation_id)
        except Exception:
            logger.warning(
                'Translation scheduling failed: translation_id=%s',
                translation_id,
                exc_info=True,
            )
    return ResolveTranslationsResponse(items=items)


@router.get('/{translation_id}', response_model=TranslationResponse)
def get_translation(
    translation_id: int,
    user: User = Depends(get_current_user),
    db_session: Session = Depends(get_db),
) -> TranslationResponse:
    entry = db_session.get(ContentTranslation, translation_id)
    if entry is None:
        _raise_api_error(404, TRANSLATION_NOT_FOUND, '翻译不存在')
    if entry.user_id != user.id:
        _raise_api_error(403, FORBIDDEN, '无权访问该翻译')

    reference = (entry.source_type, entry.source_id)
    sources, errors = TranslationSourceRegistry.load_many(
        db_session,
        [reference],
    )
    source = sources.get(reference)
    if source is None:
        if errors.get(reference) == SOURCE_NOT_FOUND:
            _raise_api_error(404, TRANSLATION_NOT_FOUND, '翻译不存在')
        _raise_api_error(409, STALE_SOURCE, '翻译源已发生变化')
    if source.user_id != user.id:
        _raise_api_error(403, FORBIDDEN, '无权访问该翻译')
    if not translation_is_fresh(entry, source):
        logger.info(
            'Stale translation rejected: translation_id=%s source_type=%s '
            'source_id=%s target_locale=%s',
            entry.id,
            entry.source_type,
            entry.source_id,
            entry.target_locale,
        )
        _raise_api_error(409, STALE_SOURCE, '翻译源已发生变化')

    payload = None
    error_code = None
    if entry.status == 'ready':
        payload = entry.translated_payload
    elif entry.status == 'failed':
        payload = source.normalized.payload
        error_code = TRANSLATION_FAILED
    return TranslationResponse(
        translation_id=entry.id,
        status=entry.status,
        source_hash=entry.source_hash,
        source_locale=entry.source_locale,
        target_locale=entry.target_locale,
        payload=payload,
        error_code=error_code,
    )


def _parse_source_refs(
    raw_sources: list[Any],
) -> list[tuple[TranslationSourceRef, tuple[str, int] | None]]:
    ordered: list[tuple[TranslationSourceRef, tuple[str, int] | None]] = []
    seen: set[tuple[str, int]] = set()
    for raw in raw_sources:
        if isinstance(raw, dict):
            source_type = raw.get('type')
            source_id = raw.get('id')
        else:
            source_type = None
            source_id = None
        valid = (
            isinstance(source_type, str)
            and isinstance(source_id, int)
            and not isinstance(source_id, bool)
            and source_id > 0
            and set(raw) == {'type', 'id'}
        )
        source_ref = TranslationSourceRef(
            type=source_type if isinstance(source_type, str) else '',
            id=source_id if isinstance(source_id, int) and not isinstance(source_id, bool) else 0,
        )
        reference = (source_type, source_id) if valid else None
        if reference is not None:
            if reference in seen:
                continue
            seen.add(reference)
        ordered.append((source_ref, reference))
    return ordered


def _error_item(
    source_ref: TranslationSourceRef,
    target_locale: str,
    error_code: str,
) -> TranslationItemResponse:
    return TranslationItemResponse(
        source=source_ref,
        status='failed',
        target_locale=target_locale,
        error_code=error_code,
    )


def _no_op_item(
    source_ref: TranslationSourceRef,
    source: TranslationSource,
    target_locale: str,
) -> TranslationItemResponse:
    return TranslationItemResponse(
        source=source_ref,
        translation_id=None,
        status='ready',
        source_hash=source.normalized.source_hash,
        source_locale=source.source_locale,
        target_locale=target_locale,
        payload=source.normalized.payload,
    )


def _cache_item(
    source_ref: TranslationSourceRef,
    source: TranslationSource,
    entry: ContentTranslation,
) -> TranslationItemResponse:
    if entry.status == 'ready':
        payload = entry.translated_payload
        error_code = None
    elif entry.status == 'failed':
        payload = source.normalized.payload
        error_code = TRANSLATION_FAILED
    else:
        payload = None
        error_code = None
    return TranslationItemResponse(
        source=source_ref,
        translation_id=entry.id,
        status=entry.status,
        source_hash=entry.source_hash,
        source_locale=entry.source_locale,
        target_locale=entry.target_locale,
        payload=payload,
        error_code=error_code,
    )


def _raise_api_error(status_code: int, code: str, message: str) -> None:
    raise HTTPException(
        status_code=status_code,
        detail={'code': code, 'error': message},
    )
