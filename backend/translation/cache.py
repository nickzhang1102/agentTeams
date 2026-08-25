"""Translation cache creation, lease ownership, and terminal state updates."""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Callable

from sqlalchemy import and_, func, or_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from db import SessionLocal
from models import ContentTranslation
from utils.time_utils import utcnow_naive
from .source import TranslationSource


TRANSLATION_LEASE_SECONDS = 120
TRANSLATION_RETRY_SECONDS = 30
TRANSLATION_RECOVERY_BATCH_SIZE = 100


def resolve_translation_cache(
    db_session: Session,
    source: TranslationSource,
    target_locale: str,
) -> tuple[ContentTranslation | None, bool]:
    """Return no-op for same locale, otherwise atomically get or create cache."""
    if source.source_locale == target_locale:
        return None, False

    values = {
        'user_id': source.user_id,
        'conversation_id': source.conversation_id,
        'source_type': source.source_type,
        'source_id': source.source_id,
        'source_hash': source.normalized.source_hash,
        'source_locale': source.source_locale,
        'target_locale': target_locale,
        'status': 'pending',
        'input_tokens': 0,
        'output_tokens': 0,
        'attempt_count': 0,
        'created_at': utcnow_naive(),
        'updated_at': utcnow_naive(),
    }
    statement = (
        insert(ContentTranslation)
        .values(**values)
        .on_conflict_do_nothing(
            constraint='uq_content_translation_source_target_hash'
        )
        .returning(ContentTranslation.id)
    )
    created_id = db_session.execute(statement).scalar_one_or_none()
    if created_id is not None:
        return db_session.get(ContentTranslation, created_id), True

    entry = db_session.query(ContentTranslation).filter_by(
        source_type=source.source_type,
        source_id=source.source_id,
        target_locale=target_locale,
        source_hash=source.normalized.source_hash,
    ).one()
    return entry, False


def translation_is_fresh(
    entry: ContentTranslation,
    source: TranslationSource,
) -> bool:
    return (
        entry.source_type == source.source_type
        and entry.source_id == source.source_id
        and entry.conversation_id == source.conversation_id
        and entry.source_locale == source.source_locale
        and entry.source_hash == source.normalized.source_hash
    )


def requeue_failed_translation(
    db_session: Session,
    entry: ContentTranslation,
    retry_after_seconds: int = TRANSLATION_RETRY_SECONDS,
) -> bool:
    """Requeue only provider failures after the explicit retry cooldown."""
    retry_before = utcnow_naive() - timedelta(
        seconds=max(0, retry_after_seconds)
    )
    updated = db_session.query(ContentTranslation).filter(
        ContentTranslation.id == entry.id,
        ContentTranslation.status == 'failed',
        ContentTranslation.error_code == 'TRANSLATION_FAILED',
        ContentTranslation.updated_at <= retry_before,
    ).update(
        {
            ContentTranslation.status: 'pending',
            ContentTranslation.error_code: None,
            ContentTranslation.attempt_count: 0,
            ContentTranslation.lease_owner: None,
            ContentTranslation.lease_expires_at: None,
            ContentTranslation.updated_at: utcnow_naive(),
        },
        synchronize_session=False,
    )
    if updated == 1:
        db_session.expire(entry)
        db_session.refresh(entry)
        return True
    return False


def find_recoverable_translation_ids(
    session_factory: Callable[[], Session] = SessionLocal,
) -> list[int]:
    session = session_factory()
    try:
        now = utcnow_naive()
        return [
            translation_id
            for (translation_id,) in session.query(ContentTranslation.id).filter(
                ContentTranslation.status == 'pending',
                or_(
                    ContentTranslation.lease_expires_at.is_(None),
                    ContentTranslation.lease_expires_at <= now,
                ),
            ).order_by(ContentTranslation.id.asc()).limit(
                TRANSLATION_RECOVERY_BATCH_SIZE
            ).all()
        ]
    finally:
        session.close()


def claim_translation_lease(
    db_session: Session,
    translation_id: int,
    lease_owner: str,
    lease_seconds: int = TRANSLATION_LEASE_SECONDS,
) -> bool:
    now = utcnow_naive()
    claimed = db_session.query(ContentTranslation).filter(
        ContentTranslation.id == translation_id,
        ContentTranslation.status == 'pending',
        or_(
            ContentTranslation.lease_expires_at.is_(None),
            ContentTranslation.lease_expires_at <= now,
        ),
    ).update(
        {
            ContentTranslation.lease_owner: lease_owner,
            ContentTranslation.lease_expires_at: now + timedelta(
                seconds=lease_seconds
            ),
            ContentTranslation.attempt_count: func.coalesce(
                ContentTranslation.attempt_count,
                0,
            ) + 1,
            ContentTranslation.updated_at: now,
        },
        synchronize_session=False,
    )
    db_session.commit()
    return claimed == 1


