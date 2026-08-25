from collections.abc import Iterable
from typing import Any

import sqlalchemy as sa
from alembic.operations import Operations


class SafeOperations:
    """Alembic 操作包装器：目标已存在时跳过。"""

    def __init__(self, operations: Operations):
        self._operations = operations

    @property
    def _connection(self) -> sa.Connection:
        return self._operations.get_bind()

    @property
    def _inspector(self) -> sa.Inspector:
        return sa.inspect(self._connection)

    def has_table(self, table_name: str) -> bool:
        return self._inspector.has_table(table_name)

    def has_column(self, table_name: str, column_name: str) -> bool:
        if not self.has_table(table_name):
            return False
        return any(
            column['name'] == column_name
            for column in self._inspector.get_columns(table_name)
        )

    def has_index(self, table_name: str, index_name: str) -> bool:
        if not self.has_table(table_name):
            return False
        return any(
            index['name'] == index_name
            for index in self._inspector.get_indexes(table_name)
        )

    def has_constraint(self, table_name: str, constraint_name: str) -> bool:
        if not constraint_name:
            return False
        if not self.has_table(table_name):
            return False

        inspector = self._inspector
        constraint_groups: Iterable[list[dict[str, Any]]] = (
            inspector.get_unique_constraints(table_name),
            inspector.get_foreign_keys(table_name),
        )
        return any(
            constraint.get('name') == constraint_name
            for constraints in constraint_groups
            for constraint in constraints
        )

    def find_constraint(
        self,
        table_name: str,
        *,
        constraint_name: str | None = None,
        constraint_type: str | None = None,
        local_cols: list[str] | None = None,
        referent_table: str | None = None,
        remote_cols: list[str] | None = None,
    ) -> str | None:
        """Return a matching constraint name, including anonymous constraints.

        PostgreSQL normally reports a generated name for an unnamed foreign key,
        while SQLite may report ``None``.  Matching by columns/referenced table
        lets migrations avoid creating duplicate constraints without depending on
        the name chosen by the database.  An anonymous match is returned as an
        empty string, reserving ``None`` for "not found".
        """
        if not self.has_table(table_name):
            return None
        if not constraint_name and local_cols is None:
            return None

        inspector = self._inspector
        groups: list[tuple[str, list[dict[str, Any]]]] = []
        if constraint_type in (None, 'unique'):
            groups.append(('unique', inspector.get_unique_constraints(table_name)))
        if constraint_type in (None, 'foreignkey'):
            groups.append(('foreignkey', inspector.get_foreign_keys(table_name)))

        wanted_local = list(local_cols) if local_cols is not None else None
        wanted_remote = list(remote_cols) if remote_cols is not None else None
        for kind, constraints in groups:
            for constraint in constraints:
                if constraint_name and constraint.get('name') == constraint_name:
                    return constraint.get('name') or ''
                if kind == 'unique':
                    if wanted_local is not None and list(constraint.get('column_names') or []) == wanted_local:
                        return constraint.get('name') or ''
                    continue
                if wanted_local is not None and list(constraint.get('constrained_columns') or []) != wanted_local:
                    continue
                if referent_table and constraint.get('referred_table') != referent_table:
                    continue
                if wanted_remote is not None and list(constraint.get('referred_columns') or []) != wanted_remote:
                    continue
                return constraint.get('name') or ''
        return None

    def create_table(self, table_name: str, *columns: sa.Column, **kwargs: Any) -> None:
        if not self.has_table(table_name):
            self._operations.create_table(table_name, *columns, **kwargs)

    def add_column(self, table_name: str, column: sa.Column) -> None:
        if not self.has_column(table_name, column.name):
            self._operations.add_column(table_name, column)

    def create_index(
        self,
        index_name: str,
        table_name: str,
        columns: list[str],
        **kwargs: Any,
    ) -> None:
        if not self.has_index(table_name, index_name):
            self._operations.create_index(index_name, table_name, columns, **kwargs)

    def create_unique_constraint(
        self,
        constraint_name: str,
        table_name: str,
        columns: list[str],
        **kwargs: Any,
    ) -> None:
        if self.find_constraint(
            table_name,
            constraint_name=constraint_name,
            constraint_type='unique',
            local_cols=columns,
        ) is None:
            self._operations.create_unique_constraint(constraint_name, table_name, columns, **kwargs)

    def create_foreign_key(
        self,
        constraint_name: str | None,
        source_table: str,
        referent_table: str,
        local_cols: list[str],
        remote_cols: list[str],
        **kwargs: Any,
    ) -> None:
        existing = self.find_constraint(
            source_table,
            constraint_name=constraint_name,
            constraint_type='foreignkey',
            local_cols=local_cols,
            referent_table=referent_table,
            remote_cols=remote_cols,
        )
        if existing is None:
            self._operations.create_foreign_key(
                constraint_name,
                source_table,
                referent_table,
                local_cols,
                remote_cols,
                **kwargs,
            )

    def drop_constraint_if_exists(
        self,
        table_name: str,
        constraint_name: str | None = None,
        *,
        type_: str | None = None,
        local_cols: list[str] | None = None,
        referent_table: str | None = None,
        remote_cols: list[str] | None = None,
    ) -> None:
        """Drop a named or structurally matching constraint when present."""
        existing = self.find_constraint(
            table_name,
            constraint_name=constraint_name,
            constraint_type=type_,
            local_cols=local_cols,
            referent_table=referent_table,
            remote_cols=remote_cols,
        )
        if existing:
            self._operations.drop_constraint(existing, table_name, type_=type_)

    def drop_index_if_exists(
        self,
        index_name: str,
        table_name: str,
        *,
        columns: list[str] | None = None,
    ) -> None:
        """Drop an index by name, falling back to column structure.

        名字精确匹配优先；仅当该名字不存在时，``columns`` 才作为
        create_all/历史版本造成的索引命名漂移兜底。若同列组合存在多个
        索引用途不明，跳过删除并由迁移作者显式指定真实名字。
        """
        if not self.has_table(table_name):
            return
        indexes = self._inspector.get_indexes(table_name)
        existing = next(
            (index for index in indexes if index.get('name') == index_name),
            None,
        )
        if existing is None and columns is not None:
            wanted = list(columns)
            same_columns = [
                index for index in indexes
                if list(index.get('column_names') or []) == wanted
            ]
            if len(same_columns) == 1:
                existing = same_columns[0]
        if existing and existing.get('name'):
            self._operations.drop_index(existing['name'], table_name=table_name)

    def drop_column_if_exists(self, table_name: str, column_name: str) -> None:
        if self.has_column(table_name, column_name):
            self._operations.drop_column(table_name, column_name)

    def drop_table_if_exists(self, table_name: str) -> None:
        if self.has_table(table_name):
            self._operations.drop_table(table_name)
