from __future__ import annotations

from typing import Any

from backend.app.core.time import local_now_iso
from backend.app.storage.config_database import initialize_config_database
from backend.app.storage.crypto import (
    seal_web_secret,
    unseal_web_secret,
)
from backend.app.storage.paths import app_paths
from backend.app.storage.sqlite import connect


WEB_PROVIDER_IDS = ("tavily", "exa")


class WebAccessRepository:
    def __init__(self, *, paths=None):
        self.paths = paths or app_paths()

    """Account-isolated settings and encrypted credentials for web access."""

    def _path(self, account_id: str):
        return self.paths.config_db(account_id)

    def _initialize(self, account_id: str) -> None:
        initialize_config_database(account_id, self.paths)

    @staticmethod
    def _provider_id(provider_id: str) -> str:
        normalized = str(provider_id or "").strip().lower()
        if normalized not in WEB_PROVIDER_IDS:
            raise ValueError("不支持的联网服务。")
        return normalized

    def get(self, account_id: str) -> dict[str, Any]:
        self._initialize(account_id)
        with connect(self._path(account_id)) as connection:
            row = connection.execute(
                "SELECT is_enabled, active_provider_id "
                "FROM web_access_settings WHERE singleton_id = 1"
            ).fetchone()
            credentials = {
                str(item["provider_id"])
                for item in connection.execute(
                    "SELECT provider_id FROM web_providers "
                    "WHERE is_configured = 1 AND encrypted_api_key IS NOT NULL"
                ).fetchall()
            }
            provider_api_urls = {
                str(item["provider_id"]): str(item["api_url"])
                for item in connection.execute(
                    "SELECT provider_id, api_url FROM web_providers"
                ).fetchall()
            }
        return {
            "is_enabled": bool(row["is_enabled"]),
            "active_provider_id": str(row["active_provider_id"]),
            "configured_providers": credentials,
            "provider_api_urls": provider_api_urls,
        }

    def update(
        self,
        account_id: str,
        *,
        is_enabled: bool | None = None,
        active_provider_id: str | None = None,
    ) -> dict[str, Any]:
        self._initialize(account_id)
        provider = (
            self._provider_id(active_provider_id)
            if active_provider_id is not None
            else None
        )
        with connect(self._path(account_id)) as connection:
            current = connection.execute(
                "SELECT is_enabled, active_provider_id FROM web_access_settings WHERE singleton_id = 1"
            ).fetchone()
            next_provider = provider or str(current["active_provider_id"])
            next_enabled = (
                bool(current["is_enabled"]) if is_enabled is None else bool(is_enabled)
            )
            if next_enabled:
                credential = connection.execute(
                    "SELECT 1 FROM web_providers "
                    "WHERE provider_id = ? AND is_configured = 1 "
                    "AND encrypted_api_key IS NOT NULL",
                    (next_provider,),
                ).fetchone()
                if credential is None:
                    raise ValueError("启用联网前，请先为当前服务保存 API key。")
            connection.execute(
                "UPDATE web_access_settings SET is_enabled = ?, active_provider_id = ? "
                "WHERE singleton_id = 1",
                (int(next_enabled), next_provider),
            )
        return self.get(account_id)

    def update_provider_api_url(
        self,
        account_id: str,
        provider_id: str,
        api_url: str,
    ) -> None:
        self._initialize(account_id)
        provider = self._provider_id(provider_id)
        timestamp = local_now_iso()
        with connect(self._path(account_id)) as connection:
            connection.execute(
                """
                UPDATE web_providers
                SET api_url = ?, updated_at = ?
                WHERE provider_id = ?
                """,
                (api_url, timestamp, provider),
            )

    def save_credential(self, account_id: str, provider_id: str, api_key: str) -> None:
        self._initialize(account_id)
        provider = self._provider_id(provider_id)
        secret = str(api_key or "").strip()
        if not secret:
            raise ValueError("API key 不能为空。")
        if len(secret) > 4096:
            raise ValueError("API key 长度无效。")
        sealed = seal_web_secret(account_id, provider, secret, paths=self.paths)
        timestamp = local_now_iso()
        with connect(self._path(account_id)) as connection:
            connection.execute(
                """
                UPDATE web_providers
                SET encrypted_api_key = ?,
                    is_configured = 1,
                    updated_at = ?
                WHERE provider_id = ?
                """,
                (sealed, timestamp, provider),
            )

    def delete_credential(self, account_id: str, provider_id: str) -> None:
        self._initialize(account_id)
        provider = self._provider_id(provider_id)
        with connect(self._path(account_id)) as connection:
            current = connection.execute(
                "SELECT is_enabled, active_provider_id FROM web_access_settings WHERE singleton_id = 1"
            ).fetchone()
            if (
                bool(current["is_enabled"])
                and str(current["active_provider_id"]) == provider
            ):
                raise ValueError(
                    "请先关闭联网或切换当前服务，再删除正在使用的 API key。"
                )
            connection.execute(
                """
                UPDATE web_providers
                SET encrypted_api_key = NULL,
                    is_configured = 0,
                    updated_at = ?
                WHERE provider_id = ?
                """,
                (local_now_iso(), provider),
            )

    def credential(self, account_id: str, provider_id: str) -> str:
        self._initialize(account_id)
        provider = self._provider_id(provider_id)
        with connect(self._path(account_id)) as connection:
            row = connection.execute(
                "SELECT encrypted_api_key FROM web_providers WHERE provider_id = ?",
                (provider,),
            ).fetchone()
        if row is None:
            return ""
        return unseal_web_secret(
            account_id, provider, row["encrypted_api_key"], paths=self.paths
        )
