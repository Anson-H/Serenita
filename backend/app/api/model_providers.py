from dataclasses import asdict
from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from backend.app.api.auth import CurrentUser, now_iso, raise_error, require_current_user
from backend.app.bootstrap import create_default_provider_registry
from backend.app.model_capabilities import (
    DEFAULT_CAPABILITY_PROFILE,
    MODEL_DEFAULT_SETTING_KEYS,
    ModelCapabilityProfile,
    RICH_CHAT_CAPABILITY_PROFILE,
    capability_column_values,
    capability_response,
    create_models_table_sql,
    ensure_model_capability_columns,
    ensure_model_default_settings_table,
    profile_from_row,
    profile_from_split_values,
)
from backend.app.providers.base import ProviderModelListError
from backend.app.providers.registry import ProviderNotFoundError
from backend.app.storage.crypto import unseal_secret
from backend.app.storage.paths import app_paths
from backend.app.storage.sqlite import connect

router = APIRouter(prefix="/api", tags=["model-providers"])

BUILTIN_MODELS = {
    "openrouter": [
        {
            "remote_model_id": "openai/gpt-4.1-mini",
            "model_name": "GPT-4.1 Mini",
            "profile": RICH_CHAT_CAPABILITY_PROFILE,
        },
        {
            "remote_model_id": "anthropic/claude-sonnet-4.5",
            "model_name": "Claude Sonnet 4.5",
            "profile": RICH_CHAT_CAPABILITY_PROFILE,
        },
    ],
    "deepseek": [
        {
            "remote_model_id": "deepseek-chat",
            "model_name": "DeepSeek Chat",
            "profile": ModelCapabilityProfile(
                supports_text=True,
                file_mime_types=[],
                thinking_modes=["default"],
                supports_tool_calling=True,
                supports_json_output=True,
            ),
        },
        {
            "remote_model_id": "deepseek-reasoner",
            "model_name": "DeepSeek Reasoner",
            "profile": ModelCapabilityProfile(
                supports_text=True,
                file_mime_types=[],
                thinking_modes=["default", "high", "xhigh"],
                supports_tool_calling=True,
                supports_json_output=True,
            ),
        },
    ],
    "aliyun_bailian": [
        {
            "remote_model_id": "qwen-plus",
            "model_name": "Qwen Plus",
            "profile": ModelCapabilityProfile(
                supports_text=True,
                thinking_modes=["default", "high"],
                supports_tool_calling=True,
                supports_json_output=True,
            ),
        },
        {
            "remote_model_id": "qwen-max",
            "model_name": "Qwen Max",
            "profile": ModelCapabilityProfile(
                supports_text=True,
                supports_tool_calling=True,
                supports_json_output=True,
            ),
        },
    ],
}


class ModelProviderSaveRequest(BaseModel):
    provider_id: str
    base_url: Optional[str] = None
    official_url: Optional[str] = None
    api_key: Optional[str] = None
    default: bool = False


class ModelProviderPatchRequest(BaseModel):
    base_url: Optional[str] = None
    official_url: Optional[str] = None
    api_key: Optional[str] = None
    default: Optional[bool] = None


class ModelProviderTestRequest(BaseModel):
    base_url: Optional[str] = None
    api_key: Optional[str] = None


class AddModelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str
    remote_model_id: str
    model_name: Optional[str] = None
    supports_text: Optional[bool] = None
    file_mime_types: Optional[list[str]] = None
    thinking_modes: Optional[list[str]] = None
    supports_tool_calling: Optional[bool] = None
    supports_json_output: Optional[bool] = None
    context_window_tokens: Optional[int] = None
    max_output_tokens: Optional[int] = None


class ModelDefaultsPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chat: Optional[str] = None
    title: Optional[str] = None
    vision_parse: Optional[str] = None
    compact: Optional[str] = None


