"""Run-scoped evidence persistence, claim validation, and owner detail reads."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional, Sequence
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from models import (
    Conversation,
    DecisionClaim,
    DecisionClaimEvidence,
    DecisionEvidence,
    DecisionEvidenceMetrics,
    DecisionRun,
    LeaderAgentResult,
    LeaderSession,
)
from services.decision_run_service import DecisionRunService
from utils.time_utils import utcnow_naive


EVIDENCE_SOURCE_TYPES = frozenset({
    'web',
    'knowledge',
    'memory',
    'user_input',
    'tool_result',
    'subtask_result',
    'agent_report',
})
EVIDENCE_COMPLETENESS = frozenset({'passage', 'snippet', 'legacy', 'unavailable'})
CLAIM_TYPES = frozenset({'fact', 'interpretation', 'recommendation', 'risk', 'uncertainty'})
CLAIM_RELATIONS = frozenset({'supports', 'contradicts', 'qualifies'})

_EVIDENCE_ID_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}$')
_CLAIM_ID_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}$')
_EXCERPT_LIMIT = 500
_PASSAGE_LIMIT = 4000


class DecisionEvidenceError(LookupError):
    """Base error translated into stable evidence API responses."""


class DecisionEvidenceNotFound(DecisionEvidenceError):
    pass


class DecisionEvidenceForbidden(DecisionEvidenceError):
    pass


class DecisionEvidenceUnavailable(DecisionEvidenceError):
    pass


class LegacyEvidenceUnresolvable(DecisionEvidenceError):
    pass


@dataclass(frozen=True)
class ClaimValidationResult:
    claims: tuple[DecisionClaim, ...]
    invalid_evidence_refs: tuple[str, ...]
    degradation_reasons: tuple[str, ...]


class DecisionEvidenceService:
    """Own evidence truth, compatibility projections, and claim relations."""

    def __init__(self, db_session: Session):
        self.db_session = db_session
        self.run_service = DecisionRunService(db_session)

    def persist_for_session(
        self,
        leader_session_id: int,
        evidence_map: Iterable[Mapping[str, Any]] | None,
        *,
        raw_tool_results: Mapping[str, Any] | None = None,
    ) -> Optional[list[dict]]:
        run = self.run_service.get_for_session(leader_session_id, for_update=True)
        if run is None:
            return None
        records = self.persist_for_run(
            run,
            evidence_map or (),
            raw_tool_results=raw_tool_results or {},
        )
        return [self.summary_projection(record) for record in records]

    def persist_for_run(
        self,
        run: DecisionRun,
        evidence_map: Iterable[Mapping[str, Any]],
        *,
        raw_tool_results: Mapping[str, Any],
    ) -> list[DecisionEvidence]:
        persisted: list[DecisionEvidence] = []
        seen: set[str] = set()
        for item in evidence_map:
            if not isinstance(item, Mapping):
                continue
            evidence_id = str(item.get('evidence_id') or '').strip()
            if evidence_id in seen or not _EVIDENCE_ID_RE.fullmatch(evidence_id):
                continue
            seen.add(evidence_id)
            persisted.append(
                self._upsert_evidence(run, evidence_id, item, raw_tool_results)
            )
        self.db_session.flush()
        self.refresh_quality_metrics(run)
        return persisted

    def summary_projection(self, evidence: DecisionEvidence) -> dict:
        return {
            'schema_version': 2,
            'evidence_id': evidence.evidence_id,
            'source_type': evidence.source_type,
            'source_id': evidence.source_id,
            'title': evidence.title,
            'excerpt': evidence.excerpt,
            'raw_ref': f'decision_evidence:{evidence.evidence_id}',
            'url': self._safe_url(evidence.url),
            'provider': evidence.provider,
            'locator': dict(evidence.locator or {}),
            'rank': evidence.rank,
            'relevance_score': evidence.relevance_score,
            'content_hash': evidence.content_hash,
            'source_version': evidence.source_version,
            'completeness': evidence.completeness,
            'agent_id': evidence.agent_id,
            'subtask_id': evidence.subtask_id,
            'created_at': self._iso(evidence.retrieved_at),
        }

    def claim_projection(self, claim: DecisionClaim) -> dict:
        relation_rows = self.db_session.query(
            DecisionClaimEvidence.relation,
            DecisionEvidence.evidence_id,
        ).join(
            DecisionEvidence,
            DecisionEvidence.id == DecisionClaimEvidence.decision_evidence_id,
        ).filter(
            DecisionClaimEvidence.decision_claim_id == claim.id,
        ).order_by(DecisionClaimEvidence.sequence.asc()).all()
        return {
            'claim_id': claim.claim_id,
            'text': claim.text,
            'claim_type': claim.claim_type,
            'confidence': claim.confidence,
            'support_status': claim.support_status,
            'evidence_relations': [
                {'evidence_id': evidence_id, 'relation': relation}
                for relation, evidence_id in relation_rows
            ],
            'agent_refs': list(claim.agent_refs or []),
        }

    def detail_for_owner(
        self,
        run_id: str,
        evidence_id: str,
        user_id: int,
    ) -> dict:
        run = self.run_service.get(run_id)
        if run is None:
            raise DecisionEvidenceNotFound('decision_run_not_found')
        if not self.run_service.owner_can_access(run, user_id):
            raise DecisionEvidenceForbidden('decision_evidence_forbidden')
        evidence = self._get_evidence(run.id, evidence_id)
        if evidence is None:
            self._increment_detail_load_failure(run)
            raise DecisionEvidenceNotFound('decision_evidence_not_found')
        try:
            return self._detail_projection(evidence)
        except DecisionEvidenceUnavailable:
            self._increment_detail_load_failure(run)
            raise

    def detail_for_session_owner(
        self,
        leader_session_id: int,
        evidence_id: str,
        user_id: int,
    ) -> dict:
        leader_session = self.db_session.get(LeaderSession, leader_session_id)
        if leader_session is None:
            raise DecisionEvidenceNotFound('leader_session_not_found')
        if not self._owns_conversation(leader_session.conversation_id, user_id):
            raise DecisionEvidenceForbidden('decision_evidence_forbidden')

        run = self.run_service.get_for_session(leader_session_id)
        if run is not None:
            evidence = self._get_evidence(run.id, evidence_id)
            if evidence is not None:
                try:
                    return self._detail_projection(evidence)
                except DecisionEvidenceUnavailable:
                    self._increment_detail_load_failure(run)
                    raise
            # DecisionRun 存在但结构化证据缺失（例如持久化降级或证据 ID 被过滤）：
            # 回退到 LeaderAgentResult.evidence_map / raw_tool_results 解析段落。
            # 仅当 legacy 也无法解析时，才把 run 级证据未命中记录为一次加载失败并抛 404。
            try:
                return self._legacy_detail(leader_session_id, evidence_id)
            except (LegacyEvidenceUnresolvable, DecisionEvidenceNotFound):
                pass
            self._increment_detail_load_failure(run)
            raise DecisionEvidenceNotFound('decision_evidence_not_found')
        return self._legacy_detail(leader_session_id, evidence_id)

    def quality_metrics_for_owner(self, run_id: str, user_id: int) -> dict:
        run = self.run_service.get(run_id)
        if run is None:
            raise DecisionEvidenceNotFound('decision_run_not_found')
        if not self.run_service.owner_can_access(run, user_id):
            raise DecisionEvidenceForbidden('decision_evidence_forbidden')
        metrics = self.db_session.query(DecisionEvidenceMetrics).filter_by(
            decision_run_id=run.id
        ).first()
        if metrics is None:
            metrics = self.refresh_quality_metrics(run)
        return metrics.to_dict()

    def record_context_dropped_for_session(
        self,
        leader_session_id: int,
        dropped_count: int,
    ) -> Optional[DecisionEvidenceMetrics]:
        run = self.run_service.get_for_session(leader_session_id, for_update=True)
        if run is None:
            return None
        return self.refresh_quality_metrics(
            run,
            context_dropped_count=max(0, int(dropped_count or 0)),
        )

    def persist_claims_for_session(
        self,
        leader_session_id: int,
        claims: Iterable[Mapping[str, Any]],
    ) -> ClaimValidationResult:
        run = self.run_service.get_for_session(leader_session_id, for_update=True)
        if run is None:
            return ClaimValidationResult((), (), ())
        return self.persist_claims_for_run(run, claims)

    def persist_claims_for_run(
        self,
        run: DecisionRun,
        claims: Iterable[Mapping[str, Any]],
    ) -> ClaimValidationResult:
        persisted: list[DecisionClaim] = []
        invalid_refs: list[str] = []
        degradation_reasons: list[str] = []

        for item in claims:
            if not isinstance(item, Mapping):
                continue
            claim_id = str(item.get('claim_id') or '').strip()
            text = str(item.get('text') or '').strip()
            claim_type = str(item.get('claim_type') or '').strip()
            if not _CLAIM_ID_RE.fullmatch(claim_id) or not text or claim_type not in CLAIM_TYPES:
                continue

            requested_relations = self._requested_claim_relations(item)
            normalized_relations = [
                (evidence_id, relation)
                for evidence_id, relation in requested_relations
                if _EVIDENCE_ID_RE.fullmatch(evidence_id) and relation in CLAIM_RELATIONS
            ]
            malformed_refs = [
                evidence_id
                for evidence_id, relation in requested_relations
                if not _EVIDENCE_ID_RE.fullmatch(evidence_id) or relation not in CLAIM_RELATIONS
            ]
            requested_ids = {evidence_id for evidence_id, _ in normalized_relations}
            available = {
                evidence.evidence_id: evidence
                for evidence in self.db_session.query(DecisionEvidence).filter(
                    DecisionEvidence.decision_run_id == run.id,
                    DecisionEvidence.evidence_id.in_(requested_ids or {'__none__'}),
                )
            }
            valid_relations = [
                (available[evidence_id], relation)
                for evidence_id, relation in normalized_relations
                if evidence_id in available
            ]
            item_invalid = [
                *malformed_refs,
                *[
                    evidence_id
                    for evidence_id, _ in normalized_relations
                    if evidence_id not in available
                ],
            ]
            invalid_refs.extend(item_invalid)
            if item_invalid:
                degradation_reasons.append('invalid_evidence_reference')

            support_status = self._support_status(
                claim_type,
                [relation for _, relation in valid_relations],
            )
            if claim_type == 'fact' and support_status == 'unsupported':
                degradation_reasons.append('unsupported_fact_claim')
            if support_status == 'conflicting':
                degradation_reasons.append('conflicting_claim')

            claim = self.db_session.query(DecisionClaim).filter_by(
                decision_run_id=run.id,
                claim_id=claim_id,
            ).with_for_update().first()
            if claim is None:
                claim = DecisionClaim(decision_run_id=run.id, claim_id=claim_id)
                self.db_session.add(claim)
            claim.text = text
            claim.claim_type = claim_type
            claim.confidence = self._confidence(item.get('confidence'))
            claim.support_status = support_status
            claim.evidence_ref_count = len(requested_relations)
            claim.resolved_evidence_ref_count = len(valid_relations)
            refs = item.get('agent_refs')
            claim.agent_refs = list(refs) if isinstance(refs, (list, tuple)) else []
            claim.updated_at = utcnow_naive()
            self.db_session.flush()

            self.db_session.query(DecisionClaimEvidence).filter_by(
                decision_claim_id=claim.id
            ).delete(synchronize_session=False)
            for sequence, (evidence, relation) in enumerate(valid_relations):
                self.db_session.add(DecisionClaimEvidence(
                    decision_claim_id=claim.id,
                    decision_evidence_id=evidence.id,
                    relation=relation,
                    sequence=sequence,
                ))
            persisted.append(claim)

        normalized_reasons = tuple(dict.fromkeys(degradation_reasons))
        if normalized_reasons:
            existing_reasons = list(run.degradation_reasons or [])
            self.run_service.mark_quality(
                run,
                'degraded',
                [*existing_reasons, *normalized_reasons],
            )
        self.db_session.flush()
        self.refresh_quality_metrics(run)
        return ClaimValidationResult(
            claims=tuple(persisted),
            invalid_evidence_refs=tuple(dict.fromkeys(invalid_refs)),
            degradation_reasons=normalized_reasons,
        )

    def refresh_quality_metrics(
        self,
        run: DecisionRun,
        *,
        context_dropped_count: Optional[int] = None,
    ) -> DecisionEvidenceMetrics:
        metrics = self.db_session.query(DecisionEvidenceMetrics).filter_by(
            decision_run_id=run.id
        ).with_for_update().first()
        if metrics is None:
            metrics = DecisionEvidenceMetrics(decision_run_id=run.id)
            self.db_session.add(metrics)
            self.db_session.flush()

        evidence_rows = self.db_session.query(DecisionEvidence).filter_by(
            decision_run_id=run.id
        ).all()
        claim_rows = self.db_session.query(DecisionClaim).filter_by(
            decision_run_id=run.id
        ).all()
        cited_ids = {
            row[0]
            for row in self.db_session.query(
                DecisionClaimEvidence.decision_evidence_id
            ).join(
                DecisionClaim,
                DecisionClaim.id == DecisionClaimEvidence.decision_claim_id,
            ).filter(DecisionClaim.decision_run_id == run.id).all()
        }

        refs_total = sum(claim.evidence_ref_count or 0 for claim in claim_rows)
        refs_resolved = sum(
            claim.resolved_evidence_ref_count or 0 for claim in claim_rows
        )
        claim_total = len(claim_rows)
        supported_total = sum(
            1 for claim in claim_rows if claim.support_status == 'supported'
        )
        source_keys = {
            self._source_identity(evidence)
            for evidence in evidence_rows
            if self._source_identity(evidence)
        }

        metrics.evidence_candidates_total = len(evidence_rows)
        metrics.evidence_cited_total = len(cited_ids)
        metrics.evidence_refs_total = refs_total
        metrics.evidence_refs_resolved_total = refs_resolved
        metrics.evidence_ref_resolvable_ratio = (
            round(refs_resolved / refs_total, 6) if refs_total else None
        )
        metrics.supported_claim_ratio = (
            round(supported_total / claim_total, 6) if claim_total else None
        )
        metrics.unique_source_count = len(source_keys)
        metrics.snippet_only_count = sum(
            1 for evidence in evidence_rows if evidence.completeness == 'snippet'
        )
        if context_dropped_count is not None:
            metrics.evidence_context_dropped_count = max(
                0, int(context_dropped_count)
            )
        metrics.updated_at = utcnow_naive()
        self.db_session.flush()
        return metrics

    def _increment_detail_load_failure(self, run: DecisionRun) -> None:
        metrics = self.refresh_quality_metrics(run)
        metrics.evidence_detail_load_failure_count = (
            metrics.evidence_detail_load_failure_count or 0
        ) + 1
        metrics.updated_at = utcnow_naive()
        self.db_session.flush()

    def _upsert_evidence(
        self,
        run: DecisionRun,
        evidence_id: str,
        item: Mapping[str, Any],
        raw_tool_results: Mapping[str, Any],
    ) -> DecisionEvidence:
        evidence = self._get_evidence(run.id, evidence_id, for_update=True)
        if evidence is None:
            evidence = DecisionEvidence(
                decision_run_id=run.id,
                evidence_id=evidence_id,
            )
            self.db_session.add(evidence)

        passage = self._resolve_passage(item, raw_tool_results)
        excerpt = self._clean_text(item.get('excerpt') or passage)
        excerpt = self._clip(excerpt, _EXCERPT_LIMIT)
        if passage:
            passage = self._clip(passage, _PASSAGE_LIMIT)
        hash_source = passage or excerpt
        content_hash = str(item.get('content_hash') or '').strip().lower()
        if not re.fullmatch(r'[0-9a-f]{64}', content_hash):
            content_hash = hashlib.sha256(hash_source.encode('utf-8')).hexdigest()

        source_type = str(item.get('source_type') or 'tool_result').strip()
        if source_type not in EVIDENCE_SOURCE_TYPES:
            source_type = 'tool_result'
        completeness = str(item.get('completeness') or 'legacy').strip()
        if completeness not in EVIDENCE_COMPLETENESS:
            completeness = 'legacy'
        locator = item.get('locator')

        evidence.source_type = source_type
        evidence.source_id = self._optional_text(item.get('source_id'), 500)
        evidence.title = self._clean_text(item.get('title') or 'Evidence')
        evidence.url = self._safe_url(item.get('url'))
        evidence.provider = self._optional_text(item.get('provider'), 100)
        evidence.locator = dict(locator) if isinstance(locator, Mapping) else {}
        evidence.excerpt = excerpt
        if passage or evidence.passage is None:
            evidence.passage = passage or None
        evidence.completeness = completeness
        evidence.content_hash = content_hash
        evidence.source_version = self._optional_text(item.get('source_version'), 200)
        evidence.relevance_score = self._bounded_float(item.get('relevance_score'))
        evidence.rank = self._nonnegative_int(item.get('rank'))
        evidence.agent_id = self._optional_text(item.get('agent_id'), 100)
        evidence.subtask_id = self._optional_text(item.get('subtask_id'), 100)
        evidence.updated_at = utcnow_naive()
        return evidence

    def _detail_projection(self, evidence: DecisionEvidence) -> dict:
        if not evidence.passage or evidence.completeness == 'unavailable':
            raise DecisionEvidenceUnavailable('decision_evidence_unavailable')
        payload = self.summary_projection(evidence)
        payload.update({
            'passage': evidence.passage,
            'truncated': self._is_truncated(evidence.passage),
            'source_available': evidence.completeness != 'unavailable',
        })
        return payload

    def _legacy_detail(self, leader_session_id: int, evidence_id: str) -> dict:
        found_summary: Optional[Mapping[str, Any]] = None
        for result in self.db_session.query(LeaderAgentResult).filter_by(
            leader_session_id=leader_session_id
        ).order_by(LeaderAgentResult.sequence_number.asc()):
            evidence_map = result.evidence_map if isinstance(result.evidence_map, list) else []
            for item in evidence_map:
                if not isinstance(item, Mapping) or item.get('evidence_id') != evidence_id:
                    continue
                found_summary = item
                passage = self._resolve_passage(item, result.raw_tool_results or {})
                if not passage:
                    raise LegacyEvidenceUnresolvable('legacy_evidence_unresolvable')
                url = self._safe_url(item.get('url'))
                return {
                    **{key: value for key, value in item.items() if key != 'raw_ref'},
                    'schema_version': 1,
                    'completeness': 'legacy',
                    'url': url,
                    'passage': passage,
                    'truncated': self._is_truncated(passage),
                    'source_available': True,
                    'legacy': True,
                }
        if found_summary is not None:
            raise LegacyEvidenceUnresolvable('legacy_evidence_unresolvable')
        raise DecisionEvidenceNotFound('decision_evidence_not_found')

    def _get_evidence(
        self,
        decision_run_id: int,
        evidence_id: str,
        *,
        for_update: bool = False,
    ) -> Optional[DecisionEvidence]:
        query = self.db_session.query(DecisionEvidence).filter_by(
            decision_run_id=decision_run_id,
            evidence_id=evidence_id,
        )
        if for_update:
            query = query.with_for_update()
        return query.first()

    def _owns_conversation(self, conversation_id: int, user_id: int) -> bool:
        return self.db_session.query(Conversation.id).filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        ).first() is not None

    @classmethod
    def _normalize_claim_relations(
        cls,
        item: Mapping[str, Any],
    ) -> list[tuple[str, str]]:
        return [
            (evidence_id, relation)
            for evidence_id, relation in cls._requested_claim_relations(item)
            if _EVIDENCE_ID_RE.fullmatch(evidence_id) and relation in CLAIM_RELATIONS
        ]

    @classmethod
    def _requested_claim_relations(
        cls,
        item: Mapping[str, Any],
    ) -> list[tuple[str, str]]:
        normalized: list[tuple[str, str]] = []
        relations = item.get('evidence_relations')
        if isinstance(relations, Sequence) and not isinstance(relations, (str, bytes)):
            for relation_item in relations:
                if not isinstance(relation_item, Mapping):
                    continue
                evidence_id = str(relation_item.get('evidence_id') or '').strip()
                relation = str(relation_item.get('relation') or 'supports').strip()
                if evidence_id:
                    normalized.append((evidence_id, relation))
        refs = item.get('evidence_refs')
        if isinstance(refs, Sequence) and not isinstance(refs, (str, bytes)):
            for ref in refs:
                evidence_id = str(ref or '').strip()
                if evidence_id:
                    normalized.append((evidence_id, 'supports'))
        return list(dict.fromkeys(normalized))

    @staticmethod
    def _source_identity(evidence: DecisionEvidence) -> str:
        locator = evidence.locator if isinstance(evidence.locator, Mapping) else {}
        return str(
            evidence.source_id
            or evidence.url
            or locator.get('source_file')
            or locator.get('document_id')
            or evidence.evidence_id
            or ''
        ).strip()

    @staticmethod
    def _support_status(claim_type: str, relations: Sequence[str]) -> str:
        relation_set = set(relations)
        if 'supports' in relation_set and 'contradicts' in relation_set:
            return 'conflicting'
        if claim_type == 'fact' and 'supports' not in relation_set:
            return 'unsupported'
        if 'supports' in relation_set and 'qualifies' not in relation_set:
            return 'supported'
        if relation_set:
            return 'partial'
        return 'unsupported'

    @classmethod
    def _resolve_passage(
        cls,
        item: Mapping[str, Any],
        raw_tool_results: Mapping[str, Any],
    ) -> str:
        direct = cls._clean_text(item.get('passage'))
        if direct:
            return direct
        evidence_id = str(item.get('evidence_id') or '').strip()
        raw = raw_tool_results.get(evidence_id)
        if raw is None:
            raw_ref = str(item.get('raw_ref') or '')
            prefix = 'raw_tool_results.'
            if raw_ref.startswith(prefix):
                raw = raw_tool_results.get(raw_ref[len(prefix):])
        if isinstance(raw, Mapping):
            return cls._clean_text(raw.get('passage') or raw.get('result'))
        return cls._clean_text(raw)

    @staticmethod
    def _safe_url(value: Any) -> Optional[str]:
        url = str(value or '').strip()
        if not url:
            return None
        try:
            parsed = urlsplit(url)
        except ValueError:
            return None
        if parsed.scheme.lower() not in {'http', 'https'} or not parsed.netloc:
            return None
        return url

    @staticmethod
    def _confidence(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            confidence = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError('Claim confidence must be between 0 and 1') from exc
        if not 0 <= confidence <= 1:
            raise ValueError('Claim confidence must be between 0 and 1')
        return confidence

    @staticmethod
    def _bounded_float(value: Any) -> Optional[float]:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if 0 <= number <= 1 else None

    @staticmethod
    def _nonnegative_int(value: Any) -> Optional[int]:
        try:
            number = int(value)
        except (TypeError, ValueError):
            return None
        return number if number >= 0 else None

    @staticmethod
    def _optional_text(value: Any, limit: int) -> Optional[str]:
        text = str(value or '').strip()
        return text[:limit] if text else None

    @staticmethod
    def _clean_text(value: Any) -> str:
        return ' '.join(str(value or '').split())

    @staticmethod
    def _clip(value: str, limit: int) -> str:
        if len(value) <= limit:
            return value
        marker = '...(truncated)'
        return value[:limit - len(marker)] + marker

    @staticmethod
    def _is_truncated(value: str) -> bool:
        return value.endswith('...(truncated)') or value.endswith('...(已截断)')

    @staticmethod
    def _iso(value) -> Optional[str]:
        return value.isoformat() + 'Z' if value else None
