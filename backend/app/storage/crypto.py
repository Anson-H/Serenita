import base64
import binascii
import hashlib
import os
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from backend.app.storage.paths import (
    PRIVATE_FILE_MODE,
    app_paths,
    ensure_private_directory,
    ensure_private_file,
)


_PROVIDER_SECRET_PREFIX = b"serenita-provider-secret:v3:"
_WEB_SECRET_PREFIX = b"serenita-web-secret:v2:"
_PROVIDER_SECRET_NONCE_BYTES = 12
_MASTER_KEY_BYTES = 32
_MASTER_KEY_ENV = "MASTER_KEY"
_WEB_MASTER_KEY_ENV = "WEB_ACCESS_MASTER_KEY"


class ProviderSecretError(RuntimeError):
    """A provider credential could not be stored or authenticated safely."""


class WebSecretError(RuntimeError):
    """A web provider credential could not be stored or authenticated safely."""


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()




def _decode_master_key(encoded: str) -> bytes:
    try:
        key = base64.b64decode(
            encoded.encode("ascii"),
            altchars=b"-_",
            validate=True,
        )
    except (UnicodeEncodeError, ValueError, binascii.Error) as exc:
        raise ProviderSecretError("模型服务密钥主密钥配置无效。") from exc
    if len(key) != _MASTER_KEY_BYTES:
        raise ProviderSecretError("模型服务密钥主密钥配置无效。")
    return key


def _read_or_create_master_key(path: Path) -> bytes:
    ensure_private_directory(path.parent)
    if path.is_symlink():
        raise ProviderSecretError("模型服务密钥主密钥文件无效。")

    if not path.exists():
        candidate = path.with_name(
            f".{path.name}.{os.getpid()}.{os.urandom(8).hex()}.tmp"
        )
        try:
            descriptor = os.open(
                candidate,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                PRIVATE_FILE_MODE,
            )
            with os.fdopen(descriptor, "wb") as handle:
                encoded = base64.urlsafe_b64encode(os.urandom(_MASTER_KEY_BYTES))
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(candidate, path)
            except FileExistsError:
                pass
        except OSError as exc:
            raise ProviderSecretError("无法写入模型服务密钥主密钥。") from exc
        finally:
            try:
                candidate.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                # A stale candidate remains private inside a 0700 directory and
                # is never selected as the active master key.
                pass

    try:
        ensure_private_file(path)
        encoded = path.read_bytes().strip()
    except OSError as exc:
        raise ProviderSecretError("无法读取模型服务密钥主密钥。") from exc
    try:
        return _decode_master_key(encoded.decode("ascii"))
    except UnicodeDecodeError as exc:
        raise ProviderSecretError("模型服务密钥主密钥文件无效。") from exc


def _master_key(paths=None) -> bytes:
    configured_key = os.environ.get(_MASTER_KEY_ENV)
    if configured_key:
        return _decode_master_key(configured_key.strip())
    return _read_or_create_master_key((paths or app_paths()).provider_master_key)


def _web_master_key(paths=None) -> bytes:
    configured_key = os.environ.get(_WEB_MASTER_KEY_ENV)
    if configured_key:
        try:
            return _decode_master_key(configured_key.strip())
        except ProviderSecretError as exc:
            raise WebSecretError("联网服务密钥主密钥配置无效。") from exc
    try:
        return _read_or_create_master_key((paths or app_paths()).web_access_master_key)
    except ProviderSecretError as exc:
        raise WebSecretError("无法安全读取或创建联网服务密钥主密钥。") from exc


def _provider_secret_aad(account_id: str, provider_id: str) -> bytes:
    return f"serenita-provider-secret\0{account_id}\0{provider_id}".encode("utf-8")


def _web_secret_aad(account_id: str, provider_id: str) -> bytes:
    return f"serenita-web-secret\0{account_id}\0{provider_id}".encode("utf-8")


def is_current_provider_secret(sealed_secret: bytes | str | None) -> bool:
    if isinstance(sealed_secret, str):
        sealed_secret = sealed_secret.encode("utf-8")
    return bool(sealed_secret and sealed_secret.startswith(_PROVIDER_SECRET_PREFIX))


