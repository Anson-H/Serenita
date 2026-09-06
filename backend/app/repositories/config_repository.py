from __future__ import annotations

from typing import Any, Mapping

from backend.app.storage.config_database import initialize_config_database
from backend.app.storage.paths import AppPaths, app_paths
from backend.app.storage.sqlite import UnsupportedSchemaError, connect


BASE_CONTEXT_COLUMNS = {
    "system_prompt": "system_prompt_display_mode",
    "tool_catalog": "tool_catalog_display_mode",
    "skill_catalog": "skill_catalog_display_mode",
    "runtime_context": "runtime_context_display_mode",
}
CONTEXT_DISPLAY_COLUMNS = {
    "current_user_message": "is_current_user_message_visible",
    "conversation_history": "is_conversation_history_visible",
    "model_tool_request": "is_context_model_tool_request_visible",
    "tool_observation": "is_tool_observation_visible",
    "compacted_summary": "is_compacted_summary_visible",
}
TOOL_DISPLAY_COLUMNS = {
    "model_tool_request": "is_execution_model_tool_request_visible",
    "tool_call": "is_tool_call_visible",
}
DISPLAY_MODES = {"hidden", "every_step", "conversation_start", "turn_start"}
COMPOSER_SUBMIT_SHORTCUTS = {"enter", "modifier_enter"}


class ConfigRepository:
    """Account-isolated configuration stored in the operator's settings.db."""

    def __init__(self, *, paths: AppPaths | None = None) -> None:
        self.paths = paths or app_paths()

    def _path(self, account_id: str):
        return self.paths.config_db(account_id)

    def _initialize(self, account_id: str) -> None:
        initialize_config_database(account_id, self.paths)

    @staticmethod
    def _conversation_preferences_from_row(row) -> dict[str, Any]:
        if row is None or int(row["singleton_id"]) != 1:
            raise UnsupportedSchemaError(
                "UNSUPPORTED_SCHEMA: conversation preferences are not current."
            )
        return {
            "composer_submit_shortcut": str(row["composer_submit_shortcut"]),
            "base_context_display_modes": {
                context_type: str(row[column])
                for context_type, column in BASE_CONTEXT_COLUMNS.items()
            },
            "is_context_window_usage_visible": bool(
                row["is_context_window_usage_visible"]
            ),
            "is_related_content_visible": bool(row["is_related_content_visible"]),
            "is_token_usage_visible": bool(row["is_token_usage_visible"]),
            "visible_context_types": [
                context_type
                for context_type, column in CONTEXT_DISPLAY_COLUMNS.items()
                if bool(row[column])
            ],
            "tool_display_types": [
                display_type
                for display_type, column in TOOL_DISPLAY_COLUMNS.items()
                if bool(row[column])
            ],
        }

    def conversation_preferences(self, account_id: str) -> dict[str, Any]:
        self._initialize(account_id)
        with connect(self._path(account_id)) as connection:
            row = connection.execute(
                "SELECT * FROM conversation_preferences WHERE singleton_id = 1"
            ).fetchone()
        return self._conversation_preferences_from_row(row)

    def replace_conversation_preferences(
        self,
        account_id: str,
        *,
        composer_submit_shortcut: str,
        base_context_display_modes: Mapping[str, str],
        is_context_window_usage_visible: bool,
        is_related_content_visible: bool,
        is_token_usage_visible: bool,
        visible_context_types: list[str],
        tool_display_types: list[str],
    ) -> dict[str, Any]:
        self._initialize(account_id)
        if composer_submit_shortcut not in COMPOSER_SUBMIT_SHORTCUTS:
            raise ValueError("不支持的发送快捷键。")
        if set(base_context_display_modes) != set(BASE_CONTEXT_COLUMNS):
            raise ValueError("系统与能力显示设置不完整。")
        if any(mode not in DISPLAY_MODES for mode in base_context_display_modes.values()):
            raise ValueError("不支持的系统与能力显示频率。")
        visible_context_type_set = set(visible_context_types)
        if not visible_context_type_set.issubset(CONTEXT_DISPLAY_COLUMNS):
            raise ValueError("不支持的输入追溯显示类型。")
        tool_display_type_set = set(tool_display_types)
        if not tool_display_type_set.issubset(TOOL_DISPLAY_COLUMNS):
            raise ValueError("不支持的工具记录显示类型。")

        values: dict[str, Any] = {
            "composer_submit_shortcut": composer_submit_shortcut,
            "is_context_window_usage_visible": int(
                is_context_window_usage_visible
            ),
            "is_related_content_visible": int(is_related_content_visible),
            "is_token_usage_visible": int(is_token_usage_visible),
        }
        values.update(
            {
                column: base_context_display_modes[context_type]
                for context_type, column in BASE_CONTEXT_COLUMNS.items()
            }
        )
        values.update(
            {
                column: int(context_type in visible_context_type_set)
                for context_type, column in CONTEXT_DISPLAY_COLUMNS.items()
            }
        )
        values.update(
            {
                column: int(display_type in tool_display_type_set)
                for display_type, column in TOOL_DISPLAY_COLUMNS.items()
            }
        )
        assignments = ", ".join(f"{column} = ?" for column in values)
        with connect(self._path(account_id)) as connection:
            connection.execute(
                f"UPDATE conversation_preferences SET {assignments} WHERE singleton_id = 1",
                tuple(values.values()),
            )
            row = connection.execute(
                "SELECT * FROM conversation_preferences WHERE singleton_id = 1"
            ).fetchone()
        return self._conversation_preferences_from_row(row)
