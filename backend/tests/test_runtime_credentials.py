import pytest
from sqlalchemy import text

from models import LLMModel, SystemConfig
from services.llm_service import (
    LLMConfigurationError,
    resolve_model_info,
)
from utils.credential_encryption import (
    CredentialDecryptionError,
    decrypt_value,
    encrypt_value,
    is_encrypted_value,
)


def test_env_cleanup_removes_only_managed_runtime_keys(tmp_path):
    from scripts.migrate_env_runtime_credentials import _remove_legacy_env_lines

    env_path = tmp_path / '.env'
    env_path.write_text(
        '# runtime\n'
        'LLM_API_KEY=llm-secret\n'
        'export EXA_API_KEY=exa-secret\n'
        'DATABASE_URL=postgresql://keep-this\n'
        'EMBEDDING_API_KEY=embedding-secret\n',
        encoding='utf-8',
    )

    removed = _remove_legacy_env_lines(env_path)
    result = env_path.read_text(encoding='utf-8')

    assert removed == ['EXA_API_KEY', 'LLM_API_KEY']
    assert 'LLM_API_KEY' not in result
    assert 'EXA_API_KEY' not in result
    assert 'DATABASE_URL=postgresql://keep-this' in result
    assert 'EMBEDDING_API_KEY=embedding-secret' in result


def test_encryption_round_trip_and_tamper_failure():
    ciphertext = encrypt_value('super-secret-key')

    assert is_encrypted_value(ciphertext)
    assert 'super-secret-key' not in ciphertext
    assert decrypt_value(ciphertext) == 'super-secret-key'
    with pytest.raises(CredentialDecryptionError):
        decrypt_value(ciphertext[:-1] + ('A' if ciphertext[-1] != 'A' else 'B'))


def test_database_columns_store_ciphertext_but_orm_returns_plaintext(db_session):
    setting = SystemConfig(key='EXA_API_KEY', value='exa-secret', description='Exa')
    model = LLMModel(
        model_id='db-model',
        display_name='DB Model',
        base_url='https://llm.test/v1',
        api_key='llm-secret',
        is_enabled=True,
        is_default=True,
    )
    db_session.add_all([setting, model])
    db_session.commit()

    raw_setting = db_session.execute(text(
        "SELECT value FROM system_configs WHERE key = 'EXA_API_KEY'"
    )).scalar_one()
    raw_model_key = db_session.execute(text(
        "SELECT api_key FROM llm_models WHERE model_id = 'db-model'"
    )).scalar_one()

    assert is_encrypted_value(raw_setting)
    assert is_encrypted_value(raw_model_key)
    assert 'exa-secret' not in raw_setting
    assert 'llm-secret' not in raw_model_key
    db_session.expire_all()
    assert db_session.query(SystemConfig).filter_by(key='EXA_API_KEY').one().value == 'exa-secret'
    assert db_session.query(LLMModel).filter_by(model_id='db-model').one().api_key == 'llm-secret'


def test_system_config_masks_secret_values():
    setting = SystemConfig(key='TAVILY_API_KEY', value='tavily-secret', description='Tavily')

    payload = setting.to_dict()

    assert payload['value'] == '********'
    assert payload['is_secret'] is True
    assert payload['is_configured'] is True
    assert 'tavily-secret' not in repr(setting)


def test_model_resolution_uses_database_default_and_never_environment(db_session, monkeypatch):
    monkeypatch.setenv('LLM_API_KEY', 'environment-key-must-not-be-used')
    model = LLMModel(
        model_id='default-db-model',
        display_name='Default DB Model',
        base_url='https://llm.test/v1',
        api_key='database-key',
        is_enabled=True,
        is_default=True,
    )
    db_session.add(model)
    db_session.commit()

    resolved = resolve_model_info(db_session=db_session)

    assert resolved['model_id'] == 'default-db-model'
    assert resolved['api_key'] == 'database-key'


def test_model_resolution_fails_when_database_has_no_enabled_model(db_session, monkeypatch):
    monkeypatch.setenv('LLM_API_KEY', 'environment-key-must-not-be-used')

    with pytest.raises(LLMConfigurationError, match='admin database'):
        resolve_model_info(db_session=db_session)


def test_explicit_disabled_model_cannot_be_used(db_session):
    db_session.add(LLMModel(
        model_id='disabled-model',
        display_name='Disabled Model',
        base_url='https://llm.test/v1',
        api_key='database-key',
        is_enabled=False,
        is_default=False,
    ))
    db_session.commit()

    with pytest.raises(LLMConfigurationError, match='admin database'):
        resolve_model_info('disabled-model', db_session=db_session)
