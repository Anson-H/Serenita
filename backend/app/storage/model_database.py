from backend.app.storage.schema import (
    CheckConstraint,
    Column,
    ColumnGroup,
    ForeignKey,
    Index,
    Table,
)
from backend.app.model_capabilities import MODEL_DEFAULT_COLUMN_BY_PURPOSE


MODELS_TABLE_SCHEMA = Table(
    name="models",
    columns=(
        Column("model_id", "TEXT", ColumnGroup.PRIMARY_KEY, nullable=False),
        Column("provider_id", "TEXT", ColumnGroup.SCOPE, nullable=False),
        Column("remote_model_id", "TEXT", ColumnGroup.DATA, nullable=False),
        Column("model_name", "TEXT", ColumnGroup.DATA, nullable=False),
        Column(
            "thinking_modes",
            "TEXT",
            ColumnGroup.STATE,
            nullable=False,
            default="'default'",
        ),
        Column(
            "capability_profiles",
            "TEXT",
            ColumnGroup.STATE,
            nullable=False,
        ),
        Column(
            "context_window_tokens",
            "INTEGER",
            ColumnGroup.STATE,
            nullable=False,
            default="131072",
        ),
        Column("max_output_tokens", "INTEGER", ColumnGroup.STATE),
        Column("created_at", "TEXT", ColumnGroup.AUDIT, nullable=False),
        Column("updated_at", "TEXT", ColumnGroup.AUDIT, nullable=False),
    ),
    primary_key=("model_id",),
    foreign_keys=(
        ForeignKey(
            ("provider_id",),
            "model_providers",
            ("provider_id",),
        ),
    ),
    indexes=(
        Index(
            "uidx_models__provider_remote",
            ("provider_id", "remote_model_id"),
            unique=True,
        ),
    ),
)


MODEL_ACCESS_SETTINGS_TABLE_SCHEMA = Table(
    name="model_access_settings",
    columns=(
        Column("singleton_id", "INTEGER", ColumnGroup.PRIMARY_KEY, nullable=False),
        Column("chat_model_id", "TEXT", ColumnGroup.REFERENCE),
        Column("title_model_id", "TEXT", ColumnGroup.REFERENCE),
        Column("vision_parse_model_id", "TEXT", ColumnGroup.REFERENCE),
        Column("compact_model_id", "TEXT", ColumnGroup.REFERENCE),
    ),
    primary_key=("singleton_id",),
    foreign_keys=tuple(
        ForeignKey(
            (column_name,),
            "models",
            ("model_id",),
            on_delete="SET NULL",
        )
        for column_name in MODEL_DEFAULT_COLUMN_BY_PURPOSE.values()
    ),
    checks=(CheckConstraint("singleton_id = 1"),),
)


def create_models_table_sql() -> str:
    return MODELS_TABLE_SCHEMA.create_table_sql()


def create_model_access_settings_table_sql() -> str:
    return MODEL_ACCESS_SETTINGS_TABLE_SCHEMA.create_table_sql()


def ensure_model_access_settings_table(connection) -> None:
    connection.execute(create_model_access_settings_table_sql())
