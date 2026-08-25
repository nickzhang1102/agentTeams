import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from migrations.safe_ops import SafeOperations


def make_operations(connection: sa.Connection) -> Operations:
    context = MigrationContext.configure(connection)
    return Operations(context)


def test_safe_operations_skip_existing_table_column_and_index() -> None:
    engine = sa.create_engine('sqlite:///:memory:')

    with engine.begin() as connection:
        operations = make_operations(connection)
        safe_op = SafeOperations(operations)

        safe_op.create_table(
            'users',
            sa.Column('id', sa.Integer(), primary_key=True),
        )
        safe_op.create_table(
            'users',
            sa.Column('id', sa.Integer(), primary_key=True),
        )

        safe_op.add_column('users', sa.Column('username', sa.String(50)))
        safe_op.add_column('users', sa.Column('username', sa.String(50)))

        safe_op.create_index('ix_users_username', 'users', ['username'])
        safe_op.create_index('ix_users_username', 'users', ['username'])

        inspector = sa.inspect(connection)
        assert inspector.has_table('users')
        assert [column['name'] for column in inspector.get_columns('users')] == ['id', 'username']
        assert [index['name'] for index in inspector.get_indexes('users')] == ['ix_users_username']
