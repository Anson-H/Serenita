from typing import Any

from backend.app.storage.crypto import (
    is_current_provider_secret,
    seal_secret,
    unseal_secret,
)
from backend.app.storage.sqlite import UnsupportedSchemaError


def ensure_provider_secret_storage(connection, account_id: str) -> None:
    """Validate that configured secrets already use the current sealed format."""

    rows = connection.execute(
        "SELECT provider_id, encrypted_api_key FROM model_providers"
    ).fetchall()
    for row in rows:
        if row["encrypted_api_key"] and not is_current_provider_secret(row["encrypted_api_key"]):
            raise UnsupportedSchemaError(
                "UNSUPPORTED_SCHEMA: provider secret format is not current."
            )


def provider_secret_from_row(account_id: str, row: Any, *, paths=None) -> str:
    if not row or not row["is_configured"]:
        return ""
    if row["encrypted_api_key"]:
        return unseal_secret(account_id, row["provider_id"], row["encrypted_api_key"], paths=paths)
    return ""


def sealed_provider_secret(account_id: str, provider_id: str, secret: str, *, paths=None) -> bytes:
    return seal_secret(account_id, provider_id, secret, paths=paths)
