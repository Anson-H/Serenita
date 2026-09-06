"""Schema ownership for the operator's private favorites database."""

from backend.app.storage.paths import AppPaths, app_paths
from backend.app.storage.schema import (
    CheckConstraint,
    Column,
    ColumnGroup,
    Database,
    Index,
    Table,
)
from backend.app.storage.sqlite import connect


FAVORITES_DATABASE_SCHEMA = Database(
    name="favorites.db",
    tables=(
        Table(
            name="favorites",
            columns=(
                Column("favorite_id", "TEXT", ColumnGroup.PRIMARY_KEY, nullable=False),
                Column("member_id", "TEXT", ColumnGroup.SCOPE),
                Column("source_type", "TEXT", ColumnGroup.REFERENCE, nullable=False),
                Column(
                    "source_session_id",
                    "TEXT",
                    ColumnGroup.REFERENCE,
                    nullable=False,
                ),
                Column("source_id", "TEXT", ColumnGroup.REFERENCE, nullable=False),
                Column("title", "TEXT", ColumnGroup.DATA, nullable=False),
                Column("content_snapshot", "TEXT", ColumnGroup.DATA, nullable=False),
                Column(
                    "tags",
                    "TEXT",
                    ColumnGroup.DATA,
                    nullable=False,
                    default="'[]'",
                ),
                Column("created_at", "TEXT", ColumnGroup.AUDIT, nullable=False),
                Column("updated_at", "TEXT", ColumnGroup.AUDIT, nullable=False),
            ),
            primary_key=("favorite_id",),
            checks=(
                CheckConstraint(
                    "source_type IN ('message', 'report')",
                ),
            ),
            indexes=(
                Index(
                    "uidx_favorites__message_source",
                    ("source_session_id", "source_id"),
                    unique=True,
                    where="source_type = 'message'",
                ),
                Index(
                    "uidx_favorites__report_source",
                    ("member_id", "source_id"),
                    unique=True,
                    where="source_type = 'report'",
                ),
                Index("idx_favorites__created_at", ("created_at",)),
            ),
        ),
    ),
)


def validate_favorites_db(account_id: str, paths: AppPaths | None = None) -> bool:
    return FAVORITES_DATABASE_SCHEMA.validate_existing(
        (paths or app_paths()).favorites_db(account_id)
    )


def initialize_favorites_database(account_id: str, paths: AppPaths | None = None) -> None:
    has_schema = validate_favorites_db(account_id, paths)
    database_path = (paths or app_paths()).favorites_db(account_id)
    with connect(database_path) as connection:
        FAVORITES_DATABASE_SCHEMA.create(connection)
    if not has_schema:
        validate_favorites_db(account_id, paths)


def favorite_member_references(paths):
    from backend.app.storage.private_references import PrivateReferenceStore
    return PrivateReferenceStore(
        source="favorite", table="favorites", id_column="favorite_id",
        path_for_account=paths.favorites_db,
        validate_existing=lambda account_id: FAVORITES_DATABASE_SCHEMA.validate_existing(paths.favorites_db(account_id)),
        interrupts_sessions=False,
    )
