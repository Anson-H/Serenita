import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

from backend.app.storage.paths import app_paths
from backend.app.storage.sqlite import connect


IMAGE_FILE_MIME_TYPES = [
    "image/jpeg",
    "image/png",
    "image/heic",
    "image/webp",
]

AUDIO_FILE_MIME_TYPES = [
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp3",
    "audio/aiff",
    "audio/x-aiff",
    "audio/aac",
    "audio/ogg",
    "audio/flac",
    "audio/mp4",
    "audio/m4a",
    "audio/x-m4a",
]

VIDEO_FILE_MIME_TYPES = [
    "video/mp4",
    "video/mpeg",
    "video/mov",
    "video/quicktime",
    "video/webm",
]

NATIVE_DOCUMENT_FILE_MIME_TYPES = [
    "application/pdf",
]

LEGACY_UPLOAD_FILE_MIME_TYPES = [
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/msword",
    "application/vnd.ms-excel",
]

DOCUMENT_FILE_MIME_TYPES = [*NATIVE_DOCUMENT_FILE_MIME_TYPES, *LEGACY_UPLOAD_FILE_MIME_TYPES]

NATIVE_ATTACHMENT_MIME_TYPES = [*IMAGE_FILE_MIME_TYPES, *NATIVE_DOCUMENT_FILE_MIME_TYPES]
FULL_FILE_MIME_TYPES = [*IMAGE_FILE_MIME_TYPES, *DOCUMENT_FILE_MIME_TYPES]


@dataclass(frozen=True)
class ModelCapabilityProfile:
    supports_text: bool = True
    file_mime_types: list[str] = field(default_factory=list)
    thinking_modes: list[str] = field(default_factory=lambda: ["default"])
    supports_tool_calling: bool = False
    supports_json_output: bool = False
    context_window_tokens: Optional[int] = None
    max_output_tokens: Optional[int] = None


DEFAULT_CAPABILITY_PROFILE = ModelCapabilityProfile()

RICH_CHAT_CAPABILITY_PROFILE = ModelCapabilityProfile(
    supports_text=True,
    file_mime_types=NATIVE_ATTACHMENT_MIME_TYPES,
    thinking_modes=["default", "fast", "low", "medium", "high"],
    supports_tool_calling=True,
    supports_json_output=True,
)

MODEL_CAPABILITY_COLUMN_DEFINITIONS = {
    "thinking_modes": "TEXT NOT NULL DEFAULT 'default'",
    "supports_text": "INTEGER NOT NULL DEFAULT 1",
    "file_mime_types": "TEXT NOT NULL DEFAULT ''",
    "supports_tool_calling": "INTEGER NOT NULL DEFAULT 0",
    "supports_json_output": "INTEGER NOT NULL DEFAULT 0",
    "context_window_tokens": "INTEGER",
    "max_output_tokens": "INTEGER",
}

MODEL_TABLE_COLUMN_NAMES = [
    "model_id",
    "provider_id",
    "remote_model_id",
    "model_name",
    "created_at",
    "updated_at",
    *MODEL_CAPABILITY_COLUMN_DEFINITIONS.keys(),
]

MODEL_DEFAULT_SETTING_KEYS = ("chat", "title", "vision_parse", "compact")
LEGACY_MODEL_DEFAULT_SETTING_KEY_MAP = {
    "ocr": "vision_parse",
}


def create_models_table_sql() -> str:
    capability_columns = "\n                ".join(
        f"{name} {definition},"
        for name, definition in MODEL_CAPABILITY_COLUMN_DEFINITIONS.items()
    )
    return f"""
            CREATE TABLE IF NOT EXISTS models (
                model_id TEXT PRIMARY KEY,
                provider_id TEXT NOT NULL,
                remote_model_id TEXT NOT NULL,
                model_name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                {capability_columns}
                FOREIGN KEY (provider_id) REFERENCES model_providers(provider_id)
            )
            """


def create_model_default_settings_table_sql() -> str:
    allowed_keys = ", ".join(f"'{key}'" for key in MODEL_DEFAULT_SETTING_KEYS)
    return f"""
            CREATE TABLE IF NOT EXISTS model_default_settings (
                setting_key TEXT PRIMARY KEY,
                model_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                CHECK (setting_key IN ({allowed_keys})),
                FOREIGN KEY (model_id) REFERENCES models(model_id) ON DELETE SET NULL
            )
            """


