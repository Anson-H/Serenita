from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from enum import IntEnum
from functools import lru_cache
from pathlib import Path

from backend.app.storage.sqlite import UnsupportedSchemaError


_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")
_DATABASE_FILENAME = re.compile(r"^[a-z][a-z0-9_]*\.db$")
_FOREIGN_KEY_ACTIONS = {
    "NO ACTION",
    "RESTRICT",
    "SET NULL",
    "SET DEFAULT",
    "CASCADE",
}


class ColumnGroup(IntEnum):
    """Canonical physical order for columns inside every Serenita table."""

    PRIMARY_KEY = 1
    SCOPE = 2
    REFERENCE = 3
    DATA = 4
    STATE = 5
    AUDIT = 6


@dataclass(frozen=True)
class Column:
    name: str
    storage_type: str
    group: ColumnGroup
    nullable: bool = True
    default: str | None = None
    collation: str | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.name, "column")
        if not self.storage_type or not re.fullmatch(r"[A-Z]+", self.storage_type):
            raise ValueError(f"invalid SQLite storage type for {self.name}")
        if self.collation is not None and not re.fullmatch(
            r"[A-Z][A-Z0-9_]*", self.collation
        ):
            raise ValueError(f"invalid SQLite collation for {self.name}")

    def sql(self) -> str:
        parts = [self.name, self.storage_type]
        if self.collation:
            parts.extend(("COLLATE", self.collation))
        if not self.nullable:
            parts.extend(("NOT", "NULL"))
        if self.default is not None:
            parts.extend(("DEFAULT", self.default))
        return " ".join(parts)


@dataclass(frozen=True)
class ForeignKey:
    columns: tuple[str, ...]
    target_table: str
    target_columns: tuple[str, ...]
    on_update: str = "NO ACTION"
    on_delete: str = "NO ACTION"

    def __post_init__(self) -> None:
        _require_identifier(self.target_table, "foreign-key target table")
        _require_nonempty_columns(self.columns, "foreign key")
        _require_nonempty_columns(self.target_columns, "foreign-key target")
        if len(self.columns) != len(self.target_columns):
            raise ValueError("foreign key has mismatched column counts")
        if self.on_update not in _FOREIGN_KEY_ACTIONS:
            raise ValueError("foreign key has invalid ON UPDATE action")
        if self.on_delete not in _FOREIGN_KEY_ACTIONS:
            raise ValueError("foreign key has invalid ON DELETE action")

    def sql(self) -> str:
        return (
            f"FOREIGN KEY ({', '.join(self.columns)}) "
            f"REFERENCES {self.target_table} ({', '.join(self.target_columns)}) "
            f"ON UPDATE {self.on_update} ON DELETE {self.on_delete}"
        )


@dataclass(frozen=True)
class UniqueConstraint:
    columns: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_nonempty_columns(self.columns, "unique constraint")

    def sql(self) -> str:
        return f"UNIQUE ({', '.join(self.columns)})"


@dataclass(frozen=True)
class CheckConstraint:
    expression: str

    def __post_init__(self) -> None:
        if not self.expression.strip():
            raise ValueError("check constraint has an empty expression")

    def sql(self) -> str:
        return f"CHECK ({self.expression.strip()})"


@dataclass(frozen=True)
class Index:
    name: str
    columns: tuple[str, ...]
    unique: bool = False
    where: str | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.name, "index")
        _require_nonempty_columns(self.columns, "index")
        if self.where is not None and not self.where.strip():
            raise ValueError(f"index {self.name} has an empty WHERE expression")

    def sql(self, table_name: str) -> str:
        unique = "UNIQUE " if self.unique else ""
        statement = (
            f"CREATE {unique}INDEX IF NOT EXISTS {self.name} "
            f"ON {table_name} ({', '.join(self.columns)})"
        )
        if self.where:
            statement += f" WHERE {self.where.strip()}"
        return statement


