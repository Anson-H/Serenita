"""Create account settings and their initial business receipts in one transaction."""
from backend.app.core.time import local_now_iso
from backend.app.storage.config_database import CONFIG_DATABASE_SCHEMA, validate_config_database
from backend.app.storage.paths import AppPaths, app_paths
from backend.app.storage.sqlite import connect


def initialize_config_database(
    account_id: str,
    paths: AppPaths | None = None,
) -> None:
    """Validate and initialize the account's complete current configuration schema."""

    resolved_paths = paths or app_paths()
    database_path = resolved_paths.config_db(account_id)
    has_schema = False
    with connect(database_path) as connection:
        # Serialize first-use requests before inspecting the schema, and publish
        # the complete schema in one commit. SQLite otherwise auto-commits DDL,
        # allowing another request to observe a partially initialized database.
        connection.execute("BEGIN IMMEDIATE")
        has_schema = validate_config_database(account_id, resolved_paths)
        CONFIG_DATABASE_SCHEMA.create(connection)
        connection.execute(
            "INSERT OR IGNORE INTO model_access_settings (singleton_id) VALUES (1)"
        )
        connection.execute(
            "INSERT OR IGNORE INTO conversation_preferences (singleton_id) VALUES (1)"
        )
        timestamp = local_now_iso()
        connection.executemany(
            """
            INSERT OR IGNORE INTO web_providers (
                provider_id, api_url, encrypted_api_key,
                created_at, updated_at
            ) VALUES (?, ?, NULL, ?, ?)
            """,
            (
                ("tavily", "https://api.tavily.com", timestamp, timestamp),
                ("exa", "https://api.exa.ai", timestamp, timestamp),
            ),
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO web_access_settings (
                singleton_id, active_provider_id, is_enabled
            ) VALUES (1, 'tavily', 0)
            """
        )
        if not has_schema:
            from backend.app.repositories.preference_changes import record_initial_preference
            record_initial_preference(connection, account_id, "conversation_preference")
    if not has_schema:
        validate_config_database(account_id, resolved_paths)
