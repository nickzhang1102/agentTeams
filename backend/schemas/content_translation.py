"""Request and response contracts for historical content translation."""
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


TranslationSourceType = Literal[
    'message',
    'leader_agent_result',
    'leader_final_report',
]
TranslationStatus = Literal['pending', 'ready', 'failed']
TranslationLocale = Literal['zh-CN', 'en-US']

UNSUPPORTED_LOCALE = 'UNSUPPORTED_LOCALE'
EMPTY_SOURCES = 'EMPTY_SOURCES'
TOO_MANY_SOURCES = 'TOO_MANY_SOURCES'
RATE_LIMITED = 'RATE_LIMITED'
SOURCE_NOT_FOUND = 'SOURCE_NOT_FOUND'
FORBIDDEN = 'FORBIDDEN'
SOURCE_NOT_TRANSLATABLE = 'SOURCE_NOT_TRANSLATABLE'
TRANSLATION_FAILED = 'TRANSLATION_FAILED'
TRANSLATION_NOT_FOUND = 'TRANSLATION_NOT_FOUND'
STALE_SOURCE = 'STALE_SOURCE'


class TranslationSourceRef(BaseModel):
    type: str
    id: int


class ResolveTranslationsRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    target_locale: Any = None
    sources: Any = None


class TranslationItemResponse(BaseModel):
    source: TranslationSourceRef
    translation_id: Optional[int] = None
    status: TranslationStatus
    source_hash: Optional[str] = None
    source_locale: Optional[TranslationLocale] = None
    target_locale: TranslationLocale
    payload: Optional[dict[str, Any]] = None
    error_code: Optional[str] = None


class TranslationResponse(BaseModel):
    translation_id: int
    status: TranslationStatus
    source_hash: str
    source_locale: TranslationLocale
    target_locale: TranslationLocale
    payload: Optional[dict[str, Any]] = None
    error_code: Optional[str] = None


class ResolveTranslationsResponse(BaseModel):
    items: list[TranslationItemResponse]


class TranslationLookupResponse(BaseModel):
    items: list[TranslationItemResponse]
    missing_sources: list[TranslationSourceRef] = Field(default_factory=list)
