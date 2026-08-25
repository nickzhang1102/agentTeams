"""Structured report helpers for Leader reports."""
from __future__ import annotations

import re
from typing import Any

from schemas.leader import (
    AgentReportSummary,
    ClaimEvidenceReference,
    FinalReportResult,
    ReportClaim,
    StructuredAgentReport,
)


_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$")
_BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.+?)\s*$")
_GENERIC_SUMMARY_RE = re.compile(
    r"^(?:分析报告|完整分析|专业分析报告|最终分析报告|分析范围|分析背景|背景分析|"
    r"综合分析报告|我的综合分析报告|以下是我的综合分析报告|核心分析|关键发现|结论与建议|结论建议|建议|风险提示|风险|"
    r"摘要|总结|前言|引言|概述)$",
    re.IGNORECASE,
)
_ROLE_ONLY_LINE_RE = re.compile(
    r"^(?:[\u4e00-\u9fa5A-Za-z0-9·_\-\s]{2,40}"
    r"(?:分析师|专家|顾问|研究员|经理|总监|工程师|架构师|交易员|投资经理)"
    r"(?:（[^）]{0,20}）|\([^)]{0,20}\))?)$"
)
_LEAD_IN_PREFIXES = (
    re.compile(r"^(?:好的|是的|明白|收到|遵照您的指示)[，,。；;：:\s]*"),
    re.compile(r"^作为[^，。；:：]{0,24}[，,:：]\s*"),
    re.compile(r"^从[^，。；:：]{0,30}角度(?:来看|出发)?[，,:：]\s*"),
    re.compile(r"^我?从[^，。；:：]{0,30}角度[^：:]{0,20}[：:]\s*"),
    re.compile(r"^针对[^，。；:：]{0,30}[，,:：]\s*"),
    re.compile(r"^基于[^，。；:：]{0,40}[，,:：]\s*"),
    re.compile(r"^根据[^，。；:：]{0,40}[，,:：]\s*"),
    re.compile(r"^(?:以下是|下面是)[^：:]{0,40}[：:]\s*"),
    re.compile(r"^(?:本次|本次分析|本次评估)[^：:]{0,20}[：:]\s*"),
    re.compile(r"^(?:在|于)[^，。；:：]{0,20}?(?:背景|环境|框架)下[，,:：]\s*"),
    re.compile(r"^(?:尊敬的|各位)[^，。；:：]{0,10}[，,:：]\s*"),
    re.compile(
        r"^(?:[\u4e00-\u9fa5A-Za-z0-9·_\-\s]{2,40}"
        r"(?:分析师|专家|顾问|研究员|经理|总监|工程师|架构师|交易员|投资经理)"
        r"(?:（[^）]{0,20}）|\([^)]{0,20}\))?)"
        r"(?:认为|判断|指出|建议|结论是|观点是|[，,:：-])\s*"
    ),
)
_PREAMBLE_SENTENCE_RE = re.compile(
    r"(?:遵照.*指示|仔细审阅|已经审阅|已审阅|提供的.*资料|以下是.*报告|下面是.*报告|"
    r"作为.*(?:专家|分析师|顾问|研究员|医生|医师|工程师|架构师|经理|总监))"
)
_DEMOGRAPHIC_ONLY_RE = re.compile(
    r"^(?:患者|病人|受检者|基本信息)?[\s，,、；;:：-]*"
    r"(?:(?:男|女|男性|女性)[\s，,、；;]*(?:\d{1,3}\s*岁(?:左右)?)|"
    r"(?:\d{1,3}\s*岁(?:左右)?)[\s，,、；;]*(?:男|女|男性|女性)|"
    r"年龄[\s:：]*(?:\d{1,3}\s*岁(?:左右)?)[\s，,、；;]*性别[\s:：]*(?:男|女|男性|女性)|"
    r"性别[\s:：]*(?:男|女|男性|女性)[\s，,、；;]*年龄[\s:：]*(?:\d{1,3}\s*岁(?:左右)?))"
    r"[\s，,、；;。.!！?？]*$"
)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？!?])\s+|(?<=[。！？!?])")
_EVIDENCE_MARKER_RE = re.compile(r"\[evidence_id:([^\]\s]+)\]")


def build_agent_structured_report(
    markdown_report: str,
    evidence_refs: list[str] | None = None,
    claim_id_prefix: str = "agent",
) -> dict[str, Any]:
    """Build a lightweight structured Agent report from Markdown content."""
    summary = build_agent_report_summary(markdown_report, evidence_refs=evidence_refs)
    claims = _build_agent_claims(summary, claim_id_prefix=claim_id_prefix)
    return StructuredAgentReport(
        summary=summary,
        markdown_report=markdown_report or "",
        visual_blocks=[],
        claims=claims,
    ).model_dump()


