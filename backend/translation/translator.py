"""Slot translation, reconstruction, and payload integrity validation."""
from __future__ import annotations

from copy import deepcopy
import json
import re
from typing import Any, Callable, Iterable

from .payload import NormalizedTranslationPayload, TranslationSlot


_FENCED_CODE_RE = re.compile(
    r'(^\s{0,3}(?P<fence>```|~~~)[^\n]*\n[\s\S]*?^\s{0,3}(?P=fence)\s*$)',
    re.MULTILINE,
)
_FENCE_LINE_RE = re.compile(r'^\s{0,3}(?:```|~~~)[^\n]*$', re.MULTILINE)
_INLINE_CODE_RE = re.compile(r'(?<!`)`[^`\n]+`(?!`)')
_URL_RE = re.compile(
    r'https?://[^\s<>\])}，。；：！？、“”‘’]+',
    re.IGNORECASE,
)
_EVIDENCE_REF_RE = re.compile(
    r'\[evidence_id:[^\]\s]+\]|\b(?:ev|evidence)[_-][A-Za-z0-9_-]+\b'
)
_UUID_RE = re.compile(
    r'\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-'
    r'[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b'
)
_NUMBER_RE = re.compile(r'(?<![\w])[-+]?\d+(?:[.,]\d+)*(?:%?)(?![\w])')
_EXPLICIT_ID_RE = re.compile(
    r'\b[A-Za-z][A-Za-z0-9]*(?:[_-][A-Za-z0-9]+)*[_-]\d+\b'
)

_TRANSLATION_BATCH_INPUT_TOKEN_LIMIT = 16000
_TRANSLATION_MAX_OUTPUT_TOKENS = 16384
_TRANSLATION_TIMEOUT_SECONDS = 240.0
_TRANSLATION_OUTPUT_EXPANSION = 2
_TRANSLATION_OUTPUT_PADDING = 256
_TRANSLATION_PROMPT_RESERVE = 512
_TRANSLATION_RESPONSE_MARGIN = 64


class TranslationIntegrityError(ValueError):
    pass


def translate_normalized_payload(
    normalized: NormalizedTranslationPayload,
    source_locale: str,
    target_locale: str,
    llm_service: Any,
) -> dict[str, Any]:
    context_limit = llm_service.get_context_limit()
    token_budget = min(
        _TRANSLATION_BATCH_INPUT_TOKEN_LIMIT,
        max(
            64,
            (
                context_limit
                - _TRANSLATION_PROMPT_RESERVE
                - _TRANSLATION_OUTPUT_PADDING
            ) // (_TRANSLATION_OUTPUT_EXPANSION + 1),
        ),
    )
    prepared_slots, slot_parts = _prepare_translation_slots(
        normalized.slots,
        token_budget,
        llm_service.estimate_tokens,
    )
    batches = batch_translation_slots(
        prepared_slots,
        token_budget,
        llm_service.estimate_tokens,
    )
    translated_parts: dict[str, str] = {}
    system_prompt = (
        'You translate user-visible historical AI content. Return only '
        'the requested JSON array and preserve all protected material.'
    )
    for batch in batches:
        prompt = _translation_prompt(batch, source_locale, target_locale)
        estimated_output = sum(
            llm_service.estimate_tokens(slot.text) for slot in batch
        )
        prompt_tokens = (
            llm_service.estimate_tokens(system_prompt)
            + llm_service.estimate_tokens(prompt)
            + _TRANSLATION_RESPONSE_MARGIN
        )
        available_output = context_limit - prompt_tokens
        if available_output < 128:
            raise TranslationIntegrityError('translation prompt exceeds context budget')
        response = llm_service.call_sync(
            prompt,
            system_prompt=system_prompt,
            max_tokens=min(
                llm_service.get_max_output_tokens(),
                _TRANSLATION_MAX_OUTPUT_TOKENS,
                available_output,
                max(
                    512,
                    estimated_output * _TRANSLATION_OUTPUT_EXPANSION
                    + _TRANSLATION_OUTPUT_PADDING,
                ),
            ),
            max_attempts=1,
            timeout=_TRANSLATION_TIMEOUT_SECONDS,
            reject_truncated=True,
        )
        translated_parts.update(_parse_batch_response(response, batch))

    translated_text = {
        slot.id: ''.join(
            literal if part_id is None else translated_parts[part_id]
            for part_id, literal in slot_parts[slot.id]
        )
        for slot in normalized.slots
    }

    translated = deepcopy(normalized.payload)
    for slot in normalized.slots:
        _set_json_pointer(translated, slot.path, translated_text[slot.id])
    validate_translated_payload(normalized, translated)
    return translated


