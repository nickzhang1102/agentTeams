"""Resolve product-owned catalog labels without runtime translation."""
import logging
from dataclasses import dataclass
from typing import Literal

from catalog.labels import CATALOG_TRANSLATIONS
from utils.locale_utils import DEFAULT_LOCALE, SUPPORTED_LOCALES, SupportedLocale


logger = logging.getLogger(__name__)

CatalogEntityType = Literal[
    'agent',
    'agent_category',
    'agent_pack',
    'workflow_template',
    'knowledge_category',
]


@dataclass(frozen=True)
class LocalizedLabel:
    key: str
    label: str
    fallback_locale: SupportedLocale = DEFAULT_LOCALE
    labels: dict[str, str] | None = None

    def to_dict(self) -> dict:
        result = {
            'key': self.key,
            'label': self.label,
            'fallback_locale': self.fallback_locale,
        }
        if self.labels is not None:
            result['labels'] = self.labels
        return result


class CatalogLocalizationService:
    """Resolve display labels from stable catalog identity and request locale."""

    def resolve_label(
        self,
        entity_type: CatalogEntityType,
        key: str,
        source_name: str | None,
        is_system: bool,
        locale: SupportedLocale,
        include_labels: bool = False,
    ) -> LocalizedLabel:
        source_label = source_name or key
        if not is_system:
            return LocalizedLabel(key=key, label=source_label)

        translations = CATALOG_TRANSLATIONS.get(entity_type, {}).get(key, {})
        effective_labels = {DEFAULT_LOCALE: source_label, **translations}
        label = effective_labels.get(locale)
        if label is None:
            logger.warning(
                'catalog_label_missing entity_type=%s key=%s locale=%s',
                entity_type,
                key,
                locale,
            )
            label = effective_labels.get(DEFAULT_LOCALE, source_label)

        labels = None
        if include_labels:
            fallback_label = effective_labels.get(DEFAULT_LOCALE, source_label)
            labels = {
                supported_locale: effective_labels.get(supported_locale, fallback_label)
                for supported_locale in SUPPORTED_LOCALES
            }

        return LocalizedLabel(
            key=key,
            label=label,
            fallback_locale=DEFAULT_LOCALE,
            labels=labels,
        )

    def localize_item(
        self,
        data: dict,
        entity_type: CatalogEntityType,
        key: str,
        source_name: str | None,
        is_system: bool,
        locale: SupportedLocale,
        include_labels: bool = False,
    ) -> dict:
        """Return a compatibility-preserving response with resolved label fields."""
        result = dict(data)
        result.update(self.resolve_label(
            entity_type=entity_type,
            key=key,
            source_name=source_name,
            is_system=is_system,
            locale=locale,
            include_labels=include_labels,
        ).to_dict())
        return result

    def matching_keys(
        self,
        entity_type: CatalogEntityType,
        locale: SupportedLocale,
        search: str,
    ) -> set[str]:
        """Map a visible-label search back to stable system catalog keys."""
        needle = search.strip().casefold()
        if not needle:
            return set()
        return {
            key
            for key, translations in CATALOG_TRANSLATIONS.get(entity_type, {}).items()
            if needle in translations.get(locale, '').casefold()
        }


catalog_localization_service = CatalogLocalizationService()