@dataclass(frozen=True)
class Table:
    name: str
    columns: tuple[Column, ...]
    primary_key: tuple[str, ...]
    foreign_keys: tuple[ForeignKey, ...] = ()
    unique_constraints: tuple[UniqueConstraint, ...] = ()
    checks: tuple[CheckConstraint, ...] = ()
    indexes: tuple[Index, ...] = ()

    def __post_init__(self) -> None:
        _require_identifier(self.name, "table")
        if not self.columns:
            raise ValueError(f"table {self.name} has no columns")
        column_names = tuple(column.name for column in self.columns)
        if len(column_names) != len(set(column_names)):
            raise ValueError(f"table {self.name} has duplicate columns")
        groups = tuple(column.group for column in self.columns)
        if groups != tuple(sorted(groups)):
            raise ValueError(f"table {self.name} does not follow canonical column order")
        _require_nonempty_columns(self.primary_key, "primary key")
        self._require_known_columns(self.primary_key, "primary key")
        primary_columns = tuple(
            column.name
            for column in self.columns
            if column.group == ColumnGroup.PRIMARY_KEY
        )
        if primary_columns != self.primary_key:
            raise ValueError(
                f"table {self.name} primary-key columns must be the first column group"
            )
        for foreign_key in self.foreign_keys:
            self._require_known_columns(foreign_key.columns, "foreign key")
        for unique_constraint in self.unique_constraints:
            self._require_known_columns(
                unique_constraint.columns,
                "unique constraint",
            )
        for index in self.indexes:
            self._require_known_columns(index.columns, f"index {index.name}")
        if "created_at" in column_names and "updated_at" in column_names:
            if column_names.index("created_at") > column_names.index("updated_at"):
                raise ValueError(
                    f"table {self.name} must place created_at before updated_at"
                )

    @property
    def column_names(self) -> tuple[str, ...]:
        return tuple(column.name for column in self.columns)

    def _require_known_columns(self, names: tuple[str, ...], label: str) -> None:
        unknown = set(names) - set(self.column_names)
        if unknown:
            raise ValueError(
                f"table {self.name} {label} uses unknown columns: "
                f"{', '.join(sorted(unknown))}"
            )

    def create_table_sql(self) -> str:
        clauses = [column.sql() for column in self.columns]
        clauses.append(f"PRIMARY KEY ({', '.join(self.primary_key)})")
        clauses.extend(foreign_key.sql() for foreign_key in self.foreign_keys)
        clauses.extend(constraint.sql() for constraint in self.unique_constraints)
        clauses.extend(check.sql() for check in self.checks)
        body = ",\n    ".join(clauses)
        return f"CREATE TABLE IF NOT EXISTS {self.name} (\n    {body}\n)"

    def create_index_sql(self) -> tuple[str, ...]:
        return tuple(index.sql(self.name) for index in self.indexes)


