from types import SimpleNamespace
from unittest.mock import MagicMock

from models import LeaderAgentResult, LeaderFinalReport, Message
from translation.source import TranslationSourceRegistry


def _query_rows(rows):
    query = MagicMock()
    query.join.return_value = query
    query.filter.return_value = query
    query.all.return_value = rows
    return query


def test_source_registry_bulk_loads_each_type_and_resolves_owner():
    message = SimpleNamespace(
        id=1,
        conversation_id=10,
        role='assistant',
        message_type='normal',
        leader_session_id=None,
        content={'text': '消息'},
        content_locale='zh-CN',
    )
    agent_result = SimpleNamespace(
        id=2,
        conversation_id=10,
        content='Agent 报告',
        summary=None,
        structured_report=None,
        content_locale='zh-CN',
    )
    final_report = SimpleNamespace(
        id=3,
        conversation_id=10,
        report='最终报告',
        executive_summary=None,
        structured_report=None,
        content_locale='zh-CN',
    )
    queries = {
        Message: _query_rows([(message, 7)]),
        LeaderAgentResult: _query_rows([(agent_result, 7)]),
        LeaderFinalReport: _query_rows([(final_report, 7)]),
    }
    db_session = MagicMock()
    db_session.query.side_effect = lambda model, owner: queries[model]

    sources, errors = TranslationSourceRegistry.load_owned_many(
        db_session,
        [
            ('message', 1),
            ('message', 1),
            ('leader_agent_result', 2),
            ('leader_final_report', 3),
        ],
        user_id=7,
    )

    assert errors == {}
    assert list(sources) == [
        ('message', 1),
        ('leader_agent_result', 2),
        ('leader_final_report', 3),
    ]
    assert db_session.query.call_count == 3
    assert all(source.conversation_id == 10 for source in sources.values())


def test_source_registry_returns_stable_errors_without_source_payloads():
    foreign_message = SimpleNamespace(
        id=4,
        conversation_id=20,
        role='assistant',
        message_type='normal',
        leader_session_id=None,
        content={'text': '其他用户的正文'},
        content_locale='zh-CN',
    )
    user_message = SimpleNamespace(
        id=5,
        conversation_id=10,
        role='user',
        message_type='normal',
        leader_session_id=None,
        content={'text': '用户输入'},
        content_locale='zh-CN',
    )
    query = _query_rows([(foreign_message, 99), (user_message, 7)])
    db_session = MagicMock()
    db_session.query.return_value = query

    from translation import source as source_module

    normalized_ids = []
    original_normalize = source_module.normalize_translation_payload

    def record_normalized(source_type, entity):
        normalized_ids.append(entity.id)
        return original_normalize(source_type, entity)

    source_module.normalize_translation_payload = record_normalized
    try:
        sources, errors = TranslationSourceRegistry.load_owned_many(
            db_session,
            [('message', 4), ('message', 5), ('message', 404), ('unknown', 1)],
            user_id=7,
        )
    finally:
        source_module.normalize_translation_payload = original_normalize

    assert sources == {}
    assert errors == {
        ('unknown', 1): 'SOURCE_NOT_FOUND',
        ('message', 5): 'SOURCE_NOT_TRANSLATABLE',
        ('message', 404): 'SOURCE_NOT_FOUND',
        ('message', 4): 'FORBIDDEN',
    }
    assert normalized_ids == [5]
    assert '其他用户的正文' not in str(errors)
