from backend.app.storage.schema import (
    CheckConstraint,
    Column,
    ColumnGroup,
    ForeignKey,
    Index,
    Table,
)
from backend.app.domain.model_capabilities import MODEL_DEFAULT_COLUMN_BY_PURPOSE


MODELS_TABLE_SCHEMA = Table(
    name="models",
    columns=(
        Column("model_id", "TEXT", ColumnGroup.PRIMARY_KEY, nullable=False),
        Column("provider_id", "TEXT", ColumnGroup.SCOPE, nullable=False),
        Column("remote_model_id", "TEXT", ColumnGroup.DATA, nullable=False),
        Column("model_name", "TEXT", ColumnGroup.DATA, nullable=False),
        Column("model_type", "TEXT", ColumnGroup.STATE, nullable=False, default="'unknown'"),
        Column("thinking_modes", "TEXT", ColumnGroup.STATE),
        Column("capability_profiles", "TEXT", ColumnGroup.STATE, json_kind="object"),
        Column("context_window_tokens", "INTEGER", ColumnGroup.STATE),
        Column("max_output_tokens", "INTEGER", ColumnGroup.STATE),
        Column("capability_detection", "TEXT", ColumnGroup.STATE, json_kind="object"),
        Column("embedding_capabilities", "TEXT", ColumnGroup.STATE, json_kind="object"),
        Column("embedding_dimensions", "INTEGER", ColumnGroup.STATE),
        Column("max_input_tokens", "INTEGER", ColumnGroup.STATE),
        Column("max_batch_size", "INTEGER", ColumnGroup.STATE),
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
    checks=(
        CheckConstraint("model_type IN ('generation', 'embedding', 'unknown')"),
        CheckConstraint("(model_type = 'generation' AND thinking_modes IS NOT NULL AND capability_profiles IS NOT NULL) OR (model_type <> 'generation' AND thinking_modes IS NULL AND capability_profiles IS NULL AND context_window_tokens IS NULL AND max_output_tokens IS NULL)"),
        CheckConstraint("model_type = 'embedding' OR (embedding_capabilities IS NULL AND embedding_dimensions IS NULL AND max_input_tokens IS NULL AND max_batch_size IS NULL)"),
        *(CheckConstraint(f"{name} IS NULL OR {name} > 0") for name in ("context_window_tokens", "max_output_tokens", "embedding_dimensions", "max_input_tokens", "max_batch_size")),
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
        Column("text_embedding_model_id", "TEXT", ColumnGroup.REFERENCE),
        Column("multimodal_embedding_model_id", "TEXT", ColumnGroup.REFERENCE),
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
