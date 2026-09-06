from __future__ import annotations

from backend.app.storage.paths import AppPaths, app_paths
from backend.app.storage.schema import (
    CheckConstraint,
    Column,
    ColumnGroup,
    Database,
    ForeignKey,
    Index,
    Table,
    UniqueConstraint,
)
from backend.app.storage.sqlite import connect


AUTH_DATABASE_SCHEMA = Database(
    name="auth.db",
    tables=(
        Table(
            name="accounts",
            columns=(
                Column("account_id", "TEXT", ColumnGroup.PRIMARY_KEY, nullable=False),
                Column(
                    "account",
                    "TEXT",
                    ColumnGroup.DATA,
                    nullable=False,
                    collation="NOCASE",
                ),
                Column("account_name", "TEXT", ColumnGroup.DATA, nullable=False),
                Column("password_hash", "TEXT", ColumnGroup.DATA, nullable=False),
                Column(
                    "access_revision",
                    "INTEGER",
                    ColumnGroup.STATE,
                    nullable=False,
                    default="0",
                ),
                Column("created_at", "TEXT", ColumnGroup.AUDIT, nullable=False),
                Column("updated_at", "TEXT", ColumnGroup.AUDIT, nullable=False),
            ),
            primary_key=("account_id",),
            unique_constraints=(
                UniqueConstraint(("account",)),
            ),
            checks=(
                CheckConstraint(
                    "length(trim(account_name)) BETWEEN 1 AND 50",
                ),
            ),
        ),
        Table(
            name="login_sessions",
            columns=(
                Column(
                    "session_token_hash",
                    "TEXT",
                    ColumnGroup.PRIMARY_KEY,
                    nullable=False,
                ),
                Column("account_id", "TEXT", ColumnGroup.SCOPE, nullable=False),
                Column("expires_at", "TEXT", ColumnGroup.STATE, nullable=False),
                Column("revoked_at", "TEXT", ColumnGroup.STATE),
                Column("created_at", "TEXT", ColumnGroup.AUDIT, nullable=False),
                Column("updated_at", "TEXT", ColumnGroup.AUDIT, nullable=False),
            ),
            primary_key=("session_token_hash",),
            foreign_keys=(
                ForeignKey(
                    ("account_id",),
                    "accounts",
                    ("account_id",),
                ),
            ),
            indexes=(
                Index("idx_login_sessions__account_id", ("account_id",)),
            ),
        ),
        Table(
            name="member_ownerships",
            columns=(
                Column("member_id", "TEXT", ColumnGroup.PRIMARY_KEY, nullable=False),
                Column("account_id", "TEXT", ColumnGroup.SCOPE, nullable=False),
                Column("created_at", "TEXT", ColumnGroup.AUDIT, nullable=False),
            ),
            primary_key=("member_id",),
            foreign_keys=(
                ForeignKey(
                    ("account_id",),
                    "accounts",
                    ("account_id",),
                ),
            ),
        ),
        Table(
            name="member_grants",
            columns=(
                Column("member_id", "TEXT", ColumnGroup.PRIMARY_KEY, nullable=False),
                Column("account_id", "TEXT", ColumnGroup.PRIMARY_KEY, nullable=False),
                Column("permission", "TEXT", ColumnGroup.STATE, nullable=False),
                Column("updated_at", "TEXT", ColumnGroup.AUDIT, nullable=False),
            ),
            primary_key=("member_id", "account_id"),
            foreign_keys=(
                ForeignKey(
                    ("member_id",),
                    "member_ownerships",
                    ("member_id",),
                ),
                ForeignKey(
                    ("account_id",),
                    "accounts",
                    ("account_id",),
                ),
            ),
            checks=(
                CheckConstraint(
                    "permission IN ('read', 'edit')",
                ),
            ),
        ),
    ),
)


def _validate_schema(paths: AppPaths | None = None) -> bool:
    return AUTH_DATABASE_SCHEMA.validate_existing((paths or app_paths()).auth_db)


def initialize_auth_database(paths: AppPaths | None = None) -> None:
    path = (paths or app_paths()).auth_db
    has_schema = _validate_schema(paths)
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        AUTH_DATABASE_SCHEMA.create(connection)
    if not has_schema:
        _validate_schema(paths)
