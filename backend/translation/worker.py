"""Lease-aware worker for one historical content translation."""
from __future__ import annotations

import logging
import secrets
from threading import Event, Thread
from typing import Any, Callable

from db import SessionLocal
from models import ContentTranslation, Conversation
from services.llm_service import LLMService, create_llm_service
from .cache import (
    TRANSLATION_LEASE_SECONDS,
    TRANSLATION_RETRY_SECONDS,
    claim_translation_lease,
    fail_translation,
    publish_translation,
    release_translation_lease,
    renew_translation_lease,
    translation_is_fresh,
)
from .source import TranslationSourceRegistry
from .translator import TranslationIntegrityError, translate_normalized_payload


logger = logging.getLogger(__name__)

TRANSLATION_MAX_ATTEMPTS = 3
TRANSLATION_HEARTBEAT_SECONDS = TRANSLATION_LEASE_SECONDS // 3


class _PermanentTranslationError(RuntimeError):
    def __init__(self, error_code: str = 'TRANSLATION_FAILED'):
        super().__init__(error_code)
        self.error_code = error_code


def run_translation_worker(
    translation_id: int,
    session_factory=SessionLocal,
    llm_factory: Callable[[Any, int], LLMService] | None = None,
) -> None:
    db_session = session_factory()
    lease_owner = secrets.token_hex(16)
    stop_heartbeat = Event()
    lease_lost = Event()
    heartbeat: Thread | None = None
    entry: ContentTranslation | None = None
    service: LLMService | None = None
    usage = {'input_tokens': 0, 'output_tokens': 0}
    try:
        if not claim_translation_lease(db_session, translation_id, lease_owner):
            return
        entry = db_session.get(ContentTranslation, translation_id)
        if entry is None:
            return

        heartbeat = Thread(
            target=_maintain_translation_lease,
            args=(
                translation_id,
                lease_owner,
                session_factory,
                stop_heartbeat,
                lease_lost,
            ),
            name=f'translation-lease-{translation_id}',
            daemon=True,
        )
        heartbeat.start()

        sources, errors = TranslationSourceRegistry.load_many(
            db_session,
            [(entry.source_type, entry.source_id)],
        )
        source = sources.get((entry.source_type, entry.source_id))
        if source is None or errors:
            raise _PermanentTranslationError()
        if (
            source.user_id != entry.user_id
            or source.conversation_id != entry.conversation_id
        ):
            raise _PermanentTranslationError()
        if not translation_is_fresh(entry, source):
            raise _PermanentTranslationError('STALE_SOURCE')

        service = (llm_factory or _build_translation_llm)(
            db_session,
            entry.conversation_id,
        )
        with service.capture_usage() as usage:
            translated = translate_normalized_payload(
                source.normalized,
                entry.source_locale,
                entry.target_locale,
                service,
            )

        if lease_lost.is_set():
            logger.warning(
                'Translation result discarded after lease loss: translation_id=%s',
                translation_id,
            )
            return
        published = publish_translation(
            db_session,
            translation_id,
            lease_owner,
            translated,
            service.model,
            usage['input_tokens'],
            usage['output_tokens'],
        )
        logger.info(
            'Translation finished: translation_id=%s source_type=%s source_id=%s '
            'target_locale=%s status=%s attempt=%s model=%s input_tokens=%s '
            'output_tokens=%s',
            translation_id,
            entry.source_type,
            entry.source_id,
            entry.target_locale,
            'ready' if published else 'lease_lost',
            entry.attempt_count,
            service.model,
            usage['input_tokens'],
            usage['output_tokens'],
        )
    except _PermanentTranslationError as exc:
        db_session.rollback()
        fail_translation(
            db_session,
            translation_id,
            lease_owner,
            exc.error_code,
            model_id=service.model if service else None,
            input_tokens=usage['input_tokens'],
            output_tokens=usage['output_tokens'],
        )
        _log_failure(entry, translation_id, exc.error_code)
    except TranslationIntegrityError:
        db_session.rollback()
        fail_translation(
            db_session,
            translation_id,
            lease_owner,
            'SOURCE_NOT_TRANSLATABLE',
            model_id=service.model if service else None,
            input_tokens=usage['input_tokens'],
            output_tokens=usage['output_tokens'],
        )
        _log_failure(entry, translation_id, 'SOURCE_NOT_TRANSLATABLE')
    except Exception:
        db_session.rollback()
        attempts = entry.attempt_count if entry is not None else TRANSLATION_MAX_ATTEMPTS
        if attempts < TRANSLATION_MAX_ATTEMPTS:
            release_translation_lease(
                db_session,
                translation_id,
                lease_owner,
                retry_after_seconds=TRANSLATION_RETRY_SECONDS,
                model_id=service.model if service else None,
                input_tokens=usage['input_tokens'],
                output_tokens=usage['output_tokens'],
            )
            status = 'pending'
        else:
            fail_translation(
                db_session,
                translation_id,
                lease_owner,
                'TRANSLATION_FAILED',
                model_id=service.model if service else None,
                input_tokens=usage['input_tokens'],
                output_tokens=usage['output_tokens'],
            )
            status = 'failed'
        logger.error(
            'Translation worker error: translation_id=%s status=%s attempt=%s',
            translation_id,
            status,
            attempts,
            exc_info=True,
        )
    finally:
        stop_heartbeat.set()
        if heartbeat is not None:
            heartbeat.join(timeout=1.0)
        db_session.close()


def _maintain_translation_lease(
    translation_id: int,
    lease_owner: str,
    session_factory,
    stop: Event,
    lease_lost: Event,
) -> None:
    while not stop.wait(TRANSLATION_HEARTBEAT_SECONDS):
        try:
            if not renew_translation_lease(
                translation_id,
                lease_owner,
                session_factory,
            ):
                lease_lost.set()
                return
        except Exception:
            lease_lost.set()
            logger.error(
                'Translation lease heartbeat failed: translation_id=%s',
                translation_id,
                exc_info=True,
            )
            return


def _build_translation_llm(db_session: Any, conversation_id: int) -> LLMService:
    conversation = db_session.get(Conversation, conversation_id)
    return create_llm_service(
        conversation.model_override if conversation else None,
        db_session=db_session,
    )


def _log_failure(
    entry: ContentTranslation | None,
    translation_id: int,
    error_code: str,
) -> None:
    logger.warning(
        'Translation failed: translation_id=%s source_type=%s source_id=%s '
        'target_locale=%s status=failed attempt=%s error_code=%s',
        translation_id,
        entry.source_type if entry else None,
        entry.source_id if entry else None,
        entry.target_locale if entry else None,
        entry.attempt_count if entry else None,
        error_code,
    )
