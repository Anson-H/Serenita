from dataclasses import dataclass, field
from typing import Any, Callable, Dict


@dataclass(frozen=True)
class ToolResult:
    name: str
    output: Dict[str, Any] = field(default_factory=dict)
    effects: Dict[str, Any] = field(default_factory=dict)
    # Paginated tools return one immutable base output plus page fragments. The
    # Harness merges every fragment before it persists or exposes an
    # Observation, so logical pagination never becomes another Agent loop.
    logical_pages: tuple[Dict[str, Any], ...] = field(default_factory=tuple)
    # Only read tools provide this continuation. It retains the exact query
    # and storage cursor outside model context and is never serialized.
    next_page: Callable[[], "ToolResult"] | None = field(default=None, repr=False, compare=False)


class Tool:
    name = "tool"
    description = ""
    # ``direct`` tools are visible to the model from the first agent step.
    # ``skill`` tools remain available only after a loaded Skill allows them.
    model_exposure = "skill"
    bind_conversation = False
    input_schema: Dict[str, Any] = {
        "type": "object",
        "additionalProperties": True,
    }

    def input_schema_for_context(self, context: Any) -> Dict[str, Any]:
        """Return the model-visible schema for the current trusted runtime context."""

        return dict(self.input_schema)

    def validation_error(
        self,
        arguments: Dict[str, Any],
        error: Exception,
        *,
        context: Any,
    ) -> tuple[str, str]:
        """Map a schema failure to a capability-specific Observation."""

        return "TOOL_ARGUMENTS_INVALID", str(error) or "工具参数无效。"

    def invalid_repetition_key(
        self, arguments: Dict[str, Any], *, context: Any
    ) -> str | None:
        """Group semantically equivalent invalid calls before schema validation."""

        return None

    def bind_runtime_arguments(
        self,
        arguments: Dict[str, Any],
        *,
        context: Any,
        observations: list[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Add trusted runtime metadata after model arguments are validated."""

        bound = dict(arguments)
        bound["account_id"] = context.account_id
        if self.bind_conversation:
            bound["model_id"] = getattr(context, "model_id", None)
            bound["session_id"] = context.session_id
            bound["turn_id"] = context.turn_id
            bound["source_message_id"] = context.memory.get("current_message_id")
            bound["visible_message_ids"] = list(
                context.memory.get("visible_message_ids") or []
            )
            bound["visible_attachments"] = dict(
                context.memory.get("visible_attachments") or {}
            )
        return bound

    def run(self, arguments: Dict[str, Any]) -> ToolResult:
        raise NotImplementedError
