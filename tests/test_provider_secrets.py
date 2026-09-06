import base64
import os
import sqlite3
import stat
import pytest
from backend.app.storage.crypto import ProviderSecretError, is_current_provider_secret, seal_secret, unseal_secret
from backend.app.storage.provider_secrets import ensure_provider_secret_storage
from backend.app.storage.sqlite import UnsupportedSchemaError


@pytest.fixture
def isolated_secret_storage(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "serenita_files"))
    monkeypatch.delenv("MASTER_KEY", raising=False)
    return tmp_path / "serenita_files"


def _provider_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE model_providers (
            provider_id TEXT PRIMARY KEY,
            encrypted_api_key BLOB,
            is_configured INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    return connection


def test_authenticated_provider_ciphertext_is_random_and_round_trips(
    isolated_secret_storage,
):
    first = seal_secret("account-a", "provider-a", "test-secret")
    second = seal_secret("account-a", "provider-a", "test-secret")

    assert first != second
    assert is_current_provider_secret(first)
    assert b"test-secret" not in first
    assert unseal_secret("account-a", "provider-a", first) == "test-secret"
    assert unseal_secret("account-a", "provider-a", second) == "test-secret"


def test_provider_ciphertext_rejects_wrong_aad_and_tampering(isolated_secret_storage):
    sealed = seal_secret("account-a", "provider-a", "test-secret")

    with pytest.raises(ProviderSecretError, match="无法验证"):
        unseal_secret("account-b", "provider-a", sealed)
    with pytest.raises(ProviderSecretError, match="无法验证"):
        unseal_secret("account-a", "provider-b", sealed)

    tampered = bytearray(sealed)
    tampered[-2] = ord("A") if tampered[-2] != ord("A") else ord("B")
    with pytest.raises(ProviderSecretError, match="无法验证"):
        unseal_secret("account-a", "provider-a", bytes(tampered))


@pytest.mark.parametrize("invalid", [b"cHJldmlvdXMtZm9ybWF0", b"not valid base64!"])
def test_invalid_provider_secret_is_rejected_without_rewriting_or_disclosure(isolated_secret_storage, invalid):
    with _provider_connection() as connection:
        connection.execute(
            "INSERT INTO model_providers (provider_id, encrypted_api_key) VALUES (?, ?)",
            ("provider-a", invalid),
        )
        with pytest.raises(UnsupportedSchemaError, match="UNSUPPORTED_SCHEMA") as error:
            ensure_provider_secret_storage(connection, "account-a")
        assert connection.execute("SELECT encrypted_api_key FROM model_providers").fetchone()[0] == invalid
        assert invalid.decode() not in str(error.value)


def test_master_key_file_is_global_separate_and_private(isolated_secret_storage):
    seal_secret("account-a", "provider-a", "test-secret")
    master_key = isolated_secret_storage / "all_users" / "secrets" / "provider_master.key"
    account_config = isolated_secret_storage / "account-a" / "config" / "settings.db"

    assert master_key.is_file()
    assert stat.S_IMODE(master_key.stat().st_mode) == 0o600
    assert stat.S_IMODE(master_key.parent.stat().st_mode) == 0o700
    assert account_config.parent not in master_key.parents
    assert len(base64.urlsafe_b64decode(master_key.read_bytes())) == 32


def test_environment_master_key_avoids_master_key_file(tmp_path, monkeypatch):
    data_root = tmp_path / "serenita_files"
    monkeypatch.setenv("DATA_ROOT", str(data_root))
    monkeypatch.setenv(
        "MASTER_KEY",
        base64.urlsafe_b64encode(os.urandom(32)).decode("ascii"),
    )

    sealed = seal_secret("account-a", "provider-a", "test-secret")

    assert unseal_secret("account-a", "provider-a", sealed) == "test-secret"
    assert not (data_root / "all_users" / "secrets" / "provider_master.key").exists()
