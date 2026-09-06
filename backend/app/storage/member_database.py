from __future__ import annotations

from pathlib import Path

from backend.app.storage.paths import AppPaths, app_paths
from backend.app.storage.schema import (
    CheckConstraint,
    Column,
    ColumnGroup,
    Database,
    Table,
)
from backend.app.storage.sqlite import (
    UnsupportedSchemaError,
    connect,
)


MEMBER_DATABASE_SCHEMA = Database(
    name="members.db",
    tables=(
        Table(
            name="members",
            columns=(
                Column("member_id", "TEXT", ColumnGroup.PRIMARY_KEY, nullable=False),
                Column("member_name", "TEXT", ColumnGroup.DATA, nullable=False),
                Column("sex", "TEXT", ColumnGroup.DATA),
                Column("birth_date", "TEXT", ColumnGroup.DATA),
                Column("blood_type", "TEXT", ColumnGroup.DATA),
                Column("created_at", "TEXT", ColumnGroup.AUDIT, nullable=False),
                Column("updated_at", "TEXT", ColumnGroup.AUDIT, nullable=False),
            ),
            primary_key=("member_id",),
            checks=(
                CheckConstraint(
                    "length(trim(member_name)) > 0",
                ),
                CheckConstraint(
                    "sex IN ('male', 'female', 'other') OR sex IS NULL",
                ),
                CheckConstraint(
                    "blood_type IN ('a', 'b', 'ab', 'o', 'other') "
                    "OR blood_type IS NULL",
                ),
            ),
        ),
    ),
)


def validate_member_database(
    account_id: str,
    paths: AppPaths | None = None,
) -> bool:
    """Validate an existing owner member database without creating it."""

    database_path = (paths or app_paths()).members_db(account_id)
    return MEMBER_DATABASE_SCHEMA.validate_existing(database_path)


def require_member_database(
    account_id: str,
    paths: AppPaths | None = None,
) -> Path:
    """Return the current member database path or reject missing owner data."""

    resolved_paths = paths or app_paths()
    database_path = resolved_paths.members_db(account_id)
    if not validate_member_database(account_id, resolved_paths):
        raise UnsupportedSchemaError(
            "UNSUPPORTED_SCHEMA: member registry points to a missing member database."
        )
    return database_path


def initialize_member_database(
    account_id: str,
    paths: AppPaths | None = None,
) -> None:
    """Create or strictly validate an owner's member profile database."""

    resolved_paths = paths or app_paths()
    database_path = resolved_paths.members_db(account_id)
    has_schema = validate_member_database(account_id, resolved_paths)
    with connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        MEMBER_DATABASE_SCHEMA.create(connection)
    if not has_schema:
        validate_member_database(account_id, resolved_paths)
