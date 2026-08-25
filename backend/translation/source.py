"""Server-owned translation source registry."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from sqlalchemy.orm import Session

from models import Conversation, LeaderAgentResult, LeaderFinalReport, Message
from .payload import NormalizedTranslationPayload, normalize_translation_payload


SOURCE_NOT_FOUND = 'SOURCE_NOT_FOUND'
FORBIDDEN = 'FORBIDDEN'
SOURCE_NOT_TRANSLATABLE = 'SOURCE_NOT_TRANSLATABLE'

_SOURCE_MODELS = {
    'message': Message,
    'leader_agent_result': LeaderAgentResult,
    'leader_final_report': LeaderFinalReport,
}


@dataclass(frozen=True)
class TranslationSource:
    source_type: str
    source_id: int
    user_id: int
    conversation_id: int
    source_locale: str
    normalized: NormalizedTranslationPayload


class TranslationSourceRegistry:
    """Batch-loads source entities together with their Conversation owner."""

    @staticmethod
    def load_many(
        db_session: Session,
        references: Iterable[tuple[str, int]],
        owner_user_id: int | None = None,
        conversation_id: int | None = None,
    ) -> tuple[
        dict[tuple[str, int], TranslationSource],
        dict[tuple[str, int], str],
    ]:
        ordered_refs = list(dict.fromkeys(references))
        sources: dict[tuple[str, int], TranslationSource] = {}
        errors: dict[tuple[str, int], str] = {}

        grouped_ids: dict[str, set[int]] = {}
        for source_type, source_id in ordered_refs:
            if source_type not in _SOURCE_MODELS or source_id <= 0:
                errors[(source_type, source_id)] = SOURCE_NOT_FOUND
                continue
            grouped_ids.setdefault(source_type, set()).add(source_id)

        for source_type, source_ids in grouped_ids.items():
            model = _SOURCE_MODELS[source_type]
            rows = (
                db_session.query(model, Conversation.user_id)
                .join(Conversation, model.conversation_id == Conversation.id)
                .filter(model.id.in_(source_ids))
                .all()
            )
            loaded_ids = set()
            for entity, user_id in rows:
                loaded_ids.add(entity.id)
                reference = (source_type, entity.id)
                if owner_user_id is not None and user_id != owner_user_id:
                    errors[reference] = FORBIDDEN
                    continue
                if conversation_id is not None and entity.conversation_id != conversation_id:
                    errors[reference] = SOURCE_NOT_FOUND
                    continue
                try:
                    normalized = normalize_translation_payload(source_type, entity)
                except ValueError:
                    errors[reference] = SOURCE_NOT_TRANSLATABLE
                    continue
                sources[reference] = TranslationSource(
                    source_type=source_type,
                    source_id=entity.id,
                    user_id=user_id,
                    conversation_id=entity.conversation_id,
                    source_locale=entity.content_locale,
                    normalized=normalized,
                )
            for missing_id in source_ids - loaded_ids:
                errors[(source_type, missing_id)] = SOURCE_NOT_FOUND

        return sources, errors

    @classmethod
    def load_owned_many(
        cls,
        db_session: Session,
        references: Iterable[tuple[str, int]],
        user_id: int,
    ) -> tuple[
        dict[tuple[str, int], TranslationSource],
        dict[tuple[str, int], str],
    ]:
        return cls.load_many(
            db_session,
            references,
            owner_user_id=user_id,
        )