def ensure_model_default_settings_table(connection) -> None:
    tables = {
        row["name"]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }
    if "model_default_settings" not in tables:
        connection.execute(create_model_default_settings_table_sql())
        return

    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(model_default_settings)").fetchall()
    }
    foreign_key_tables = {
        row["table"]
        for row in connection.execute("PRAGMA foreign_key_list(model_default_settings)").fetchall()
    }
    expected_columns = {"setting_key", "model_id", "created_at", "updated_at"}
    table_sql_row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'model_default_settings'"
    ).fetchone()
    table_sql = table_sql_row["sql"] if table_sql_row else ""
    has_current_keys = all(f"'{key}'" in table_sql for key in MODEL_DEFAULT_SETTING_KEYS)
    has_legacy_keys = any(f"'{key}'" in table_sql for key in LEGACY_MODEL_DEFAULT_SETTING_KEY_MAP)
    if (
        expected_columns.issubset(columns)
        and foreign_key_tables == {"models"}
        and has_current_keys
        and not has_legacy_keys
    ):
        return

    connection.execute("DROP TABLE IF EXISTS model_default_settings_before_rebuild")
    connection.execute("ALTER TABLE model_default_settings RENAME TO model_default_settings_before_rebuild")
    connection.execute(create_model_default_settings_table_sql())
    old_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(model_default_settings_before_rebuild)").fetchall()
    }
    if expected_columns.issubset(old_columns):
        _copy_model_default_settings_rows(connection)
    connection.execute("DROP TABLE model_default_settings_before_rebuild")


