import logging

from services.catalog_localization_service import CatalogLocalizationService


def test_system_label_changes_with_locale_but_key_does_not():
    service = CatalogLocalizationService()

    english = service.resolve_label(
        'agent', 'cardiology-expert', '心血管内科专家', True, 'en-US'
    )
    chinese = service.resolve_label(
        'agent', 'cardiology-expert', '心血管内科专家', True, 'zh-CN'
    )

    assert english.to_dict() == {
        'key': 'cardiology-expert',
        'label': 'Cardiology Specialist',
        'fallback_locale': 'zh-CN',
    }
    assert chinese.key == english.key
    assert chinese.label == '心血管内科专家'


def test_custom_label_always_preserves_source_name():
    service = CatalogLocalizationService()

    result = service.resolve_label(
        'agent', 'cardiology-expert', '我的自建 Agent', False, 'en-US', include_labels=True
    )

    assert result.to_dict() == {
        'key': 'cardiology-expert',
        'label': '我的自建 Agent',
        'fallback_locale': 'zh-CN',
    }


def test_missing_system_translation_falls_back_and_logs(caplog):
    service = CatalogLocalizationService()

    with caplog.at_level(logging.WARNING):
        result = service.resolve_label(
            'agent', 'new-system-agent', '新系统 Agent', True, 'en-US'
        )

    assert result.label == '新系统 Agent'
    assert 'catalog_label_missing entity_type=agent key=new-system-agent locale=en-US' in caplog.text


def test_admin_labels_return_complete_effective_map():
    service = CatalogLocalizationService()

    result = service.resolve_label(
        'agent_category', 'medical', '医疗专家', True, 'en-US', include_labels=True
    )

    assert result.to_dict()['labels'] == {
        'zh-CN': '医疗专家',
        'en-US': 'Medical Specialists',
    }


def test_missing_admin_translation_uses_fallback_for_both_locales():
    service = CatalogLocalizationService()

    result = service.resolve_label(
        'agent_pack', 'unknown-pack', '未知团队', True, 'en-US', include_labels=True
    )

    assert result.label == '未知团队'
    assert result.labels == {'zh-CN': '未知团队', 'en-US': '未知团队'}


def test_system_knowledge_category_uses_code_resource_but_custom_stays_source():
    service = CatalogLocalizationService()

    system = service.resolve_label(
        'knowledge_category', 'regulation', '制度', True, 'en-US'
    )
    custom = service.resolve_label(
        'knowledge_category', 'my_policy', '我的政策', False, 'en-US'
    )

    assert system.to_dict() == {
        'key': 'regulation',
        'label': 'Policies',
        'fallback_locale': 'zh-CN',
    }
    assert custom.to_dict() == {
        'key': 'my_policy',
        'label': '我的政策',
        'fallback_locale': 'zh-CN',
    }
