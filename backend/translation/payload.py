"""Normalized payload, source hash, translation slots, and protected values."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any


SUPPORTED_LOCALES = frozenset({'zh-CN', 'en-US'})

_SUMMARY_TEXT_FIELDS = frozenset({
    'title',
    'executive_summary',
    'one_sentence',
    'key_findings',
    'recommendations',
    'risks',
    'next_steps',
    'agent_summaries_used',
    'open_questions',
})
_AGENT_STRUCTURED_FIELDS = frozenset({
    'summary',
    'markdown_report',
    'visual_blocks',
})
_FINAL_STRUCTURED_FIELDS = frozenset({
    'title',
    'executive_summary',
    'key_findings',
    'recommendations',
    'risks',
    'next_steps',
    'agent_summaries_used',
    'evidence_refs',
    'visual_blocks',
    'markdown_report',
})
_PROTECTED_KEYS = frozenset({
    'block_id',
    'type',
    'evidence_refs',
    'confidence',
    'score',
    'status',
    'likelihood',
    'probability',
    'impact',
})
_VISUAL_BLOCK_TEXT_FIELDS = frozenset({
    'risk',
    'name',
    'mitigation',
    'action',
    'response',
    'option',
    'pros',
    'cons',
    'recommendation',
    'note',
})
_URL_RE = re.compile(r'^https?://\S+$', re.IGNORECASE)
_CODE_RE = re.compile(r'^(?:`[^`]+`|```[\s\S]*```)$')


@dataclass(frozen=True)
class TranslationSlot:
    """A stable path and text unit supplied to the translator."""

    id: str
    path: str
    text: str


@dataclass(frozen=True)
class NormalizedTranslationPayload:
    """Visible payload plus deterministic translation metadata."""

    payload: dict[str, Any]
    source_hash: str
    slots: tuple[TranslationSlot, ...]
    protected_manifest: dict[str, Any]


def canonical_source_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
    )
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def normalize_translation_payload(
    source_type: str,
    source: Any,
) -> NormalizedTranslationPayload:
    if source_type == 'message':
        payload = _normalize_message(source)
    elif source_type == 'leader_agent_result':
        payload = _normalize_agent_result(source)
    elif source_type == 'leader_final_report':
        payload = _normalize_final_report(source)
    else:
        raise ValueError('SOURCE_NOT_FOUND')

    slots, protected_manifest = _extract_slots(payload)
    if not slots:
        raise ValueError('SOURCE_NOT_TRANSLATABLE')
    return NormalizedTranslationPayload(
        payload=payload,
        source_hash=canonical_source_hash(payload),
        slots=tuple(slots),
        protected_manifest=protected_manifest,
    )


def _normalize_message(message: Any) -> dict[str, Any]:
    if getattr(message, 'content_locale', None) not in SUPPORTED_LOCALES:
        raise ValueError('SOURCE_NOT_TRANSLATABLE')
    if getattr(message, 'role', None) == 'user':
        raise ValueError('SOURCE_NOT_TRANSLATABLE')

    message_type = getattr(message, 'message_type', 'normal') or 'normal'
    if message_type == 'answer':
        raise ValueError('SOURCE_NOT_TRANSLATABLE')
    is_assistant_message = getattr(message, 'role', None) == 'assistant'
    is_leader_generated = (
        getattr(message, 'leader_session_id', None) is not None
    )
    if not is_assistant_message and not is_leader_generated:
        raise ValueError('SOURCE_NOT_TRANSLATABLE')

    content = getattr(message, 'content', None)
    if isinstance(content, str):
        text = content
    elif isinstance(content, dict):
        text = content.get('text')
    else:
        text = None
    if not isinstance(text, str) or not text.strip():
        raise ValueError('SOURCE_NOT_TRANSLATABLE')
    return {'text': text}


def _normalize_agent_result(result: Any) -> dict[str, Any]:
    _require_supported_locale(result)
    return {
        'content': _optional_text(getattr(result, 'content', None)),
        'summary': _normalize_summary(getattr(result, 'summary', None)),
        'structured_report': _normalize_structured_report(
            getattr(result, 'structured_report', None),
            _AGENT_STRUCTURED_FIELDS,
        ),
    }


def _normalize_final_report(report: Any) -> dict[str, Any]:
    _require_supported_locale(report)
    return {
        'report': _optional_text(getattr(report, 'report', None)),
        'executive_summary': _normalize_summary(
            getattr(report, 'executive_summary', None)
        ),
        'structured_report': _normalize_structured_report(
            getattr(report, 'structured_report', None),
            _FINAL_STRUCTURED_FIELDS,
        ),
    }


def _require_supported_locale(source: Any) -> None:
    if getattr(source, 'content_locale', None) not in SUPPORTED_LOCALES:
        raise ValueError('SOURCE_NOT_TRANSLATABLE')


def _optional_text(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _normalize_summary(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {
        key: deepcopy(item)
        for key, item in value.items()
        if key in _SUMMARY_TEXT_FIELDS or key in {'confidence', 'evidence_refs'}
    }


def _normalize_structured_report(
    value: Any,
    allowed_fields: frozenset[str],
) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None

    normalized: dict[str, Any] = {}
    for key, item in value.items():
        if key not in allowed_fields:
            continue
        if key == 'summary':
            normalized[key] = _normalize_summary(item)
        elif key == 'visual_blocks':
            normalized[key] = _normalize_visual_blocks(item)
        else:
            normalized[key] = deepcopy(item)
    return normalized


def _normalize_visual_blocks(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    blocks: list[dict[str, Any]] = []
    for block in value:
        if not isinstance(block, dict):
            continue
        blocks.append({
            key: deepcopy(block[key])
            for key in ('block_id', 'type', 'title', 'data', 'evidence_refs')
            if key in block
        })
    return blocks


def _extract_slots(
    payload: dict[str, Any],
) -> tuple[list[TranslationSlot], dict[str, Any]]:
    slots: list[TranslationSlot] = []
    protected: dict[str, Any] = {}

    def walk(value: Any, path: tuple[str | int, ...], key: str = '') -> None:
        pointer = _json_pointer(path)
        if isinstance(value, dict):
            for child_key, child in value.items():
                walk(child, (*path, child_key), child_key)
            return
        if isinstance(value, list):
            if key in _PROTECTED_KEYS or key == 'evidence_refs':
                protected[pointer] = deepcopy(value)
                return
            for index, child in enumerate(value):
                walk(child, (*path, index), key)
            return
        if isinstance(value, str) and _is_translatable_text(key, value, path):
            slots.append(TranslationSlot(
                id=f'slot_{len(slots) + 1:04d}',
                path=pointer,
                text=value,
            ))
            return
        protected[pointer] = deepcopy(value)

    walk(payload, ())
    return slots, protected


def _is_translatable_text(
    key: str,
    value: str,
    path: tuple[str | int, ...],
) -> bool:
    normalized_key = key.casefold()
    if _is_visual_block_data_path(path):
        return normalized_key in _VISUAL_BLOCK_TEXT_FIELDS
    if (
        normalized_key in _PROTECTED_KEYS
        or normalized_key == 'id'
        or normalized_key.endswith('_id')
    ):
        return False
    if not value.strip() or _URL_RE.fullmatch(value.strip()):
        return False
    return not _CODE_RE.fullmatch(value.strip())


def _is_visual_block_data_path(path: tuple[str | int, ...]) -> bool:
    return (
        len(path) >= 5
        and path[0] == 'structured_report'
        and path[1] == 'visual_blocks'
        and isinstance(path[2], int)
        and path[3] == 'data'
    )


def _json_pointer(path: tuple[str | int, ...]) -> str:
    if not path:
        return ''
    encoded = [
        str(part).replace('~', '~0').replace('/', '~1')
        for part in path
    ]
    return '/' + '/'.join(encoded)