def renew_translation_lease(
    translation_id: int,
    lease_owner: str,
    session_factory: Callable[[], Session] = SessionLocal,
    lease_seconds: int = TRANSLATION_LEASE_SECONDS,
) -> bool:
    session = session_factory()
    try:
        now = utcnow_naive()
        updated = session.query(ContentTranslation).filter(
            ContentTranslation.id == translation_id,
            ContentTranslation.status == 'pending',
            ContentTranslation.lease_owner == lease_owner,
        ).update(
            {
                ContentTranslation.lease_expires_at: now + timedelta(
                    seconds=lease_seconds
                ),
                ContentTranslation.updated_at: now,
            },
            synchronize_session=False,
        )
        session.commit()
        return updated == 1
    finally:
        session.close()


def publish_translation(
    db_session: Session,
    translation_id: int,
    lease_owner: str,
    payload: dict[str, Any],
    model_id: str,
    input_tokens: int,
    output_tokens: int,
) -> bool:
    now = utcnow_naive()
    updated = _owned_pending_query(
        db_session,
        translation_id,
        lease_owner,
    ).update(
        {
            ContentTranslation.translated_payload: payload,
            ContentTranslation.status: 'ready',
            ContentTranslation.error_code: None,
            ContentTranslation.model_id: model_id,
            ContentTranslation.input_tokens: func.coalesce(
                ContentTranslation.input_tokens,
                0,
            ) + input_tokens,
            ContentTranslation.output_tokens: func.coalesce(
                ContentTranslation.output_tokens,
                0,
            ) + output_tokens,
            ContentTranslation.lease_owner: None,
            ContentTranslation.lease_expires_at: None,
            ContentTranslation.updated_at: now,
        },
        synchronize_session=False,
    )
    db_session.commit()
    return updated == 1


def fail_translation(
    db_session: Session,
    translation_id: int,
    lease_owner: str,
    error_code: str,
    model_id: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> bool:
    now = utcnow_naive()
    values = {
        ContentTranslation.translated_payload: None,
        ContentTranslation.status: 'failed',
        ContentTranslation.error_code: error_code,
        ContentTranslation.input_tokens: func.coalesce(
            ContentTranslation.input_tokens,
            0,
        ) + input_tokens,
        ContentTranslation.output_tokens: func.coalesce(
            ContentTranslation.output_tokens,
            0,
        ) + output_tokens,
        ContentTranslation.lease_owner: None,
        ContentTranslation.lease_expires_at: None,
        ContentTranslation.updated_at: now,
    }
    if model_id is not None:
        values[ContentTranslation.model_id] = model_id
    updated = _owned_pending_query(
        db_session,
        translation_id,
        lease_owner,
    ).update(
        values,
        synchronize_session=False,
    )
    db_session.commit()
    return updated == 1


def release_translation_lease(
    db_session: Session,
    translation_id: int,
    lease_owner: str,
    retry_after_seconds: int = 0,
    model_id: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> bool:
    now = utcnow_naive()
    values = {
        ContentTranslation.lease_owner: None,
        ContentTranslation.lease_expires_at: now + timedelta(
            seconds=max(0, retry_after_seconds)
        ),
        ContentTranslation.input_tokens: func.coalesce(
            ContentTranslation.input_tokens,
            0,
        ) + input_tokens,
        ContentTranslation.output_tokens: func.coalesce(
            ContentTranslation.output_tokens,
            0,
        ) + output_tokens,
        ContentTranslation.updated_at: now,
    }
    if model_id is not None:
        values[ContentTranslation.model_id] = model_id
    updated = _owned_pending_query(
        db_session,
        translation_id,
        lease_owner,
    ).update(
        values,
        synchronize_session=False,
    )
    db_session.commit()
    return updated == 1


def _owned_pending_query(
    db_session: Session,
    translation_id: int,
    lease_owner: str,
):
    return db_session.query(ContentTranslation).filter(
        ContentTranslation.id == translation_id,
        ContentTranslation.status == 'pending',
        ContentTranslation.lease_owner == lease_owner,
    )