def _build_agent_claims(
    summary: AgentReportSummary,
    *,
    claim_id_prefix: str,
) -> list[ReportClaim]:
    safe_prefix = re.sub(r"[^A-Za-z0-9_.:-]+", "_", claim_id_prefix).strip("_") or "agent"
    groups = (
        ("fact", summary.key_findings),
        ("recommendation", summary.recommendations),
        ("risk", summary.risks),
        ("uncertainty", summary.open_questions),
    )
    claims: list[ReportClaim] = []
    for claim_type, items in groups:
        for item in items:
            refs = list(dict.fromkeys(_EVIDENCE_MARKER_RE.findall(item or "")))
            text = _EVIDENCE_MARKER_RE.sub("", item or "").strip(" \t.,;，。；")
            if not text:
                continue
            claims.append(ReportClaim(
                claim_id=f"{safe_prefix}_claim_{claim_type}_{len(claims) + 1}",
                text=text,
                claim_type=claim_type,
                confidence=summary.confidence,
                evidence_relations=[
                    ClaimEvidenceReference(evidence_id=evidence_id, relation="supports")
                    for evidence_id in refs
                ],
                agent_refs=[safe_prefix],
            ))
    return claims


def build_agent_report_summary(
    markdown_report: str,
    evidence_refs: list[str] | None = None,
) -> AgentReportSummary:
    """Extract a deterministic MVP summary from an Agent Markdown report."""
    text = (markdown_report or "").strip()
    if not text:
        return AgentReportSummary(one_sentence="无执行结果", confidence=0.0, evidence_refs=evidence_refs or [])

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    # Extract sections first — they are naturally free of opening preamble.
    bullets = _extract_bullets(lines)
    recommendations = _section_items(lines, ("建议", "recommendation", "行动", "next step"))[:3]
    risks = _section_items(lines, ("风险", "注意", "risk"))[:3]
    open_questions = _section_items(lines, ("待确认", "open question", "问题"))[:3]

    one_sentence = _build_one_sentence_summary(lines, bullets[:3], recommendations, risks)
    confidence = _estimate_summary_confidence(
        text=text,
        one_sentence=one_sentence,
        key_findings=bullets[:3],
        recommendations=recommendations,
        risks=risks,
        evidence_refs=evidence_refs or [],
        open_questions=open_questions,
    )

    return AgentReportSummary(
        one_sentence=one_sentence,
        key_findings=bullets[:3],
        recommendations=recommendations,
        risks=risks,
        confidence=confidence,
        evidence_refs=evidence_refs or [],
        open_questions=open_questions,
    )


def final_report_summary_payload(report: FinalReportResult | None) -> dict[str, Any] | None:
    """Return final report summary payload for SSE/API/DB."""
    if report is None:
        return None
    return report.summary_payload()


def final_report_structured_payload(report: FinalReportResult | None) -> dict[str, Any] | None:
    """Return full structured final report payload for SSE/API/DB."""
    if report is None:
        return None
    return report.structured_payload()


def _build_one_sentence_summary(
    lines: list[str],
    key_findings: list[str],
    recommendations: list[str],
    risks: list[str],
) -> str:
    explicit_summary = _first_section_item(
        lines,
        ("一句话摘要", "摘要", "概述", "overview", "summary", "核心结论"),
        excluded_keywords=("建议", "recommendation", "风险", "risk"),
    )
    if explicit_summary:
        return explicit_summary

    first_sentence = _first_meaningful_sentence(lines, allow_headings=False)
    if first_sentence:
        return first_sentence

    if key_findings and recommendations:
        return _truncate(f"报告指出：{key_findings[0]}；建议：{recommendations[0]}")
    if key_findings:
        return _truncate(f"报告指出：{key_findings[0]}")
    if recommendations:
        return _truncate(f"报告围绕行动方案展开；建议：{recommendations[0]}")
    if risks:
        return _truncate(f"报告提示：{risks[0]}")

    return _first_meaningful_sentence(lines, allow_headings=True) or "无摘要"


def _first_meaningful_sentence(lines: list[str], *, allow_headings: bool = True) -> str:
    for line in lines:
        heading = _HEADING_RE.match(line)
        if heading:
            if not allow_headings:
                continue
            title = _sanitize_summary_candidate(heading.group(1))
            if title:
                return _truncate(title)
            continue
        if _BULLET_RE.match(line):
            continue
        if _is_structured_inline_line(line):
            continue
        for candidate in _summary_candidates_from_line(line):
            return _truncate(candidate)
    return ""


def _extract_bullets(lines: list[str]) -> list[str]:
    items: list[str] = []
    in_non_finding_section = False
    for line in lines:
        heading = _HEADING_RE.match(line)
        if heading:
            title = heading.group(1).lower()
            in_non_finding_section = any(
                keyword in title
                for keyword in ("建议", "recommendation", "行动", "next step", "风险", "注意", "risk", "待确认", "open question", "问题")
            )
            continue
        if in_non_finding_section:
            continue
        match = _BULLET_RE.match(line)
        if match:
            items.append(_truncate(match.group(1)))
    return items


