from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


ComposerSubmitShortcut = Literal["enter", "modifier_enter"]
BaseContextDisplayMode = Literal[
    "hidden",
    "every_step",
    "conversation_start",
    "turn_start",
]
VisibleContextType = Literal[
    "current_user_message",
    "conversation_history",
    "model_tool_request",
    "tool_observation",
    "compacted_summary",
]
ToolDisplayType = Literal["model_tool_request", "tool_call"]


class BaseContextDisplayModes(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system_prompt: BaseContextDisplayMode
    tool_catalog: BaseContextDisplayMode
    skill_catalog: BaseContextDisplayMode
    runtime_context: BaseContextDisplayMode


class ConversationPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")

    composer_submit_shortcut: ComposerSubmitShortcut
    base_context_display_modes: BaseContextDisplayModes
    is_context_window_usage_visible: bool
    is_related_content_visible: bool
    is_token_usage_visible: bool
    visible_context_types: list[VisibleContextType]
    tool_display_types: list[ToolDisplayType]

    @field_validator("visible_context_types", "tool_display_types")
    @classmethod
    def deduplicate_display_types(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))
