"""encrypt database-backed runtime credentials

Revision ID: f4b5c6d7e8a9
Revises: e9f0a1b2c3d4
Create Date: 2026-08-12
"""

from alembic import op
import sqlalchemy as sa

from utils.credential_encryption import decrypt_value, encrypt_value, is_encrypted_value


revision = 'f4b5c6d7e8a9'
down_revision = 'e9f0a1b2c3d4'
branch_labels = None
depends_on = None


def _rewrite_column(table: str, column: str, transform) -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text(f'SELECT id, {column} FROM {table}')).mappings().all()
    statement = sa.text(f'UPDATE {table} SET {column} = :value WHERE id = :id')
    for row in rows:
        value = row[column]
        rewritten = transform(value)
        if rewritten != value:
            bind.execute(statement, {'id': row['id'], 'value': rewritten})


def upgrade():
    op.alter_column(
        'llm_models',
        'api_key',
        existing_type=sa.String(length=500),
        type_=sa.Text(),
        existing_nullable=False,
    )

    _rewrite_column('llm_models', 'api_key', encrypt_value)
    _rewrite_column('system_configs', 'value', encrypt_value)

    bind = op.get_bind()
    existing = {
        row[0]
        for row in bind.execute(sa.text(
            "SELECT key FROM system_configs WHERE key IN ('EXA_API_KEY', 'TAVILY_API_KEY')"
        ))
    }
    settings = {
        'EXA_API_KEY': 'Exa Web Search API Key',
        'TAVILY_API_KEY': 'Tavily Web Search API Key',
    }
    insert = sa.text(
        'INSERT INTO system_configs (key, value, description, created_at, updated_at) '
        'VALUES (:key, :value, :description, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)'
    )
    for key, description in settings.items():
        if key not in existing:
            bind.execute(insert, {
                'key': key,
                'value': encrypt_value(''),
                'description': description,
            })


def downgrade():
    # Keep search settings during downgrade: they may predate this revision or
    # contain user data. Older application versions can safely ignore the rows.
    _rewrite_column(
        'llm_models',
        'api_key',
        lambda value: decrypt_value(value) if is_encrypted_value(value) else value,
    )
    _rewrite_column(
        'system_configs',
        'value',
        lambda value: decrypt_value(value) if is_encrypted_value(value) else value,
    )
    op.alter_column(
        'llm_models',
        'api_key',
        existing_type=sa.Text(),
        type_=sa.String(length=500),
        existing_nullable=False,
    )
