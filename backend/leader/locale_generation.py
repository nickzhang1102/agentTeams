"""Locale policy for Leader-generated user-visible content."""
from dataclasses import dataclass
import re
from typing import Literal, cast

from utils.locale_utils import (
    DEFAULT_LOCALE,
    SupportedLocale,
    is_supported_locale,
    normalize_locale,
)
from catalog.labels import CATALOG_TRANSLATIONS
from services.catalog_localization_service import catalog_localization_service


OutputContentKind = Literal[
    "assessment",
    "question",
    "agent_report",
    "final_report",
]

_CONTENT_KIND_LABELS = {
    "assessment": ("需求评估", "assessment"),
    "question": ("追问及选项", "follow-up questions and options"),
    "agent_report": ("Agent 分析与报告", "Agent analysis and report"),
    "final_report": ("最终综合报告", "final synthesis report"),
}

_MACHINE_CONTRACT_INSTRUCTION_ZH = (
    "Pydantic/JSON 字段名、枚举值、状态值、证据 ID、URL、代码和数值必须保持原有机器契约，"
    "不得翻译或改写。用户输入、原始证据和工具结果必须保持原文。"
)
_MACHINE_CONTRACT_INSTRUCTION_EN = (
    "Keep all Pydantic/JSON field names, enum values, status values, evidence IDs, URLs, code, "
    "and numeric values unchanged. Preserve user input, raw evidence, and tool results verbatim."
)

_CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_URL_RE = re.compile(r"https?://\S+")
_EVIDENCE_REF_RE = re.compile(r"\[evidence_id:[^\]\s]+\]")
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_ENGLISH_WORD_RE = re.compile(r"[A-Za-z0-9]+(?:['-][A-Za-z0-9]+)*")
_MIN_LANGUAGE_SIGNAL_CHARS = 20
_CONFIDENT_LANGUAGE_RATIO = 0.75


@dataclass(frozen=True)
class OutputLengthPolicy:
    """Locale-aware quality units for final report generation."""

    locale: SupportedLocale
    unit: Literal["effective_chars", "effective_words"]
    minimum_units: int
    maximum_units: int
    agent_increment: int
    evidence_increment: int
    input_divisor: int
    tokens_per_unit: float

    def count_units(self, text: str) -> int:
        if self.unit == "effective_words":
            return len(_ENGLISH_WORD_RE.findall(text or ""))
        return len(re.sub(r"\s+", "", text or ""))

    def target_units(
        self,
        *,
        agent_count: int,
        evidence_count: int,
        input_size: int,
    ) -> int:
        target = (
            self.minimum_units
            + max(0, agent_count - 1) * self.agent_increment
            + min(max(0, evidence_count), 16) * self.evidence_increment
            + min(max(0, input_size), 24000) // self.input_divisor
        )
        return min(self.maximum_units, max(self.minimum_units, target))

    def output_token_budget(self, target_units: int) -> int:
        return max(2048, int(target_units * self.tokens_per_unit) + 1024)


_OUTPUT_LENGTH_POLICIES: dict[SupportedLocale, OutputLengthPolicy] = {
    "zh-CN": OutputLengthPolicy(
        locale="zh-CN",
        unit="effective_chars",
        minimum_units=800,
        maximum_units=5000,
        agent_increment=500,
        evidence_increment=100,
        input_divisor=20,
        tokens_per_unit=1.0,
    ),
    "en-US": OutputLengthPolicy(
        locale="en-US",
        unit="effective_words",
        minimum_units=500,
        maximum_units=3000,
        agent_increment=300,
        evidence_increment=60,
        input_divisor=32,
        tokens_per_unit=1.5,
    ),
}


def resolve_generation_locale(
    explicit_locale: str | None = None,
    session_locale: str | None = None,
    conversation_locale: str | None = None,
    preferred_locale: str | None = None,
    accept_language: str | None = None,
) -> SupportedLocale:
    """Resolve a Leader generation locale using the roadmap precedence."""
    if explicit_locale is not None:
        if not is_supported_locale(explicit_locale):
            raise ValueError("UNSUPPORTED_LOCALE")
        return cast(SupportedLocale, explicit_locale)

    for candidate in (session_locale, conversation_locale, preferred_locale):
        if is_supported_locale(candidate):
            return cast(SupportedLocale, candidate)

    return normalize_locale(accept_language) or DEFAULT_LOCALE


def resolve_agent_display_name(
    agent_id: str,
    source_name: str | None = None,
    locale: SupportedLocale = DEFAULT_LOCALE,
    is_system: bool | None = None,
) -> str:
    """Resolve the stable catalog name used in user-visible Leader events."""
    if is_system is None:
        is_system = agent_id in CATALOG_TRANSLATIONS.get('agent', {})
    return catalog_localization_service.resolve_label(
        entity_type='agent',
        key=agent_id,
        source_name=source_name or agent_id,
        is_system=is_system,
        locale=locale,
    ).label


def build_output_locale_instruction(
    locale: SupportedLocale,
    content_kind: OutputContentKind,
) -> str:
    """Build the final system-prompt instruction for user-visible output."""
    if not is_supported_locale(locale):
        raise ValueError("UNSUPPORTED_LOCALE")
    if content_kind not in _CONTENT_KIND_LABELS:
        raise ValueError(f"UNSUPPORTED_CONTENT_KIND: {content_kind}")

    zh_label, en_label = _CONTENT_KIND_LABELS[content_kind]
    if locale == "en-US":
        return (
            f"\n\n## Output language (highest priority)\n"
            f"Write every user-visible value in this {en_label} in English (en-US). "
            "This instruction takes precedence over role prompts and workflow template additions. "
            f"{_MACHINE_CONTRACT_INSTRUCTION_EN}"
        )
    return (
        f"\n\n## 输出语言（最高优先级）\n"
        f"本次{zh_label}的所有用户可见文本必须使用简体中文（zh-CN）。"
        "本约束优先于角色提示和工作流模板附加提示。"
        f"{_MACHINE_CONTRACT_INSTRUCTION_ZH}"
    )


def get_output_length_policy(locale: SupportedLocale) -> OutputLengthPolicy:
    """Return the immutable report length policy for one supported locale."""
    try:
        return _OUTPUT_LENGTH_POLICIES[locale]
    except KeyError as exc:
        raise ValueError("UNSUPPORTED_LOCALE") from exc


def detect_content_locale(
    text: str,
    expected_locale: SupportedLocale,
) -> SupportedLocale:
    """Detect a clear opposite-language output, otherwise keep the expected locale."""
    if not is_supported_locale(expected_locale):
        raise ValueError("UNSUPPORTED_LOCALE")

    visible_text = _EVIDENCE_REF_RE.sub("", _URL_RE.sub("", _CODE_FENCE_RE.sub("", text or "")))
    cjk_chars = len(_CJK_RE.findall(visible_text))
    latin_chars = len(_LATIN_RE.findall(visible_text))
    signal_chars = cjk_chars + latin_chars
    if signal_chars < _MIN_LANGUAGE_SIGNAL_CHARS:
        return expected_locale

    cjk_ratio = cjk_chars / signal_chars
    latin_ratio = latin_chars / signal_chars
    if cjk_ratio >= _CONFIDENT_LANGUAGE_RATIO:
        return "zh-CN"
    if latin_ratio >= _CONFIDENT_LANGUAGE_RATIO:
        return "en-US"
    return expected_locale