def _init_config_db(account: str) -> None:
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
            columns.add("api_key")
        if "official_url" not in columns:
            connection.execute("ALTER TABLE model_providers ADD COLUMN official_url TEXT")
            columns.add("official_url")
        if "key_info_data" in columns:
            for row in connection.execute(
                "SELECT provider_id, api_key, configured, key_info_data FROM model_providers"
            ).fetchall():
                if row["configured"] and not row["api_key"] and row["key_info_data"]:
                    connection.execute(
                        "UPDATE model_providers SET api_key = ? WHERE provider_id = ?",
                        (unseal_secret(account, row["key_info_data"]), row["provider_id"]),
                    )
            _clear_legacy_api_key_columns(connection)
        connection.execute(create_models_table_sql())
        ensure_model_capability_columns(connection)
        ensure_model_default_settings_table(connection)
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_models_provider_remote
            ON models(provider_id, remote_model_id)
            """
        )


def _registry_provider(provider_id: str):
    registry = create_default_provider_registry()
    try:
        return registry.get(provider_id)
    except ProviderNotFoundError:
        raise_error(404, "NOT_FOUND", "模型服务不存在。")


def _provider_row(account: str, provider_id: str):
    _init_config_db(account)
    with connect(app_paths().config_db(account)) as connection:
        return connection.execute(
            "SELECT * FROM model_providers WHERE provider_id = ?",
            (provider_id,),
        ).fetchone()


def _provider_summary(account: str, provider) -> dict[str, Any]:
    row = _provider_row(account, provider.provider_id)
    return {
        "provider_id": provider.provider_id,
        "provider_name": provider.display_name,
        "default_base_url": provider.default_base_url,
        "default_official_url": provider.default_official_url,
        "base_url": row["base_url"] if row else provider.default_base_url,
        "official_url": row["official_url"] if row and row["official_url"] is not None else provider.default_official_url,
        "api_key": _api_key_from_row(account, row),
        "configured": bool(row["configured"]) if row else False,
        "default": bool(row["default_provider"]) if row else False,
    }


def _api_key_from_row(account: str, row) -> str:
    if not row or not row["configured"]:
        return ""
    if row["api_key"]:
        return row["api_key"]
    if "key_info_data" in row.keys():
        return unseal_secret(account, row["key_info_data"])
    return ""


def _saved_api_key(account: str, provider_id: str) -> str:
    return _api_key_from_row(account, _provider_row(account, provider_id))


def _builtin_model(provider_id: str, remote_model_id: str) -> dict[str, Any] | None:
    for model in BUILTIN_MODELS.get(provider_id, []):
        if model["remote_model_id"] == remote_model_id:
            return model
    return None


def _model_payload_from_provider_model(model) -> dict[str, Any]:
    return {
        "remote_model_id": model.remote_model_id,
        "model_name": model.model_name,
        **capability_response(_provider_model_profile(model)),
    }


def default_model_for_account(account: str):
    _init_config_db(account)
    with connect(app_paths().config_db(account)) as connection:
        row = _default_model_row(connection, "chat")
    return _model_response(row) if row else None


def model_for_account(account: str, model_id: str):
    _init_config_db(account)
    with connect(app_paths().config_db(account)) as connection:
        row = connection.execute(
            "SELECT * FROM models WHERE model_id = ?",
            (model_id,),
        ).fetchone()
    return _model_response(row) if row else None


def _model_response(row) -> dict[str, Any]:
    profile = profile_from_row(row)
    return {
        "model_id": row["model_id"],
        "provider_id": row["provider_id"],
        "remote_model_id": row["remote_model_id"],
        "model_name": row["model_name"],
        **capability_response(profile),
    }


def _default_model_row(connection, setting_key: str):
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


def _set_model_default_in_connection(connection, setting_key: str, model_id: str | None) -> None:
    timestamp = now_iso()
    connection.execute(
        """
        INSERT INTO model_default_settings (setting_key, model_id, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(setting_key) DO UPDATE SET
            model_id = excluded.model_id,
            updated_at = excluded.updated_at
        """,
        (setting_key, model_id, timestamp, timestamp),
    )


def _clear_model_default_references(connection, model_id: str) -> None:
    timestamp = now_iso()
    connection.execute(
        """
        UPDATE model_default_settings
        SET model_id = NULL, updated_at = ?
        WHERE model_id = ?
        """,
        (timestamp, model_id),
    )


def _model_defaults_response(account: str) -> dict[str, Any]:
    _init_config_db(account)
    with connect(app_paths().config_db(account)) as connection:
        defaults = {}
        for setting_key in MODEL_DEFAULT_SETTING_KEYS:
            row = _default_model_row(connection, setting_key)
            defaults[setting_key] = _model_response(row) if row else None
    return {"defaults": defaults}


def _provider_model_profile(model) -> ModelCapabilityProfile:
    return ModelCapabilityProfile(
        supports_text=model.supports_text,
        file_mime_types=model.file_mime_types,
        thinking_modes=model.thinking_modes,
        supports_tool_calling=model.supports_tool_calling,
        supports_json_output=model.supports_json_output,
        context_window_tokens=model.context_window_tokens,
        max_output_tokens=model.max_output_tokens,
    )


@router.get("/model-providers")
def list_model_providers(user: CurrentUser = Depends(require_current_user)):
    registry = create_default_provider_registry()
    return {
        "providers": [
            _provider_summary(user.account, provider)
            for provider in registry._providers.values()
        ]
    }


@router.post("/model-providers")
def create_model_provider(
    payload: ModelProviderSaveRequest,
    user: CurrentUser = Depends(require_current_user),
):
    provider = _registry_provider(payload.provider_id)
    existing = _provider_row(user.account, provider.provider_id)
    api_key = (
        payload.api_key.strip()
        if payload.api_key is not None
        else _saved_api_key(user.account, provider.provider_id)
    )
    base_url = (
        payload.base_url
        if payload.base_url is not None
        else (existing["base_url"] if existing else provider.default_base_url)
    )
    official_url = (
        payload.official_url
        if payload.official_url is not None
        else (
            existing["official_url"]
            if existing and existing["official_url"] is not None
            else provider.default_official_url
        )
    )

    timestamp = now_iso()
    if payload.default:
        _clear_default_provider(user.account)
    with connect(app_paths().config_db(user.account)) as connection:
        connection.execute(
            """
            INSERT INTO model_providers (
                provider_id, provider_name, base_url, official_url, api_key, configured, default_provider,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(provider_id) DO UPDATE SET
                provider_name = excluded.provider_name,
                base_url = excluded.base_url,
                official_url = excluded.official_url,
                api_key = excluded.api_key,
                configured = excluded.configured,
                default_provider = excluded.default_provider,
                updated_at = excluded.updated_at
            """,
            (
                provider.provider_id,
                provider.display_name,
                base_url or provider.default_base_url,
                official_url,
                api_key,
                1 if api_key else 0,
                1 if payload.default else 0,
                timestamp,
                timestamp,
            ),
        )
    return _provider_summary(user.account, provider)


@router.patch("/model-providers/{provider_id}")
def update_model_provider(
    provider_id: str,
    payload: ModelProviderPatchRequest,
    user: CurrentUser = Depends(require_current_user),
):
    provider = _registry_provider(provider_id)
    existing = _provider_row(user.account, provider_id)
    if not existing:
        raise_error(404, "NOT_FOUND", "该模型服务尚未配置。")

    next_base_url = payload.base_url if payload.base_url is not None else existing["base_url"]
    next_official_url = (
        payload.official_url
        if payload.official_url is not None
        else (
            existing["official_url"]
            if existing["official_url"] is not None
            else provider.default_official_url
        )
    )
    next_default = bool(existing["default_provider"]) if payload.default is None else payload.default
    next_key = _saved_api_key(user.account, provider_id)
    if payload.api_key is not None:
        trimmed_key = payload.api_key.strip()
        next_key = trimmed_key
    if next_default:
        _clear_default_provider(user.account)

    timestamp = now_iso()
    with connect(app_paths().config_db(user.account)) as connection:
        connection.execute(
            """
            UPDATE model_providers
            SET base_url = ?, official_url = ?, api_key = ?, configured = ?, default_provider = ?, updated_at = ?
            WHERE provider_id = ?
            """,
            (
                next_base_url or provider.default_base_url,
                next_official_url,
                next_key,
                1 if next_key else 0,
                1 if next_default else 0,
                timestamp,
                provider_id,
            ),
        )
        _clear_legacy_api_key_columns(connection)
    return _provider_summary(user.account, provider)


def _clear_legacy_api_key_columns(connection) -> None:
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(model_providers)").fetchall()
    }
    legacy_columns = [
        column
        for column in ("account_md5", "key_md5", "key_info_md5", "key_info_data")
        if column in columns
    ]
    if legacy_columns:
        assignments = ", ".join(f"{column} = NULL" for column in legacy_columns)
        connection.execute(f"UPDATE model_providers SET {assignments}")


def _clear_default_provider(account: str) -> None:
    _init_config_db(account)
    with connect(app_paths().config_db(account)) as connection:
        connection.execute("UPDATE model_providers SET default_provider = 0")


def _raise_provider_test_error(message: str) -> None:
    if "认证失败" in message:
        raise_error(502, "PROVIDER_AUTH_FAILED", message)
    if "超时" in message:
        raise_error(504, "MODEL_TIMEOUT", message)
    raise_error(502, "MODEL_ERROR", message or "模型服务调用失败。")


@router.post("/model-providers/{provider_id}/test")
def test_model_provider(
    provider_id: str,
    payload: ModelProviderTestRequest,
    user: CurrentUser = Depends(require_current_user),
):
    provider = _registry_provider(provider_id)
    api_key = payload.api_key or _saved_api_key(user.account, provider_id)
    if not api_key:
        raise_error(422, "MODEL_NOT_CONFIGURED", "请先输入或保存 API key。")

    result = provider.test_connection(
        base_url=payload.base_url or provider.default_base_url,
        api_key=api_key,
    )
    if not result.reachable:
        _raise_provider_test_error(result.message)
    return asdict(result)


@router.get("/model-providers/{provider_id}/models")
def list_remote_models(provider_id: str, user: CurrentUser = Depends(require_current_user)):
    provider = _registry_provider(provider_id)
    row = _provider_row(user.account, provider_id)
    if not row or not row["configured"]:
        raise_error(422, "MODEL_NOT_CONFIGURED", "请先配置该模型服务。")
    api_key = _saved_api_key(user.account, provider_id)
    if not api_key:
        raise_error(422, "MODEL_NOT_CONFIGURED", "请先输入或保存 API key。")

    try:
        remote_models = provider.list_models(
            base_url=row["base_url"] or provider.default_base_url,
            api_key=api_key,
        )
    except ProviderModelListError as exc:
        _raise_provider_test_error(str(exc))

    return {
        "account": user.account,
        "provider_id": provider.provider_id,
        "models": [_model_payload_from_provider_model(model) for model in remote_models],
    }


@router.post("/models")
def add_model(payload: AddModelRequest, user: CurrentUser = Depends(require_current_user)):
    _registry_provider(payload.provider_id)
    provider_row = _provider_row(user.account, payload.provider_id)
    if not provider_row or not provider_row["configured"]:
        raise_error(422, "MODEL_NOT_CONFIGURED", "请先配置该模型服务。")

    remote_model = _builtin_model(payload.provider_id, payload.remote_model_id)
    fallback_profile = remote_model["profile"] if remote_model else DEFAULT_CAPABILITY_PROFILE
    model_profile = profile_from_split_values(
        fallback=fallback_profile,
        supports_text=payload.supports_text,
        file_mime_types=payload.file_mime_types,
        thinking_modes=payload.thinking_modes,
        supports_tool_calling=payload.supports_tool_calling,
        supports_json_output=payload.supports_json_output,
        context_window_tokens=payload.context_window_tokens,
        max_output_tokens=payload.max_output_tokens,
    )

    model_id = f"{payload.provider_id}:{payload.remote_model_id}"
    model_name = payload.model_name or (remote_model["model_name"] if remote_model else payload.remote_model_id)
    timestamp = now_iso()
    with connect(app_paths().config_db(user.account)) as connection:
        connection.execute(
            """
            INSERT INTO models (
                model_id, provider_id, remote_model_id, model_name,
                created_at, updated_at,
                thinking_modes, supports_text, file_mime_types,
                supports_tool_calling, supports_json_output,
                context_window_tokens, max_output_tokens
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(model_id) DO UPDATE SET
                model_name = excluded.model_name,
                updated_at = excluded.updated_at,
                thinking_modes = excluded.thinking_modes,
                supports_text = excluded.supports_text,
                file_mime_types = excluded.file_mime_types,
                supports_tool_calling = excluded.supports_tool_calling,
                supports_json_output = excluded.supports_json_output,
                context_window_tokens = excluded.context_window_tokens,
                max_output_tokens = excluded.max_output_tokens
            """,
            (
                model_id,
                payload.provider_id,
                payload.remote_model_id,
                model_name,
                timestamp,
                timestamp,
                *capability_column_values(model_profile),
            ),
        )
        row = connection.execute("SELECT * FROM models WHERE model_id = ?", (model_id,)).fetchone()
    return _model_response(row)


@router.get("/models")
def list_models(user: CurrentUser = Depends(require_current_user)):
    _init_config_db(user.account)
    with connect(app_paths().config_db(user.account)) as connection:
        rows = connection.execute("SELECT * FROM models ORDER BY created_at").fetchall()
    return {"models": [_model_response(row) for row in rows]}


@router.get("/model-defaults")
def list_model_defaults(user: CurrentUser = Depends(require_current_user)):
    return _model_defaults_response(user.account)


@router.patch("/model-defaults")
def update_model_defaults(
    payload: ModelDefaultsPatchRequest,
    user: CurrentUser = Depends(require_current_user),
):
    _init_config_db(user.account)
    updates = {
        setting_key: getattr(payload, setting_key)
        for setting_key in MODEL_DEFAULT_SETTING_KEYS
        if setting_key in payload.model_fields_set
    }
    with connect(app_paths().config_db(user.account)) as connection:
        for setting_key, model_id in updates.items():
            if model_id is not None:
                row = connection.execute(
                    "SELECT model_id FROM models WHERE model_id = ?",
                    (model_id,),
                ).fetchone()
                if not row:
                    raise_error(404, "MODEL_NOT_FOUND", "模型不存在或未添加。")
        for setting_key, model_id in updates.items():
            _set_model_default_in_connection(connection, setting_key, model_id)
    return _model_defaults_response(user.account)


@router.delete("/models/{model_id:path}")
def delete_model(model_id: str, user: CurrentUser = Depends(require_current_user)):
    _init_config_db(user.account)
    with connect(app_paths().config_db(user.account)) as connection:
        row = connection.execute(
            "SELECT * FROM models WHERE model_id = ?",
            (model_id,),
        ).fetchone()
        if not row:
            raise_error(404, "MODEL_NOT_FOUND", "模型不存在或未添加。")
        connection.execute("DELETE FROM models WHERE model_id = ?", (model_id,))
        _clear_model_default_references(connection, model_id)
    return {"model_id": model_id, "deleted": True}
