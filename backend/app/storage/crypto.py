import hashlib
import base64


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def md5_text(value: str) -> str:
    return hashlib.md5(value.encode("utf-8")).hexdigest()


def seal_secret(account: str, secret: str) -> bytes:
    key = hashlib.sha256(account.encode("utf-8")).digest()
    data = secret.encode("utf-8")
    sealed = bytes(byte ^ key[index % len(key)] for index, byte in enumerate(data))
    return base64.b64encode(sealed)


def unseal_secret(account: str, sealed_secret: bytes | str | None) -> str:
    if not sealed_secret:
        return ""
    raw = base64.b64decode(sealed_secret)
    key = hashlib.sha256(account.encode("utf-8")).digest()
    data = bytes(byte ^ key[index % len(key)] for index, byte in enumerate(raw))
    return data.decode("utf-8")
