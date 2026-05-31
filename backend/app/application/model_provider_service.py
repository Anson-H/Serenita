from typing import Any, Optional

from backend.app.api.auth import raise_error
from backend.app.bootstrap import create_default_provider_registry
from backend.app.model_capabilities import (
    capability_response,
    create_models_table_sql,
    ensure_model_capability_columns,
    ensure_model_default_settings_table,
    profile_from_row,
)
from backend.app.providers.base import ProviderChatCompletionError
from backend.app.providers.registry import ProviderNotFoundError
from backend.app.storage.crypto import unseal_secret
from backend.app.storage.paths import app_paths
from backend.app.storage.sqlite import connect


class ModelProviderService:
    def __init__(self, provider_registry=None):
        self.provider_registry = provider_registry

    def default_model_for_account(self, account: str, setting_key: str = "chat") -> Optional[dict[str, Any]]:
        self._init_config_db(account)
        with connect(app_paths().config_db(account)) as connection:
            row = self._default_model_row(connection, setting_key)
        return self._model_response(row) if row else None

    def model_for_account(self, account: str, model_id: str) -> Optional[dict[str, Any]]:
        self._init_config_db(account)
        with connect(app_paths().config_db(account)) as connection:
            row = connection.execute(
                "SELECT * FROM models WHERE model_id = ?",
                (model_id,),
            ).fetchone()
        return self._model_response(row) if row else None

    def complete_chat_for_account(
        self,
        account: str,
        model: dict[str, Any],
        messages: list[dict[str, str]],
        thinking_mode: str,
    ):
        provider_id = model["provider_id"]
        provider = self._provider(provider_id)
        row = self._provider_row(account, provider_id)
        if not row or not row["configured"]:
            raise_error(422, "MODEL_NOT_CONFIGURED", "请先配置该模型服务。")
        api_key = self._api_key_from_row(account, row)
        if not api_key:
            raise_error(422, "MODEL_NOT_CONFIGURED", "请先输入或保存 API key。")

        try:
            return provider.complete_chat(
                base_url=row["base_url"] or provider.default_base_url,
                api_key=api_key,
                remote_model_id=model["remote_model_id"],
                messages=messages,
                thinking_mode=thinking_mode,
            )
        except ProviderChatCompletionError as exc:
            self._raise_provider_error(str(exc))

    def stream_chat_for_account(
        self,
        account: str,
        model: dict[str, Any],
        messages: list[dict[str, str]],
        thinking_mode: str,
    ):
        provider_id = model["provider_id"]
        provider = self._provider(provider_id)
        row = self._provider_row(account, provider_id)
        if not row or not row["configured"]:
            raise_error(422, "MODEL_NOT_CONFIGURED", "请先配置该模型服务。")
        api_key = self._api_key_from_row(account, row)
        if not api_key:
            raise_error(422, "MODEL_NOT_CONFIGURED", "请先输入或保存 API key。")

        return provider.stream_chat(
            base_url=row["base_url"] or provider.default_base_url,
            api_key=api_key,
            remote_model_id=model["remote_model_id"],
            messages=messages,
            thinking_mode=thinking_mode,
        )

    def provider_supports_native_attachment(self, model: dict[str, Any], mime_type: str) -> bool:
        provider = self._provider(model["provider_id"])
        return provider.supports_native_attachment(mime_type)

    def _init_config_db(self, account: str) -> None:
        with connect(app_paths().config_db(account)) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS model_providers (
                    provider_id TEXT PRIMARY KEY,
                    provider_name TEXT NOT NULL,
                    base_url TEXT NOT NULL,
                    official_url TEXT,
                    api_key TEXT,
                    configured INTEGER NOT NULL DEFAULT 0,
                    default_provider INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(model_providers)").fetchall()
            }
            if "api_key" not in columns:
                connection.execute("ALTER TABLE model_providers ADD COLUMN api_key TEXT")
            if "official_url" not in columns:
                connection.execute("ALTER TABLE model_providers ADD COLUMN official_url TEXT")
            connection.execute(create_models_table_sql())
            ensure_model_capability_columns(connection)
            ensure_model_default_settings_table(connection)
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_models_provider_remote
                ON models(provider_id, remote_model_id)
                """
            )

    def _provider(self, provider_id: str):
        registry = self.provider_registry or create_default_provider_registry()
        try:
            return registry.get(provider_id)
        except ProviderNotFoundError:
            raise_error(404, "NOT_FOUND", "模型服务不存在。")

    def _provider_row(self, account: str, provider_id: str):
        self._init_config_db(account)
        with connect(app_paths().config_db(account)) as connection:
            return connection.execute(
                "SELECT * FROM model_providers WHERE provider_id = ?",
                (provider_id,),
            ).fetchone()

    def _api_key_from_row(self, account: str, row) -> str:
        if not row or not row["configured"]:
            return ""
        if row["api_key"]:
            return row["api_key"]
        if "key_info_data" in row.keys() and row["key_info_data"]:
            return unseal_secret(account, row["key_info_data"])
        return ""

    def _model_response(self, row) -> dict[str, Any]:
        profile = profile_from_row(row)
        return {
            "model_id": row["model_id"],
            "provider_id": row["provider_id"],
            "remote_model_id": row["remote_model_id"],
            "model_name": row["model_name"],
            **capability_response(profile),
        }

    def _default_model_row(self, connection, setting_key: str):
        return connection.execute(
            """
            SELECT models.*
            FROM model_default_settings
            JOIN models ON models.model_id = model_default_settings.model_id
            WHERE model_default_settings.setting_key = ?
            LIMIT 1
            """,
            (setting_key,),
        ).fetchone()

    def _raise_provider_error(self, message: str) -> None:
        if "认证失败" in message:
            raise_error(502, "PROVIDER_AUTH_FAILED", message)
        if "超时" in message:
            raise_error(504, "MODEL_TIMEOUT", message)
        raise_error(502, "MODEL_ERROR", message or "模型服务调用失败。")
