from backend.app.storage.crypto import sha256_text


def hash_secret(secret: str) -> str:
    return sha256_text(secret)