def _prepare_translation_slots(
    slots: Iterable[TranslationSlot],
    token_budget: int,
    estimate_tokens: Callable[[str], int],
) -> tuple[
    tuple[TranslationSlot, ...],
    dict[str, tuple[tuple[str | None, str | None], ...]],
]:
    prepared: list[TranslationSlot] = []
    slot_parts: dict[str, tuple[tuple[str | None, str | None], ...]] = {}
    text_budget = token_budget - 32
    if text_budget < 1:
        raise TranslationIntegrityError('translation context budget is too small')

    for slot in slots:
        chunks = _split_markdown_text(slot.text, text_budget, estimate_tokens)
        if len(chunks) == 1 and not chunks[0][1]:
            prepared.append(slot)
            slot_parts[slot.id] = ((slot.id, None),)
            continue

        part_refs: list[tuple[str | None, str | None]] = []
        translated_index = 0
        for chunk, protected in chunks:
            if protected:
                part_refs.append((None, chunk))
                continue
            translated_index += 1
            part_id = f'{slot.id}__part_{translated_index:04d}'
            prepared.append(TranslationSlot(id=part_id, path=slot.path, text=chunk))
            part_refs.append((part_id, None))
        slot_parts[slot.id] = tuple(part_refs)

    return tuple(prepared), slot_parts


def _split_markdown_text(
    text: str,
    token_budget: int,
    estimate_tokens: Callable[[str], int],
) -> tuple[tuple[str, bool], ...]:
    if estimate_tokens(text) <= token_budget:
        return ((text, False),)

    pieces: list[tuple[str, bool]] = []
    cursor = 0
    for match in _FENCED_CODE_RE.finditer(text):
        if match.start() > cursor:
            pieces.extend((line, False) for line in text[cursor:match.start()].splitlines(keepends=True))
        pieces.append((match.group(0), True))
        cursor = match.end()
    if cursor < len(text):
        pieces.extend((line, False) for line in text[cursor:].splitlines(keepends=True))

    expanded: list[tuple[str, bool]] = []
    for piece, protected in pieces:
        if not piece:
            continue
        if protected:
            expanded.append((piece, True))
        elif estimate_tokens(piece) <= token_budget:
            expanded.append((piece, False))
        else:
            expanded.extend(
                (chunk, False)
                for chunk in _split_oversize_text(piece, token_budget, estimate_tokens)
            )

    chunks: list[tuple[str, bool]] = []
    current = ''
    for piece, protected in expanded:
        if protected:
            if current:
                chunks.append((current, False))
                current = ''
            chunks.append((piece, True))
            continue
        candidate = current + piece
        if current and estimate_tokens(candidate) > token_budget:
            chunks.append((current, False))
            current = piece
        else:
            current = candidate
    if current:
        chunks.append((current, False))
    if ''.join(chunk for chunk, _ in chunks) != text:
        raise TranslationIntegrityError('translation Markdown split changed source text')
    return tuple(chunks)


