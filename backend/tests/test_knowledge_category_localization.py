from types import SimpleNamespace
from datetime import datetime, UTC

import pytest
from fastapi import HTTPException

from api.deps import resolve_request_locale
from api.knowledge_api import _localize_knowledge_category
from models import KnowledgeCategory


def test_knowledge_category_localization_keeps_source_name_and_resolves_label():
    now = datetime(2026, 8, 1, tzinfo=UTC)
    system = KnowledgeCategory(
        key='regulation',
        label='制度',
        user_id=None,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    personal = KnowledgeCategory(
        key='my_policy',
        label='我的政策',
        user_id=12,
        is_active=True,
        created_at=now,
        updated_at=now,
    )

    localized_system = _localize_knowledge_category(system, 'en-US', include_count=3)
    localized_personal = _localize_knowledge_category(personal, 'en-US')

    assert localized_system['key'] == 'regulation'
    assert localized_system['name'] == '制度'
    assert localized_system['label'] == 'Policies'
    assert localized_system['fallback_locale'] == 'zh-CN'
    assert localized_system['count'] == 3
    assert localized_personal['key'] == 'my_policy'
    assert localized_personal['name'] == '我的政策'
    assert localized_personal['label'] == '我的政策'


def test_knowledge_category_locale_rejects_unsupported_explicit_value():
    request = SimpleNamespace(headers={})
    user = SimpleNamespace(preferred_locale='zh-CN')

    with pytest.raises(HTTPException) as exc_info:
        resolve_request_locale(request, 'fr-FR', user)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail['code'] == 'UNSUPPORTED_LOCALE'