def _section_items(lines: list[str], keywords: tuple[str, ...]) -> list[str]:
    items: list[str] = []
    in_section = False
    for line in lines:
        heading = _HEADING_RE.match(line)
        if heading:
            title = heading.group(1).lower()
            in_section = any(keyword.lower() in title for keyword in keywords)
            continue
        inline_item = _inline_section_item(line, keywords)
        if inline_item:
            _append_unique(items, inline_item)
            continue
        if not in_section:
            continue
        bullet = _BULLET_RE.match(line)
        if bullet:
            _append_unique(items, _truncate(bullet.group(1)))
        elif line:
            _append_unique(items, _truncate(_normalize_line(line)))
    return items


def _first_section_item(
    lines: list[str],
    keywords: tuple[str, ...],
    excluded_keywords: tuple[str, ...] = (),
) -> str:
    in_section = False
    for line in lines:
        heading = _HEADING_RE.match(line)
        if heading:
            title = heading.group(1).lower()
            has_keyword = any(keyword.lower() in title for keyword in keywords)
            has_excluded = any(keyword.lower() in title for keyword in excluded_keywords)
            in_section = has_keyword and not has_excluded
            continue

        inline_item = _inline_section_item(line, keywords)
        if inline_item:
            return inline_item
        if not in_section:
            continue

        bullet = _BULLET_RE.match(line)
        candidate = bullet.group(1) if bullet else line
        candidate = _sanitize_summary_candidate(candidate)
        if candidate:
            return _truncate(candidate)
    return ""


def _truncate(text: str, limit: int = 180) -> str:
    normalized = " ".join((text or "").split())
    return normalized[:limit].rstrip() + ("..." if len(normalized) > limit else "")


def _normalize_line(text: str) -> str:
    return re.sub(r"[*_`>#]+", "", (text or "")).strip()


def _sanitize_summary_candidate(text: str) -> str:
    candidate = _normalize_line(text)
    inline_item = _split_inline_label(candidate)
    if inline_item:
        _, candidate = inline_item
    previous = None
    while candidate and candidate != previous:
        previous = candidate
        for pattern in _LEAD_IN_PREFIXES:
            candidate = pattern.sub("", candidate).strip()
    if (
        _GENERIC_SUMMARY_RE.match(candidate)
        or _ROLE_ONLY_LINE_RE.match(candidate)
        or _is_preamble_sentence(candidate)
        or _is_demographic_only_sentence(candidate)
    ):
        return ""
    return candidate


def _summary_candidates_from_line(line: str) -> list[str]:
    normalized = _normalize_line(line)
    if not normalized:
        return []
    candidates: list[str] = []
    for part in _SENTENCE_SPLIT_RE.split(normalized):
        candidate = _sanitize_summary_candidate(part)
        if candidate:
            candidates.append(candidate)
    if candidates:
        return candidates
    candidate = _sanitize_summary_candidate(normalized)
    return [candidate] if candidate else []


def _is_preamble_sentence(candidate: str) -> bool:
    normalized = candidate.strip("。！？!?；;，, ")
    if not normalized:
        return True
    if _PREAMBLE_SENTENCE_RE.search(normalized):
        return True
    return normalized in {"好的", "遵照您的指示", "以下是", "下面是"}


def _is_demographic_only_sentence(candidate: str) -> bool:
    normalized = candidate.strip()
    if not normalized:
        return True
    return bool(_DEMOGRAPHIC_ONLY_RE.match(normalized))


def _split_inline_label(line: str) -> tuple[str, str] | None:
    normalized = _normalize_line(line)
    for separator in ("：", ":"):
        label, matched, body = normalized.partition(separator)
        if not matched:
            continue
        label = label.strip().lower()
        body = body.strip()
        if body and label and len(label) <= 30:
            return label, body
    return None


def _inline_section_item(line: str, keywords: tuple[str, ...]) -> str:
    parsed = _split_inline_label(line)
    if not parsed:
        return ""
    label, body = parsed
    if any(keyword.lower() in label for keyword in keywords):
        return _truncate(body)
    return ""


def _is_structured_inline_line(line: str) -> bool:
    parsed = _split_inline_label(line)
    if not parsed:
        return False
    label, _ = parsed
    return any(
        keyword in label
        for keyword in (
            "关键发现",
            "发现",
            "建议",
            "recommendation",
            "行动",
            "next step",
            "风险",
            "risk",
            "待确认",
            "open question",
            "问题",
        )
    )


def _append_unique(items: list[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def _estimate_summary_confidence(
    *,
    text: str,
    one_sentence: str,
    key_findings: list[str],
    recommendations: list[str],
    risks: list[str],
    evidence_refs: list[str],
    open_questions: list[str],
) -> float:
    """Estimate summary confidence from extracted structure density."""
    score = 0.2

    if one_sentence and one_sentence != "无摘要":
        score += 0.2
    score += min(len(key_findings), 3) * 0.1
    if recommendations:
        score += 0.15
    if risks:
        score += 0.15
    if evidence_refs:
        score += 0.15
    if open_questions:
        score += 0.05
    if len(text) >= 400:
        score += 0.05
    elif len(text) >= 160:
        score += 0.03

    return round(min(score, 0.95), 2)
