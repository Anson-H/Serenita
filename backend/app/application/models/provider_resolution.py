"""Resolve model connections in the caller's account scope."""
from urllib.parse import urlsplit

from backend.app.core.errors import raise_error
from backend.app.providers.compatible import CompatibleProvider
from backend.app.providers.default_registry import create_default_provider_registry
from backend.app.providers.registry import ProviderNotFoundError


def resolve_provider(provider_id, *, account_id=None, repository=None, registry=None, paths=None, transaction=None, official_service=None):
    if provider_id == "serenita":
        from backend.app.providers.serenita import SerenitaProvider
        return SerenitaProvider(account_id=account_id, paths=paths, official_service=official_service)
    registry = registry or create_default_provider_registry()
    try:
        return registry.get(provider_id)
    except ProviderNotFoundError:
        if provider_id.startswith("custom_"):
            if account_id is None:
                return CompatibleProvider(provider_id)
            row = (transaction.get_provider(provider_id=provider_id) if transaction is not None
                   else repository.get_provider(account_id, provider_id))
            if row:
                return CompatibleProvider(provider_id, row["provider_name"], row["api_url"])
        raise_error("missing", "NOT_FOUND", "模型服务不存在。")


def configured_provider_row(provider, row):
    if row is None:
        return None
    result = dict(row)
    result["is_configured"] = bool(result["api_url"] and (
        not provider.requires_api_key or result["encrypted_api_key"]
    ))
    return result


def provider_metadata(provider):
    return {
        "provider_id": provider.provider_id,
        "provider_name": provider.provider_name,
        "provider_kind": provider.provider_kind,
        "default_api_url": provider.default_api_url,
        "default_official_url": provider.default_official_url,
        "native_attachment_mime_types": sorted(provider.native_attachment_mime_types()),
    }


def validate_provider_url(value, *, optional=False):
    value = (value or "").strip().rstrip("/")
    if optional and not value:
        return None
    try:
        parsed = urlsplit(value)
        valid = parsed.scheme in {"http", "https"} and parsed.hostname and not (
            parsed.username or parsed.password or (not optional and (parsed.query or parsed.fragment))
        )
        parsed.port
    except ValueError:
        valid = False
    if not valid:
        raise_error("invalid_structure", "INVALID_PROVIDER_URL", "请填写有效的 HTTP 或 HTTPS 基础地址。")
    return value
