from __future__ import annotations
from backend.app.storage.business_change_database import BUSINESS_CHANGE_TABLES

import sqlite3
from pathlib import Path

from backend.app.storage.models.database import MODEL_ACCESS_SETTINGS_TABLE_SCHEMA, MODELS_TABLE_SCHEMA
from backend.app.storage.crypto import is_current_web_secret
from backend.app.storage.paths import AppPaths, app_paths
from backend.app.storage.schema import (
    CheckConstraint,
    Column,
    ColumnGroup,
    Database,
    ForeignKey,
    Table,
)
from backend.app.storage.models.provider_secrets import validate_provider_secret_storage
from backend.app.storage.sqlite import (
    UnsupportedSchemaError,
    connect,
)


MODEL_PROVIDERS_TABLE_SCHEMA = Table(
    name="model_providers",
    columns=(
        Column("provider_id", "TEXT", ColumnGroup.PRIMARY_KEY, nullable=False),
        Column("provider_name", "TEXT", ColumnGroup.DATA, nullable=False),
        Column("api_url", "TEXT", ColumnGroup.DATA, nullable=False),
        Column("official_url", "TEXT", ColumnGroup.DATA),
        Column("encrypted_api_key", "BLOB", ColumnGroup.DATA),

        Column("created_at", "DATETIME", ColumnGroup.AUDIT, nullable=False),
        Column("updated_at", "DATETIME", ColumnGroup.AUDIT, nullable=False),
    ),
    primary_key=("provider_id",),
    checks=(


    ),
)

MEMBER_PREFERENCES_TABLE_SCHEMA = Table(
    name="member_preferences",
    columns=(
        Column("singleton_id", "INTEGER", ColumnGroup.PRIMARY_KEY, nullable=False),
        Column("default_member_id", "TEXT", ColumnGroup.REFERENCE),
        Column("last_member_id", "TEXT", ColumnGroup.REFERENCE),
        Column(
            "startup_mode",
            "TEXT",
            ColumnGroup.STATE,
            nullable=False,
            default="'last_used'",
        ),
    ),
    primary_key=("singleton_id",),
    checks=(
        CheckConstraint("singleton_id = 1"),
        CheckConstraint(
            "startup_mode IN ('default', 'last_used')",
        ),
    ),
)

CONVERSATION_PREFERENCES_TABLE_SCHEMA = Table(
    name="conversation_preferences",
    columns=(
        Column("singleton_id", "INTEGER", ColumnGroup.PRIMARY_KEY, nullable=False),
        Column(
            "composer_submit_shortcut",
            "TEXT",
            ColumnGroup.STATE,
            nullable=False,
            default="'enter'",
        ),
        Column(
            "system_prompt_display_mode",
            "TEXT",
            ColumnGroup.STATE,
            nullable=False,
            default="'conversation_start'",
        ),
        Column(
            "tool_catalog_display_mode",
            "TEXT",
            ColumnGroup.STATE,
            nullable=False,
            default="'conversation_start'",
        ),
        Column(
            "skill_catalog_display_mode",
            "TEXT",
            ColumnGroup.STATE,
            nullable=False,
            default="'conversation_start'",
        ),
        Column(
            "runtime_context_display_mode",
            "TEXT",
            ColumnGroup.STATE,
            nullable=False,
            default="'conversation_start'",
        ),
        Column(
            "is_context_window_usage_visible",
            "INTEGER",
            ColumnGroup.STATE,
            nullable=False,
            default="0",
        ),
        Column(
            "is_related_content_visible",
            "INTEGER",
            ColumnGroup.STATE,
            nullable=False,
            default="1",
        ),
        Column(
            "is_model_identity_visible",
            "INTEGER",
            ColumnGroup.STATE,
            nullable=False,
            default="0",
        ),
        Column(
            "is_token_usage_visible",
            "INTEGER",
            ColumnGroup.STATE,
            nullable=False,
            default="0",
        ),
        Column(
            "is_current_user_message_visible",
            "INTEGER",
            ColumnGroup.STATE,
            nullable=False,
            default="0",
        ),
        Column(
            "is_conversation_history_visible",
            "INTEGER",
            ColumnGroup.STATE,
            nullable=False,
            default="0",
        ),
        Column(
            "is_context_model_tool_request_visible",
            "INTEGER",
            ColumnGroup.STATE,
            nullable=False,
            default="0",
        ),
        Column(
            "is_tool_observation_visible",
            "INTEGER",
            ColumnGroup.STATE,
            nullable=False,
            default="0",
        ),
        Column(
            "is_compacted_summary_visible",
            "INTEGER",
            ColumnGroup.STATE,
            nullable=False,
            default="0",
        ),
        Column(
            "is_execution_model_tool_request_visible",
            "INTEGER",
            ColumnGroup.STATE,
            nullable=False,
            default="1",
        ),
        Column(
            "is_tool_call_visible",
            "INTEGER",
            ColumnGroup.STATE,
            nullable=False,
            default="1",
        ),
    ),
    primary_key=("singleton_id",),
    checks=(
        CheckConstraint(
            "singleton_id = 1",
        ),
        CheckConstraint(
            "composer_submit_shortcut IN ('enter', 'modifier_enter')",
        ),
        *tuple(
            CheckConstraint(
                f"{column} IN ('hidden', 'every_step', "
                "'conversation_start', 'turn_start')",
            )
            for column in (
                "system_prompt_display_mode",
                "tool_catalog_display_mode",
                "skill_catalog_display_mode",
                "runtime_context_display_mode",
            )
        ),
        *tuple(
            CheckConstraint(
                f"{column} IN (0, 1)",
            )
            for column in (
                "is_context_window_usage_visible",
                "is_related_content_visible",
                "is_token_usage_visible",
                "is_model_identity_visible",
                "is_current_user_message_visible",
                "is_conversation_history_visible",
                "is_context_model_tool_request_visible",
                "is_tool_observation_visible",
                "is_compacted_summary_visible",
                "is_execution_model_tool_request_visible",
                "is_tool_call_visible",
            )
        ),
    ),
)

