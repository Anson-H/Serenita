"""Deployment-owned model service settings, independent of account credentials."""
from dataclasses import dataclass
import os
from urllib.parse import urlsplit


@dataclass(frozen=True)
class ModelServiceConfig:
    official: bool
    official_url: str

    @classmethod
    def from_environment(cls):
        mode = os.environ.get("SERENITA_SERVICE_MODE", "self_hosted")
        if mode not in {"official", "self_hosted"}:
            raise ValueError("SERENITA_SERVICE_MODE must be official or self_hosted")
        url = os.environ.get("SERENITA_OFFICIAL_URL", "").strip().rstrip("/")
        if url:
            parsed = urlsplit(url)
            if (parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username
                    or parsed.password or parsed.query or parsed.fragment
                    or (parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"})):
                raise ValueError("SERENITA_OFFICIAL_URL must be HTTPS (HTTP is allowed for loopback testing)")
        return cls(mode == "official", url)
