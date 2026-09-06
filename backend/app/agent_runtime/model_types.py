from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any, Iterable


@dataclass(frozen=True)
class ToolSchema:
    """One model-visible function contract."""

    name: str
    description: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    order: int | None = None
    kind: str = "application"

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("工具 schema 名称不能为空。")
        if not isinstance(self.parameters, dict):
            raise TypeError("工具 schema 参数必须是 JSON 对象。")

    def as_dict(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": dict(self.parameters),
            },
        }

    @classmethod
    def from_catalog_entry(
        cls, value: dict[str, Any], *, kind: str = "application"
    ) -> "ToolSchema":
        return cls(
            name=str(value["name"]),
            description=str(value.get("description") or ""),
            parameters=dict(value["input_schema"]),
            order=(
                int(value["order"])
                if isinstance(value.get("order"), int)
                and not isinstance(value.get("order"), bool)
                else None
            ),
            kind=kind,
        )


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.name.strip():
            raise ValueError("工具调用 ID 和名称不能为空。")
        if not isinstance(self.arguments, dict):
            raise TypeError("工具调用参数必须是 JSON 对象。")

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.name,
                "arguments": json.dumps(
                    self.arguments,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            },
        }


@dataclass(frozen=True)
class ToolCallDelta:
    index: int
    id: str = ""
    name_delta: str = ""
    arguments_delta: str = ""


@dataclass(frozen=True)
class PromptAssembly:
    system: str
    tools: tuple[ToolSchema, ...] = ()
    context_sections: tuple["PromptContextSection", ...] = ()


@dataclass(frozen=True)
class PromptContextSection:
    """One truthful, user-visible section of a model request's system context."""

    context_type: str
    label: str
    content: str

    def __post_init__(self) -> None:
        if not self.context_type.strip() or not self.label.strip():
            raise ValueError("Prompt context type and label must not be empty.")
        if not self.content.strip():
            raise ValueError("Prompt context content must not be empty.")


@dataclass(frozen=True)
class ModelRequest:
    system: str
    messages: tuple[dict[str, Any], ...]
    tools: tuple[ToolSchema, ...] = ()
    context_sections: tuple[PromptContextSection, ...] = ()
    tool_choice: str | dict[str, Any] | None = "auto"
    model_config: dict[str, Any] = field(default_factory=dict)
    transport_mode: str = "native"

    @classmethod
    def build(
        cls,
        *,
        system: str,
        messages: Iterable[dict[str, Any]],
        tools: Iterable[ToolSchema] = (),
        context_sections: Iterable[PromptContextSection] = (),
        tool_choice: str | dict[str, Any] | None = "auto",
        model_config: dict[str, Any] | None = None,
        transport_mode: str = "native",
    ) -> "ModelRequest":
        normalized_system = str(system or "")
        normalized_context_sections = tuple(context_sections)
        if normalized_context_sections:
            section_system = "\n\n".join(
                section.content for section in normalized_context_sections
            )
            if section_system != normalized_system:
                raise ValueError(
                    "Prompt context sections must exactly reconstruct the system prompt."
                )
        return cls(
            system=normalized_system,
            messages=tuple(dict(item) for item in messages),
            tools=tuple(tools),
            context_sections=normalized_context_sections,
            tool_choice=tool_choice,
            model_config=dict(model_config or {}),
            transport_mode=transport_mode,
        )

    def canonical_dict(self) -> dict[str, Any]:
        return {
            "system": self.system,
            "messages": [dict(item) for item in self.messages],
            "tools": [item.as_dict() for item in self.tools],
            "tool_choice": self.tool_choice if self.tools else None,
            "model_config": dict(self.model_config),
            "transport_mode": self.transport_mode,
        }


@dataclass(frozen=True)
class AssistantModelOutput:
    content: str = ""
    reasoning: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    usage: dict[str, Any] = field(default_factory=dict)
    stop_reason: str = "end_turn"
    raw_content: str = ""

@dataclass(frozen=True)
class ModelStreamChunk:
    content_delta: str = ""
    reasoning_delta: str = ""
    tool_call_deltas: tuple[ToolCallDelta, ...] = ()
    usage: dict[str, Any] = field(default_factory=dict)
    stop_reason: str | None = None
    raw_content_delta: str = ""