def _copy_model_default_settings_rows(connection) -> None:
    allowed_old_keys = tuple(
        dict.fromkeys((*MODEL_DEFAULT_SETTING_KEYS, *LEGACY_MODEL_DEFAULT_SETTING_KEY_MAP.keys()))
    )
    rows = connection.execute(
        f"""
        SELECT setting_key, model_id, created_at, updated_at
        FROM model_default_settings_before_rebuild
        WHERE setting_key IN ({", ".join("?" for _ in allowed_old_keys)})
        """,
        allowed_old_keys,
    ).fetchall()
    migrated_rows: dict[str, dict[str, Any]] = {}
    for row in rows:
        setting_key = LEGACY_MODEL_DEFAULT_SETTING_KEY_MAP.get(row["setting_key"], row["setting_key"])
        is_legacy_key = setting_key != row["setting_key"]
        existing_row = migrated_rows.get(setting_key)
        if existing_row and (is_legacy_key or not existing_row["is_legacy_key"]):
            continue
        migrated_rows[setting_key] = {
            "model_id": row["model_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "is_legacy_key": is_legacy_key,
        }

    for setting_key, row in migrated_rows.items():
        model_id = row["model_id"]
        if model_id is not None:
            model_exists = connection.execute(
                "SELECT 1 FROM models WHERE model_id = ?",
                (model_id,),
            ).fetchone()
            if not model_exists:
                model_id = None
        connection.execute(
            """
            INSERT OR REPLACE INTO model_default_settings (
                setting_key, model_id, created_at, updated_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (setting_key, model_id, row["created_at"], row["updated_at"]),
        )


def ensure_model_capability_columns(connection) -> None:
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(models)").fetchall()
    }
    for name, definition in MODEL_CAPABILITY_COLUMN_DEFINITIONS.items():
        if name not in columns:
            connection.execute(f"ALTER TABLE models ADD COLUMN {name} {definition}")
            columns.add(name)

    if "capabilities_json" in columns:
        _migrate_legacy_capabilities_json(connection)
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(models)").fetchall()
        }

    current_order = [
        row["name"]
        for row in connection.execute("PRAGMA table_info(models)").fetchall()
    ]
    if current_order != MODEL_TABLE_COLUMN_NAMES:
        _rebuild_models_table(connection, current_order)


def migrate_existing_account_model_capabilities(root: Optional[Path] = None) -> None:
    data_root = root or app_paths().root
    if not data_root.exists():
        return
    for account_root in data_root.iterdir():
        if not account_root.is_dir() or account_root.name == "all_users":
            continue
        config_db = account_root / "config" / "config.db"
        if not config_db.exists():
            continue
        with connect(config_db) as connection:
            _ensure_model_providers_table(connection)
            connection.execute(create_models_table_sql())
            ensure_model_capability_columns(connection)
            ensure_model_default_settings_table(connection)


def capability_response(profile: ModelCapabilityProfile) -> dict[str, Any]:
    return {
        "supports_text": profile.supports_text,
        "file_mime_types": profile.file_mime_types,
        "thinking_modes": profile.thinking_modes,
        "supports_tool_calling": profile.supports_tool_calling,
        "supports_json_output": profile.supports_json_output,
        "context_window_tokens": profile.context_window_tokens,
        "max_output_tokens": profile.max_output_tokens,
    }


def _ensure_model_providers_table(connection) -> None:
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


def capability_column_values(profile: ModelCapabilityProfile) -> tuple[Any, ...]:
    return (
        _serialize_list(profile.thinking_modes),
        1 if profile.supports_text else 0,
        _serialize_list(profile.file_mime_types),
        1 if profile.supports_tool_calling else 0,
        1 if profile.supports_json_output else 0,
        profile.context_window_tokens,
        profile.max_output_tokens,
    )


def profile_from_row(row) -> ModelCapabilityProfile:
    return ModelCapabilityProfile(
        supports_text=bool(row["supports_text"]),
        file_mime_types=_deserialize_list(row["file_mime_types"]),
        thinking_modes=_deserialize_list(row["thinking_modes"]) or ["default"],
        supports_tool_calling=bool(row["supports_tool_calling"]),
        supports_json_output=bool(row["supports_json_output"]),
        context_window_tokens=_optional_int(row["context_window_tokens"]),
        max_output_tokens=_optional_int(row["max_output_tokens"]),
    )


def profile_from_mapping(
    payload: Optional[dict[str, Any]],
    fallback: ModelCapabilityProfile = DEFAULT_CAPABILITY_PROFILE,
) -> ModelCapabilityProfile:
    if not payload:
        return fallback
    file_mime_types = _list_value(payload.get("file_mime_types"), fallback.file_mime_types)
    if not file_mime_types and _bool_value(payload, "supports_vision", "vision", fallback=False):
        file_mime_types = list(IMAGE_FILE_MIME_TYPES)
    return ModelCapabilityProfile(
        supports_text=_bool_value(payload, "supports_text", "text", fallback=fallback.supports_text),
        file_mime_types=file_mime_types,
        thinking_modes=_list_value(payload.get("thinking_modes"), fallback.thinking_modes) or ["default"],
        supports_tool_calling=_bool_value(
            payload,
            "supports_tool_calling",
            "tool_calling",
            fallback=fallback.supports_tool_calling,
        ),
        supports_json_output=_bool_value(
            payload,
            "supports_json_output",
            "json_output",
            fallback=fallback.supports_json_output,
        ),
        context_window_tokens=_optional_int(payload.get("context_window_tokens", fallback.context_window_tokens)),
        max_output_tokens=_optional_int(payload.get("max_output_tokens", fallback.max_output_tokens)),
    )


def profile_from_split_values(
    *,
    fallback: ModelCapabilityProfile,
    supports_text: Optional[bool] = None,
    file_mime_types: Optional[list[str]] = None,
    thinking_modes: Optional[list[str]] = None,
    supports_tool_calling: Optional[bool] = None,
    supports_json_output: Optional[bool] = None,
    context_window_tokens: Optional[int] = None,
    max_output_tokens: Optional[int] = None,
) -> ModelCapabilityProfile:
    base = fallback
    return ModelCapabilityProfile(
        supports_text=base.supports_text if supports_text is None else supports_text,
        file_mime_types=base.file_mime_types if file_mime_types is None else _list_value(file_mime_types, []),
        thinking_modes=base.thinking_modes if thinking_modes is None else (_list_value(thinking_modes, []) or ["default"]),
        supports_tool_calling=base.supports_tool_calling if supports_tool_calling is None else supports_tool_calling,
        supports_json_output=base.supports_json_output if supports_json_output is None else supports_json_output,
        context_window_tokens=base.context_window_tokens if context_window_tokens is None else context_window_tokens,
        max_output_tokens=base.max_output_tokens if max_output_tokens is None else max_output_tokens,
    )


def _migrate_legacy_capabilities_json(connection) -> None:
    rows = connection.execute("SELECT model_id, capabilities_json FROM models").fetchall()
    for row in rows:
        try:
            payload = json.loads(row["capabilities_json"] or "{}")
        except json.JSONDecodeError:
            payload = {}
        profile = profile_from_mapping(payload, DEFAULT_CAPABILITY_PROFILE)
        connection.execute(
            """
            UPDATE models
            SET thinking_modes = ?, supports_text = ?, file_mime_types = ?,
                supports_tool_calling = ?, supports_json_output = ?,
                context_window_tokens = ?, max_output_tokens = ?
            WHERE model_id = ?
            """,
            (*capability_column_values(profile), row["model_id"]),
        )


def _rebuild_models_table(connection, current_order: list[str]) -> None:
    default_settings = _model_default_settings_snapshot(connection)
    connection.execute("ALTER TABLE models RENAME TO models_before_rebuild")
    connection.execute(
        """
        INSERT OR IGNORE INTO model_providers (
            provider_id, provider_name, base_url, configured, default_provider, created_at, updated_at
        )
        SELECT DISTINCT provider_id, provider_id, '', 0, 0,
            '1970-01-01T00:00:00+00:00',
            '1970-01-01T00:00:00+00:00'
        FROM models_before_rebuild
        """
    )
    connection.execute(create_models_table_sql())
    column_names = [name for name in MODEL_TABLE_COLUMN_NAMES if name in current_order]
    columns_csv = ", ".join(column_names)
    connection.execute(
        f"""
        INSERT INTO models ({columns_csv})
        SELECT {columns_csv} FROM models_before_rebuild
        """
    )
    connection.execute("DROP TABLE models_before_rebuild")
    if default_settings:
        ensure_model_default_settings_table(connection)
        for setting_key, model_id, created_at, updated_at in default_settings:
            connection.execute(
                """
                INSERT OR REPLACE INTO model_default_settings (
                    setting_key, model_id, created_at, updated_at
                )
                VALUES (
                    ?,
                    CASE
                        WHEN ? IS NOT NULL
                        AND EXISTS (SELECT 1 FROM models WHERE model_id = ?)
                        THEN ?
                        ELSE NULL
                    END,
                    ?,
                    ?
                )
                """,
                (setting_key, model_id, model_id, model_id, created_at, updated_at),
            )


def _model_default_settings_snapshot(connection) -> list[tuple[str, Optional[str], str, str]]:
    tables = {
        row["name"]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }
    if "model_default_settings" not in tables:
        return []
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(model_default_settings)").fetchall()
    }
    expected_columns = {"setting_key", "model_id", "created_at", "updated_at"}
    if not expected_columns.issubset(columns):
        return []
    rows = connection.execute(
        """
        SELECT setting_key, model_id, created_at, updated_at
        FROM model_default_settings
        WHERE setting_key IN ({})
        """.format(", ".join("?" for _ in MODEL_DEFAULT_SETTING_KEYS)),
        MODEL_DEFAULT_SETTING_KEYS,
    ).fetchall()
    return [
        (row["setting_key"], row["model_id"], row["created_at"], row["updated_at"])
        for row in rows
    ]


def _serialize_list(values: Iterable[str]) -> str:
    return "\n".join(_list_value(list(values), []))


def _deserialize_list(value: Any) -> list[str]:
    if not isinstance(value, str) or not value:
        return []
    return _list_value(value.splitlines(), [])


def _list_value(value: Any, fallback: list[str]) -> list[str]:
    if not isinstance(value, list):
        return list(fallback)
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _bool_value(payload: dict[str, Any], *keys: str, fallback: bool) -> bool:
    for key in keys:
        if key in payload and isinstance(payload[key], bool):
            return payload[key]
    return fallback


def _optional_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    return None
