import hashlib
import hmac
import secrets

_SCRYPT_N = 1 << 14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32
_SCRYPT_PREFIX = "scrypt"


def hash_secret(secret: str) -> str:
    """Return a salted, deliberately expensive password hash."""

    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        secret.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )
    return "$".join(
        (
            _SCRYPT_PREFIX,
            str(_SCRYPT_N),
            str(_SCRYPT_R),
            str(_SCRYPT_P),
            salt.hex(),
            digest.hex(),
        )
    )


def verify_secret(secret: str, encoded: str) -> bool:
    if not encoded.startswith(f"{_SCRYPT_PREFIX}$"):
        return False

    try:
        prefix, n_raw, r_raw, p_raw, salt_raw, expected_raw = encoded.split("$", 5)
        n, r, p = int(n_raw), int(r_raw), int(p_raw)
        salt = bytes.fromhex(salt_raw)
        expected = bytes.fromhex(expected_raw)
    except (TypeError, ValueError):
        return False

    # Never let parameters read from local storage request unbounded work.
    if (
        prefix != _SCRYPT_PREFIX
        or (n, r, p) != (_SCRYPT_N, _SCRYPT_R, _SCRYPT_P)
        or len(salt) != 16
        or len(expected) != _SCRYPT_DKLEN
    ):
        return False

    actual = hashlib.scrypt(
        secret.encode("utf-8"),
        salt=salt,
        n=n,
        r=r,
        p=p,
        dklen=len(expected),
    )
    return hmac.compare_digest(actual, expected)