def _split_oversize_text(
    text: str,
    token_budget: int,
    estimate_tokens: Callable[[str], int],
) -> list[str]:
    chunks: list[str] = []
    remaining = text
    while remaining:
        low, high = 1, len(remaining)
        while low < high:
            middle = (low + high + 1) // 2
            if estimate_tokens(remaining[:middle]) <= token_budget:
                low = middle
            else:
                high = middle - 1
        split_at = low
        if split_at < len(remaining):
            candidate = remaining[:split_at]
            boundaries = list(re.finditer(r'[。！？.!?](?:\s+|$)|\s+', candidate))
            preferred = next(
                (match.end() for match in reversed(boundaries) if match.end() >= split_at // 2),
                None,
            )
            if preferred:
                split_at = preferred
        chunk = remaining[:split_at]
        if not chunk or estimate_tokens(chunk) > token_budget:
            raise TranslationIntegrityError('translation text cannot fit context budget')
        chunks.append(chunk)
        remaining = remaining[split_at:]
    return chunks


def batch_translation_slots(
    slots: Iterable[TranslationSlot],
    token_budget: int,
    estimate_tokens: Callable[[str], int],
) -> list[tuple[TranslationSlot, ...]]:
    batches: list[tuple[TranslationSlot, ...]] = []
    current: list[TranslationSlot] = []
    current_tokens = 0

    for slot in slots:
        slot_tokens = max(1, estimate_tokens(slot.text)) + 32
        if slot_tokens > token_budget:
            raise TranslationIntegrityError('translation slot exceeds context budget')
        if current and current_tokens + slot_tokens > token_budget:
            batches.append(tuple(current))
            current = []
            current_tokens = 0
        current.append(slot)
        current_tokens += slot_tokens
    if current:
        batches.append(tuple(current))
    return batches


def validate_translated_payload(
    normalized: NormalizedTranslationPayload,
    translated: dict[str, Any],
) -> None:
    _validate_shape(normalized.payload, translated)

    for path, expected in normalized.protected_manifest.items():
        if _get_json_pointer(translated, path) != expected:
            raise TranslationIntegrityError(f'protected value changed at {path}')

    for slot in normalized.slots:
        translated_text = _get_json_pointer(translated, slot.path)
        if not isinstance(translated_text, str) or not translated_text.strip():
            raise TranslationIntegrityError(f'invalid translated slot at {slot.path}')
        _validate_text_integrity(slot.text, translated_text, slot.path)


def _translation_prompt(
    slots: tuple[TranslationSlot, ...],
    source_locale: str,
    target_locale: str,
) -> str:
    payload = [{'id': slot.id, 'text': slot.text} for slot in slots]
    return (
        f'Translate each text from {source_locale} to {target_locale}. '
        'Preserve Markdown structure, fenced and inline code, URLs, evidence '
        'references, IDs, numbers, and enum-like machine values exactly. '
        'Return a JSON array with exactly one object per input in the same order; '
        'each object must have only "id" and "text". Input:\n'
        + json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
    )


def _parse_batch_response(
    response: str,
    batch: tuple[TranslationSlot, ...],
) -> dict[str, str]:
    try:
        items = json.loads(response)
    except (TypeError, json.JSONDecodeError) as exc:
        raise TranslationIntegrityError('translation response is not valid JSON') from exc
    if not isinstance(items, list) or len(items) != len(batch):
        raise TranslationIntegrityError('translation response item count changed')

    expected_ids = [slot.id for slot in batch]
    actual_ids: list[str] = []
    translated: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict) or set(item) != {'id', 'text'}:
            raise TranslationIntegrityError('translation response shape changed')
        slot_id = item['id']
        text = item['text']
        if not isinstance(slot_id, str) or not isinstance(text, str) or not text.strip():
            raise TranslationIntegrityError('translation response contains invalid values')
        actual_ids.append(slot_id)
        translated[slot_id] = text
    if actual_ids != expected_ids or len(translated) != len(batch):
        raise TranslationIntegrityError('translation slot ids changed')
    return translated


def _validate_shape(source: Any, translated: Any, path: str = '') -> None:
    if type(source) is not type(translated):
        raise TranslationIntegrityError(f'payload type changed at {path}')
    if isinstance(source, dict):
        if list(source) != list(translated):
            raise TranslationIntegrityError(f'payload keys changed at {path}')
        for key in source:
            _validate_shape(source[key], translated[key], f'{path}/{key}')
    elif isinstance(source, list):
        if len(source) != len(translated):
            raise TranslationIntegrityError(f'payload list length changed at {path}')
        for index, value in enumerate(source):
            _validate_shape(value, translated[index], f'{path}/{index}')


def _validate_text_integrity(source: str, translated: str, path: str) -> None:
    extractors = (
        _FENCE_LINE_RE.findall,
        _FENCED_CODE_RE.findall,
        _INLINE_CODE_RE.findall,
        _URL_RE.findall,
        _EVIDENCE_REF_RE.findall,
        _UUID_RE.findall,
        _NUMBER_RE.findall,
        _EXPLICIT_ID_RE.findall,
    )
    for extract in extractors:
        if extract(source) != extract(translated):
            raise TranslationIntegrityError(f'protected text changed at {path}')


def _set_json_pointer(payload: Any, pointer: str, value: Any) -> None:
    parts = _decode_json_pointer(pointer)
    target = payload
    for part in parts[:-1]:
        target = target[int(part)] if isinstance(target, list) else target[part]
    final = parts[-1]
    if isinstance(target, list):
        target[int(final)] = value
    else:
        target[final] = value


def _get_json_pointer(payload: Any, pointer: str) -> Any:
    target = payload
    for part in _decode_json_pointer(pointer):
        target = target[int(part)] if isinstance(target, list) else target[part]
    return target


def _decode_json_pointer(pointer: str) -> list[str]:
    if not pointer:
        return []
    return [
        part.replace('~1', '/').replace('~0', '~')
        for part in pointer.removeprefix('/').split('/')
    ]
