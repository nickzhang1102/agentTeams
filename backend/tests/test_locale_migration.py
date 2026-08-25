from migrations.versions import f3a4b5c6d7e8_add_locale_fields as migration


def test_locale_migration_adds_and_removes_expected_columns(monkeypatch):
    added_columns = []
    dropped_columns = []

    class RecordingSafeOperations:
        def __init__(self, operations):
            self.operations = operations

        def add_column(self, table_name, column):
            added_columns.append((table_name, column))

    monkeypatch.setattr(migration, 'SafeOperations', RecordingSafeOperations)
    monkeypatch.setattr(
        migration.op,
        'drop_column',
        lambda table_name, column_name: dropped_columns.append((table_name, column_name)),
    )

    migration.upgrade()

    assert [
        (table_name, column.name, column.nullable)
        for table_name, column in added_columns
    ] == [
        ('users', 'preferred_locale', False),
        ('conversations', 'default_locale', False),
        ('messages', 'content_locale', True),
        ('leader_sessions', 'locale', False),
        ('leader_agent_results', 'content_locale', False),
        ('leader_final_reports', 'content_locale', False),
    ]
    assert all(
        str(column.server_default.arg) == "'zh-CN'"
        for _, column in added_columns
        if not column.nullable
    )
    assert added_columns[2][1].server_default is None

    migration.downgrade()

    assert dropped_columns == [
        ('leader_final_reports', 'content_locale'),
        ('leader_agent_results', 'content_locale'),
        ('leader_sessions', 'locale'),
        ('messages', 'content_locale'),
        ('conversations', 'default_locale'),
        ('users', 'preferred_locale'),
    ]