def seal_secret(account_id: str, provider_id: str, secret: str, *, paths=None) -> bytes:
    nonce = os.urandom(_PROVIDER_SECRET_NONCE_BYTES)
    encrypted = AESGCM(_master_key(paths)).encrypt(
        nonce,
        secret.encode("utf-8"),
        _provider_secret_aad(account_id, provider_id),
    )
    return _PROVIDER_SECRET_PREFIX + base64.urlsafe_b64encode(nonce + encrypted)


def unseal_secret(
    account_id: str,
    provider_id: str,
    sealed_secret: bytes | str | None,
    *, paths=None,
) -> str:
    if not sealed_secret:
        return ""
    if isinstance(sealed_secret, str):
        sealed_secret = sealed_secret.encode("utf-8")
    if not sealed_secret.startswith(_PROVIDER_SECRET_PREFIX):
        raise ProviderSecretError(
            "已保存的模型服务密钥格式无效，请重新保存 API key。"
        )
    try:
        payload = base64.b64decode(
            sealed_secret[len(_PROVIDER_SECRET_PREFIX) :],
            altchars=b"-_",
            validate=True,
        )
        nonce = payload[:_PROVIDER_SECRET_NONCE_BYTES]
        encrypted = payload[_PROVIDER_SECRET_NONCE_BYTES:]
        if len(nonce) != _PROVIDER_SECRET_NONCE_BYTES or len(encrypted) < 16:
            raise ValueError("invalid encrypted payload")
        plaintext = AESGCM(_master_key(paths)).decrypt(
            nonce,
            encrypted,
            _provider_secret_aad(account_id, provider_id),
        )
        return plaintext.decode("utf-8")
    except (InvalidTag, ValueError, UnicodeDecodeError, binascii.Error) as exc:
        raise ProviderSecretError(
            "已保存的模型服务密钥无法验证，请重新保存 API key。"
        ) from exc


def is_current_web_secret(sealed_secret: bytes | str | None) -> bool:
    if isinstance(sealed_secret, str):
        sealed_secret = sealed_secret.encode("utf-8")
    return bool(sealed_secret and sealed_secret.startswith(_WEB_SECRET_PREFIX))


def seal_web_secret(account_id: str, provider_id: str, secret: str, *, paths=None) -> bytes:
    nonce = os.urandom(_PROVIDER_SECRET_NONCE_BYTES)
    encrypted = AESGCM(_web_master_key(paths)).encrypt(
        nonce,
        secret.encode("utf-8"),
        _web_secret_aad(account_id, provider_id),
    )
    return _WEB_SECRET_PREFIX + base64.urlsafe_b64encode(nonce + encrypted)


def unseal_web_secret(
    account_id: str,
    provider_id: str,
    sealed_secret: bytes | str | None,
    *, paths=None,
) -> str:
    if not sealed_secret:
        return ""
    if isinstance(sealed_secret, str):
        sealed_secret = sealed_secret.encode("utf-8")
    if not sealed_secret.startswith(_WEB_SECRET_PREFIX):
        raise WebSecretError("已保存的联网服务密钥格式无效，请重新保存 API key。")
    try:
        payload = base64.b64decode(
            sealed_secret[len(_WEB_SECRET_PREFIX) :],
            altchars=b"-_",
            validate=True,
        )
        nonce = payload[:_PROVIDER_SECRET_NONCE_BYTES]
        encrypted = payload[_PROVIDER_SECRET_NONCE_BYTES:]
        if len(nonce) != _PROVIDER_SECRET_NONCE_BYTES or len(encrypted) < 16:
            raise ValueError("invalid encrypted payload")
        plaintext = AESGCM(_web_master_key(paths)).decrypt(
            nonce,
            encrypted,
            _web_secret_aad(account_id, provider_id),
        )
        return plaintext.decode("utf-8")
    except (InvalidTag, ValueError, UnicodeDecodeError, binascii.Error) as exc:
        raise WebSecretError(
            "已保存的联网服务密钥无法验证，请重新保存 API key。"
        ) from exc
