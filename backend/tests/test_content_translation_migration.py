from migrations.versions import b6c7d8e9f0a1_add_content_translations as migration


def test_content_translation_migration_upgrade_and_downgrade(monkeypatch):
    created_tables = []
    created_indexes = []
    dropped_tables = []

    class _RecordingSafeOperations:
        """记录 SafeOperations 调用的桩，避免依赖真实迁移上下文"""

        def __init__(self, operations):
            pass

        def create_table(self, name, *elements):
            created_tables.append((name, elements))

        def create_index(self, name, table, columns, **kwargs):
            created_indexes.append((name, table, tuple(columns), kwargs.get('unique', False)))

        def drop_table(self, name):
            dropped_tables.append(name)

    monkeypatch.setattr(migration, 'SafeOperations', _RecordingSafeOperations)
    # downgrade 仍直接使用 op.drop_table
    monkeypatch.setattr(
        migration.op,
        'drop_table',
        lambda name: dropped_tables.append(name),
    )

    migration.upgrade()

    assert migration.down_revision == 'a4b5c6d7e8f9'
    assert len(created_tables) == 1
    table_name, elements = created_tables[0]
    assert table_name == 'content_translations'

    columns = {
        element.name: element
        for element in elements
        if element.__class__.__name__ == 'Column'
    }
    assert columns['id'].type.__class__.__name__ == 'BigInteger'
    assert columns['translated_payload'].nullable is True
    assert str(columns['status'].server_default.arg) == 'pending'

    foreign_keys = [
        element
        for element in elements
        if element.__class__.__name__ == 'ForeignKeyConstraint'
    ]
    assert len(foreign_keys) == 2
    assert all(constraint.ondelete == 'CASCADE' for constraint in foreign_keys)

    assert created_indexes == [
        (
            'ix_content_translations_user_id',
            'content_translations',
            ('user_id',),
            False,
        ),
        (
            'ix_content_translations_conversation_id',
            'content_translations',
            ('conversation_id',),
            False,
        ),
        (
            'idx_content_translation_source',
            'content_translations',
            ('source_type', 'source_id'),
            False,
        ),
        (
            'idx_content_translation_recovery',
            'content_translations',
            ('status', 'lease_expires_at'),
            False,
        ),
    ]

    migration.downgrade()
    assert dropped_tables == ['content_translations']
