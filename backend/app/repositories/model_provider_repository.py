from contextlib import contextmanager

from backend.app.domain.model_capabilities import MODEL_DEFAULT_COLUMN_BY_PURPOSE
from backend.app.storage.model_codec import capability_column_values
from backend.app.storage.config_database import initialize_config_database, CONFIG_DATABASE_SCHEMA
from backend.app.storage.paths import app_paths
from backend.app.storage.sqlite import connect


class ModelProviderTransaction:
    def __init__(self, connection):
        self.connection = connection

    def validate_write(self, table, values, previous=None):
        contract = CONFIG_DATABASE_SCHEMA.table_by_name[table]
        contract.validate_values({**dict(previous or {}), **values}, partial=previous is None)

    def get_provider(self, *, provider_id):
        values = (provider_id,)
        return self.connection.execute(
            "SELECT * FROM model_providers WHERE provider_id = ?", values
        ).fetchone()

    def get_public_provider(self, *, provider_id):
        values = (provider_id,)
        return self.connection.execute(
            """
            SELECT provider_id, provider_name, api_url, official_url,
                   is_configured,
                   CASE
                       WHEN is_configured = 1
                        AND COALESCE(LENGTH(encrypted_api_key), 0) > 0
                       THEN 1 ELSE 0
                   END AS has_api_key
            FROM model_providers
            WHERE provider_id = ?
            """,
            values,
        ).fetchone()

    def get_model(self, *, model_id):
        values = (model_id,)
        return self.connection.execute(
            "SELECT * FROM models WHERE model_id = ?", values
        ).fetchone()

    def default_model(self, purpose):
        values = ()
        column_name = MODEL_DEFAULT_COLUMN_BY_PURPOSE[purpose]
        return self.connection.execute(
            f"""
        SELECT models.*
        FROM model_access_settings
        JOIN models ON models.model_id = model_access_settings.{column_name}
        WHERE model_access_settings.singleton_id = 1
        LIMIT 1
        """,
            values,
        ).fetchone()

    def set_default(self, purpose, *, model_id):
        values = (model_id,)
        column_name = MODEL_DEFAULT_COLUMN_BY_PURPOSE[purpose]
        return self.connection.execute(
            f"""
        UPDATE model_access_settings
        SET {column_name} = ?
        WHERE singleton_id = 1
        """,
            values,
        )

    def write_profile(self, *, model_id, model_name, profile, profiles, updated_at):
        values = (
            model_name,
            updated_at,
            *capability_column_values(profile, profiles),
            model_id,
        )
        self.validate_write('models', dict(zip(('model_name','updated_at','thinking_modes','capability_profiles','context_window_tokens','max_output_tokens','model_id'), values)), self.get_model(model_id=model_id))
        return self.connection.execute(
            """
        UPDATE models
        SET model_name = ?, updated_at = ?,
            thinking_modes = ?, capability_profiles = ?,
            context_window_tokens = ?, max_output_tokens = ?
        WHERE model_id = ?
        """,
            values,
        )

    def save_provider(
        self,
        *,
        provider_id,
        provider_name,
        api_url,
        official_url,
        encrypted_api_key,
        is_configured,
        created_at,
        updated_at,
    ):
        values = (
            provider_id,
            provider_name,
            api_url,
            official_url,
            encrypted_api_key,
            is_configured,
            created_at,
            updated_at,
        )
        self.validate_write('model_providers', dict(zip(CONFIG_DATABASE_SCHEMA.table_by_name['model_providers'].column_names, values)))
        return self.connection.execute(
            """
            INSERT INTO model_providers (
                provider_id, provider_name, api_url, official_url, encrypted_api_key,
                is_configured,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(provider_id) DO UPDATE SET
                provider_name = excluded.provider_name,
                api_url = excluded.api_url,
                official_url = excluded.official_url,
                encrypted_api_key = excluded.encrypted_api_key,
                is_configured = excluded.is_configured,
                updated_at = excluded.updated_at
            """,
            values,
        )

    def update_provider(
        self,
        *,
        api_url,
        official_url,
        encrypted_api_key,
        is_configured,
        updated_at,
        provider_id,
    ):
        values = (
            api_url,
            official_url,
            encrypted_api_key,
            is_configured,
            updated_at,
            provider_id,
        )
        self.validate_write('model_providers', dict(zip(('api_url','official_url','encrypted_api_key','is_configured','updated_at','provider_id'), values)), self.get_provider(provider_id=provider_id))
        return self.connection.execute(
            """
            UPDATE model_providers
            SET api_url = ?, official_url = ?, encrypted_api_key = ?,
                is_configured = ?, updated_at = ?
            WHERE provider_id = ?
            """,
            values,
        )

    def save_model(
        self,
        *,
        model_id,
        provider_id,
        remote_model_id,
        model_name,
        created_at,
        updated_at,
    ):
        values = (model_id, provider_id, remote_model_id, model_name, created_at, updated_at)
        self.validate_write('models', dict(zip(('model_id','provider_id','remote_model_id','model_name','created_at','updated_at'), values)))
        self.connection.execute(
            "INSERT INTO models (model_id, provider_id, remote_model_id, model_name, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(model_id) DO NOTHING", values
        )

    def write_typed_model(self, *, model_id, model_type, model_name, profile=None, profiles=None,
                          embedding_capabilities=None, embedding_dimensions=None,
                          max_input_tokens=None, max_batch_size=None, updated_at):
        import json
        generation = capability_column_values(profile, profiles) if model_type == "generation" else (None,) * 4
        embedding = (json.dumps(embedding_capabilities) if embedding_capabilities is not None else None, embedding_dimensions, max_input_tokens, max_batch_size) if model_type == "embedding" else (None,) * 4
        self.validate_write('models', dict(zip(('model_type','model_name','thinking_modes','capability_profiles','context_window_tokens','max_output_tokens','embedding_capabilities','embedding_dimensions','max_input_tokens','max_batch_size','updated_at','model_id'), (model_type, model_name, *generation, *embedding, updated_at, model_id))), self.get_model(model_id=model_id))
        self.connection.execute(
            """UPDATE models SET model_type = ?, model_name = ?, thinking_modes = ?,
            capability_profiles = ?, context_window_tokens = ?, max_output_tokens = ?,
            embedding_capabilities = ?, embedding_dimensions = ?, max_input_tokens = ?,
            max_batch_size = ?, updated_at = ? WHERE model_id = ?""",
            (model_type, model_name, *generation, *embedding, updated_at, model_id),
        )

    def list_models(self):
        values = ()
        return self.connection.execute(
            "SELECT * FROM models ORDER BY created_at", values
        ).fetchall()

    def model_id_row(self, *, model_id):
        values = (model_id,)
        return self.connection.execute(
            "SELECT model_id FROM models WHERE model_id = ?", values
        ).fetchone()

    def delete_model(self, *, model_id):
        values = (model_id,)
        return self.connection.execute("DELETE FROM models WHERE model_id = ?", values)


class ModelProviderRepository:
    def __init__(self, *, paths=None):
        self.paths = paths or app_paths()

    @contextmanager
    def transaction(self, account_id, *, write=False):
        initialize_config_database(account_id, self.paths)
        with connect(self.paths.config_db(account_id)) as connection:
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield ModelProviderTransaction(connection)

    def get_provider(self, account_id, provider_id):
        with self.transaction(account_id) as transaction:
            return transaction.get_provider(provider_id=provider_id)

    def get_model(self, account_id, model_id):
        with self.transaction(account_id) as transaction:
            return transaction.get_model(model_id=model_id)

    def default_model(self, account_id, purpose):
        with self.transaction(account_id) as transaction:
            return transaction.default_model(purpose)
