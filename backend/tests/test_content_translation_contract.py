from sqlalchemy import CheckConstraint, UniqueConstraint

from models import ContentTranslation
from schemas.content_translation import (
    ResolveTranslationsRequest,
    TranslationItemResponse,
    TranslationLookupResponse,
)


def test_content_translation_metadata_matches_persistence_contract():
    table = ContentTranslation.__table__

    assert table.c.id.type.__class__.__name__ == 'BigInteger'
    assert table.c.source_id.type.__class__.__name__ == 'BigInteger'
    assert table.c.translated_payload.nullable is True
    assert table.c.status.default.arg == 'pending'
    assert table.c.attempt_count.default.arg == 0

    foreign_keys = {
        (foreign_key.parent.name, foreign_key.target_fullname): foreign_key.ondelete
        for foreign_key in table.foreign_keys
    }
    assert foreign_keys == {
        ('user_id', 'users.id'): 'CASCADE',
        ('conversation_id', 'conversations.id'): 'CASCADE',
    }

    unique_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert (
        'source_type',
        'source_id',
        'target_locale',
        'source_hash',
    ) in unique_columns

    check_sql = {
        str(constraint.sqltext)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert any('leader_final_report' in sql for sql in check_sql)
    assert any("status IN ('pending', 'ready', 'failed')" in sql for sql in check_sql)
    assert sum("'zh-CN', 'en-US'" in sql for sql in check_sql) == 2


def test_content_translation_request_keeps_business_validation_in_api_layer():
    request = ResolveTranslationsRequest(
        target_locale='fr-FR',
        sources=[{'type': 'future_source', 'id': 0}] * 21,
    )

    assert request.target_locale == 'fr-FR'
    assert len(request.sources) == 21


def test_translation_response_contract_supports_pending_and_share_misses():
    item = TranslationItemResponse(
        source={'type': 'message', 'id': 101},
        translation_id=301,
        status='pending',
        source_hash='a' * 64,
        source_locale='zh-CN',
        target_locale='en-US',
    )
    lookup = TranslationLookupResponse(items=[], missing_sources=[item.source])

    assert item.payload is None
    assert item.error_code is None
    assert lookup.missing_sources[0].id == 101
