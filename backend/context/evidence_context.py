"""Select and render bounded evidence passages for LLM contexts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence


@dataclass(frozen=True)
class EvidenceContextSelection:
    """A rendered evidence selection plus budget diagnostics."""

    text: str
    selected_ids: tuple[str, ...]
    dropped_count: int
    used_chars: int


class EvidenceContextBuilder:
    """Centralizes evidence ordering, passage resolution, and context budgets."""

    def __init__(
        self,
        *,
        total_char_budget: int,
        item_char_budget: int,
        item_limit: int,
    ) -> None:
        if total_char_budget <= 0 or item_char_budget <= 0 or item_limit <= 0:
            raise ValueError("Evidence context budgets must be positive")
        self.total_char_budget = total_char_budget
        self.item_char_budget = item_char_budget
        self.item_limit = item_limit

    def build(
        self,
        evidence_map: Iterable[Mapping[str, Any]],
        *,
        raw_tool_results: Mapping[str, Any] | None = None,
        preferred_refs: Sequence[str] | None = None,
    ) -> EvidenceContextSelection:
        candidates = self._ordered_candidates(evidence_map, preferred_refs or ())
        lines: list[str] = []
        selected_ids: list[str] = []
        used_chars = 0

        for item in candidates:
            if len(selected_ids) >= self.item_limit:
                break
            evidence_id = str(item.get("evidence_id") or "").strip()
            passage = self._resolve_passage(item, raw_tool_results or {})
            if not evidence_id or not passage:
                continue

            passage = self._clip(passage, self.item_char_budget)
            title = self._normalize_text(item.get("title") or "Evidence")
            relation = self._relation(item)
            relation_label = f" ({relation})" if relation else ""
            line = f"- [evidence_id:{evidence_id}] {title}{relation_label}: {passage}"
            separator_chars = 1 if lines else 0
            remaining = self.total_char_budget - used_chars - separator_chars
            if remaining <= 0:
                break
            if len(line) > remaining:
                minimum_useful = len(f"- [evidence_id:{evidence_id}] {title}: ") + 40
                if remaining < minimum_useful:
                    break
                line = self._clip(line, remaining)

            lines.append(line)
            selected_ids.append(evidence_id)
            used_chars += len(line) + separator_chars

        eligible_count = sum(
            1
            for item in candidates
            if item.get("evidence_id") and self._resolve_passage(item, raw_tool_results or {})
        )
        return EvidenceContextSelection(
            text="\n".join(lines),
            selected_ids=tuple(selected_ids),
            dropped_count=max(0, eligible_count - len(selected_ids)),
            used_chars=used_chars,
        )

    @classmethod
    def _ordered_candidates(
        cls,
        evidence_map: Iterable[Mapping[str, Any]],
        preferred_refs: Sequence[str],
    ) -> list[Mapping[str, Any]]:
        candidates = [item for item in evidence_map if isinstance(item, Mapping)]
        preferred_order = {evidence_id: index for index, evidence_id in enumerate(preferred_refs)}

        preferred = sorted(
            (item for item in candidates if item.get("evidence_id") in preferred_order),
            key=lambda item: preferred_order[str(item.get("evidence_id"))],
        )
        remaining = [item for item in candidates if item.get("evidence_id") not in preferred_order]
        conflicts = [item for item in remaining if cls._relation(item) in {"contradicts", "qualifies"}]
        ordinary = [
            item
            for item in remaining
            if cls._relation(item) not in {"contradicts", "qualifies"}
        ]

        diverse: list[Mapping[str, Any]] = []
        repeated: list[Mapping[str, Any]] = []
        seen_sources: set[str] = set()
        for item in ordinary:
            source = cls._source_key(item)
            if source and source not in seen_sources:
                seen_sources.add(source)
                diverse.append(item)
            else:
                repeated.append(item)
        return preferred + conflicts + diverse + repeated

    @classmethod
    def _resolve_passage(
        cls,
        item: Mapping[str, Any],
        raw_tool_results: Mapping[str, Any],
    ) -> str:
        direct = cls._normalize_text(item.get("passage"))
        if direct:
            return direct

        evidence_id = str(item.get("evidence_id") or "").strip()
        raw = raw_tool_results.get(evidence_id)
        if raw is None:
            raw_ref = str(item.get("raw_ref") or "")
            prefix = "raw_tool_results."
            if raw_ref.startswith(prefix):
                raw = raw_tool_results.get(raw_ref[len(prefix):])
        if isinstance(raw, Mapping):
            resolved = cls._normalize_text(raw.get("passage") or raw.get("result"))
            if resolved:
                return resolved
        elif raw is not None:
            resolved = cls._normalize_text(raw)
            if resolved:
                return resolved
        return cls._normalize_text(item.get("excerpt"))

    @staticmethod
    def _normalize_text(value: Any) -> str:
        return " ".join(str(value or "").split())

    @staticmethod
    def _clip(text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        marker = "...(truncated)"
        return text[: max(0, limit - len(marker))] + marker

    @staticmethod
    def _relation(item: Mapping[str, Any]) -> str:
        return str(item.get("relation") or "").strip().lower()

    @staticmethod
    def _source_key(item: Mapping[str, Any]) -> str:
        locator = item.get("locator")
        source_file = locator.get("source_file") if isinstance(locator, Mapping) else None
        return str(
            item.get("source_id")
            or item.get("url")
            or source_file
            or item.get("evidence_id")
            or ""
        ).strip()
