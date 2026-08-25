"""Canonical locale definitions shared by HTTP APIs and later workflows."""
from typing import Final, Literal, cast


SupportedLocale = Literal['zh-CN', 'en-US']

DEFAULT_LOCALE: Final[SupportedLocale] = 'zh-CN'
SUPPORTED_LOCALES: Final[tuple[SupportedLocale, ...]] = ('zh-CN', 'en-US')
LOCALE_CATALOG: Final[tuple[dict[str, str], ...]] = (
    {'code': 'zh-CN', 'native_name': '中文'},
    {'code': 'en-US', 'native_name': 'English'},
)


def is_supported_locale(value: str | None) -> bool:
    """Return whether a product-level locale is an exact canonical value."""
    return value in SUPPORTED_LOCALES


def normalize_locale(value: str | None) -> SupportedLocale | None:
    """Map browser language ranges to a supported locale without accepting them as explicit API values."""
    if not value:
        return None

    language = value.strip().lower().split(',', 1)[0].split(';', 1)[0]
    if language == 'zh-cn' or language.startswith('zh-') or language == 'zh':
        return 'zh-CN'
    if language == 'en-us' or language.startswith('en-') or language == 'en':
        return 'en-US'
    return None


def resolve_locale(
    explicit_locale: str | None,
    preferred_locale: str | None = None,
    accept_language: str | None = None,
) -> SupportedLocale:
    """Resolve one request locale using the product-level precedence contract."""
    if explicit_locale is not None:
        if not is_supported_locale(explicit_locale):
            raise ValueError('UNSUPPORTED_LOCALE')
        return cast(SupportedLocale, explicit_locale)

    if is_supported_locale(preferred_locale):
        return cast(SupportedLocale, preferred_locale)

    return normalize_locale(accept_language) or DEFAULT_LOCALE