@dataclass(frozen=True)
class Database:
    name: str
    tables: tuple[Table, ...]
    _table_by_name: dict[str, Table] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not _DATABASE_FILENAME.fullmatch(self.name):
            raise ValueError(
                "database contract name must use lowercase snake_case and end with .db"
            )
        table_names = [table.name for table in self.tables]
        if len(table_names) != len(set(table_names)):
            raise ValueError(f"database {self.name} has duplicate tables")
        index_names = [index.name for table in self.tables for index in table.indexes]
        if len(index_names) != len(set(index_names)):
            raise ValueError(f"database {self.name} has duplicate explicit indexes")
        object.__setattr__(
            self,
            "_table_by_name",
            {table.name: table for table in self.tables},
        )

    @property
    def table_by_name(self) -> dict[str, Table]:
        return dict(self._table_by_name)

    def create(self, connection: sqlite3.Connection) -> None:
        for table in self.tables:
            connection.execute(table.create_table_sql())
        for table in self.tables:
            for statement in table.create_index_sql():
                connection.execute(statement)

    def validate_existing(self, path: Path | str) -> bool:
        """Reject any non-empty database that differs from this exact contract."""

        database_path = Path(path)
        if not database_path.is_file() or database_path.stat().st_size == 0:
            return False
        uri = f"file:{database_path.resolve().as_posix()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        try:
            tables = {
                str(row["name"])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
                )
            }
            if not tables:
                return False
            expected_tables = set(self._table_by_name)
            if tables != expected_tables:
                missing = expected_tables - tables
                extra = tables - expected_tables
                details = []
                if missing:
                    details.append(f"missing {', '.join(sorted(missing))}")
                if extra:
                    details.append(f"unexpected {', '.join(sorted(extra))}")
                raise UnsupportedSchemaError(
                    f"UNSUPPORTED_SCHEMA: database {self.name} has "
                    + "; ".join(details)
                    + "."
                )
            for table in self.tables:
                self._validate_table(connection, table)
            self._validate_indexes(connection)
            return True
        finally:
            connection.close()

    def _validate_table(
        self,
        connection: sqlite3.Connection,
        table: Table,
    ) -> None:
        rows = connection.execute(
            f'SELECT name FROM pragma_table_info("{table.name}") ORDER BY cid'
        ).fetchall()
        actual_columns = tuple(str(row["name"]) for row in rows)
        if actual_columns != table.column_names:
            raise UnsupportedSchemaError(
                "UNSUPPORTED_SCHEMA: "
                f"table {table.name} has unsupported column order {actual_columns}."
            )
        row = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table.name,),
        ).fetchone()
        actual_sql = str(row["sql"] or "") if row else ""
        if _canonical_sql(actual_sql) != _canonical_sql(table.create_table_sql()):
            raise UnsupportedSchemaError(
                "UNSUPPORTED_SCHEMA: "
                f"table {table.name} constraints or column definitions are not current."
            )

    def _validate_indexes(self, connection: sqlite3.Connection) -> None:
        expected = {
            index.name: index.sql(table.name)
            for table in self.tables
            for index in table.indexes
        }
        actual = {
            str(row["name"]): str(row["sql"] or "")
            for row in connection.execute(
                "SELECT name, sql FROM sqlite_master "
                "WHERE type = 'index' AND name NOT LIKE 'sqlite_%'"
            )
        }
        if set(actual) != set(expected):
            raise UnsupportedSchemaError(
                f"UNSUPPORTED_SCHEMA: database {self.name} has unsupported explicit indexes."
            )
        for name, expected_sql in expected.items():
            if _canonical_sql(actual[name]) != _canonical_sql(expected_sql):
                raise UnsupportedSchemaError(
                    f"UNSUPPORTED_SCHEMA: index {name} is not current."
                )


def _require_identifier(value: str, label: str) -> None:
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"invalid {label} identifier: {value!r}")


def _require_nonempty_columns(columns: tuple[str, ...], label: str) -> None:
    if not columns:
        raise ValueError(f"{label} must include at least one column")
    for column in columns:
        _require_identifier(column, f"{label} column")


@lru_cache(maxsize=512)
def _canonical_sql(sql: str) -> str:
    without_if_not_exists = re.sub(
        r"\bIF\s+NOT\s+EXISTS\b",
        "",
        sql,
        flags=re.IGNORECASE,
    )
    without_constraint_labels = _strip_constraint_labels(without_if_not_exists)
    return re.sub(r"\s+", " ", without_constraint_labels).strip().rstrip(";")


def _strip_constraint_labels(sql: str) -> str:
    """Remove optional ``CONSTRAINT name`` labels outside quoted SQL values."""

    pattern = re.compile(
        r"\bCONSTRAINT\s+(?:[a-z_][a-z0-9_]*|\"(?:\"\"|[^\"])+\"|"
        r"`(?:``|[^`])+`|\[(?:]]|[^]])+])\s*",
        flags=re.IGNORECASE,
    )
    pieces: list[str] = []
    start = 0
    position = 0
    quote: str | None = None
    while position < len(sql):
        character = sql[position]
        if quote is not None:
            if character == quote:
                if position + 1 < len(sql) and sql[position + 1] == quote:
                    position += 2
                    continue
                quote = None
            position += 1
            continue
        if character == "'":
            quote = character
            position += 1
            continue
        match = pattern.match(sql, position)
        if match is not None:
            pieces.append(sql[start:position])
            start = match.end()
            position = match.end()
            continue
        position += 1
    pieces.append(sql[start:])
    return "".join(pieces)


STORED_FILE_DATA_COLUMNS = (
    Column("mime_type", "TEXT", ColumnGroup.DATA, nullable=False),
    Column("size_bytes", "INTEGER", ColumnGroup.DATA, nullable=False),
    Column("relative_path", "TEXT", ColumnGroup.DATA, nullable=False),
    Column("sha256", "TEXT", ColumnGroup.DATA, nullable=False),
)