WEB_ACCESS_SETTINGS_TABLE_SCHEMA = Table(
    name="web_access_settings",
    columns=(
        Column("singleton_id", "INTEGER", ColumnGroup.PRIMARY_KEY, nullable=False),
        Column("active_provider_id", "TEXT", ColumnGroup.REFERENCE, nullable=False),
        Column("is_enabled", "INTEGER", ColumnGroup.STATE, nullable=False),
    ),
    primary_key=("singleton_id",),
    foreign_keys=(
        ForeignKey(
            ("active_provider_id",),
            "web_providers",
            ("provider_id",),
        ),
    ),
    checks=(
        CheckConstraint("singleton_id = 1"),
        CheckConstraint(
            "active_provider_id IN ('tavily', 'exa')",
        ),
        CheckConstraint(
            "is_enabled IN (0, 1)",
        ),
    ),
)

WEB_PROVIDERS_TABLE_SCHEMA = Table(
    name="web_providers",
    columns=(
        Column("provider_id", "TEXT", ColumnGroup.PRIMARY_KEY, nullable=False),
        Column("api_url", "TEXT", ColumnGroup.DATA, nullable=False),
        Column("encrypted_api_key", "BLOB", ColumnGroup.DATA),

        Column("created_at", "DATETIME", ColumnGroup.AUDIT, nullable=False),
        Column("updated_at", "DATETIME", ColumnGroup.AUDIT, nullable=False),
    ),
    primary_key=("provider_id",),
    checks=(
        CheckConstraint(
            "provider_id IN ('tavily', 'exa')",
        ),


    ),
)

CONFIG_DATABASE_SCHEMA = Database(
    name="settings.db",
    tables=(
        MODEL_PROVIDERS_TABLE_SCHEMA,
        MODELS_TABLE_SCHEMA,
        MODEL_ACCESS_SETTINGS_TABLE_SCHEMA,
        MEMBER_PREFERENCES_TABLE_SCHEMA,
        CONVERSATION_PREFERENCES_TABLE_SCHEMA,
        WEB_PROVIDERS_TABLE_SCHEMA,
        WEB_ACCESS_SETTINGS_TABLE_SCHEMA,
        *BUSINESS_CHANGE_TABLES,
    ),
)


def validate_config_database(
    account_id: str,
    paths: AppPaths | None = None,
) -> bool:
    """Strictly validate an existing account configuration database."""

    resolved_paths = paths or app_paths()
    path = resolved_paths.config_db(account_id)
    if not CONFIG_DATABASE_SCHEMA.validate_existing(path):
        return False

    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        validate_provider_secret_storage(connection)
        web_credentials = connection.execute(
            "SELECT provider_id, encrypted_api_key FROM web_providers"
        ).fetchall()
        for row in web_credentials:
            if row["encrypted_api_key"] is not None and not is_current_web_secret(
                row["encrypted_api_key"]
            ):
                raise UnsupportedSchemaError(
                    "UNSUPPORTED_SCHEMA: web credential secret format is not current."
                )
        for table_name in (
            "model_access_settings",
            "conversation_preferences",
            "web_access_settings",
        ):
            rows = connection.execute(
                f"SELECT singleton_id FROM {table_name}"
            ).fetchall()
            if len(rows) != 1 or int(rows[0]["singleton_id"]) != 1:
                raise UnsupportedSchemaError(
                    f"UNSUPPORTED_SCHEMA: {table_name} is not current."
                )
    return True




def require_config_database(
    account_id: str,
    paths: AppPaths | None = None,
) -> Path:
    """Return the current configuration database path or reject its absence."""

    resolved_paths = paths or app_paths()
    path = resolved_paths.config_db(account_id)
    if not validate_config_database(account_id, resolved_paths):
        raise UnsupportedSchemaError(
            "UNSUPPORTED_SCHEMA: account configuration database is missing."
        )
    return path
