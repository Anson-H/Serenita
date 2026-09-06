from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass(frozen=True)
class AgentEvent:
    type: str
    payload: Dict[str, Any] = field(default_factory=dict)


def visible_workflow_event(value: Any) -> dict[str, str] | None:
    """Validate one real workflow event without replacing its visible content."""
    if not isinstance(value, dict):
        return None
    stage = str(value.get("stage") or "")
    status = str(value.get("status") or "")
    if stage not in {
        "reasoning",
        "tool",
        "content",
        "action",
    }:
        return None
    label = str(value.get("label") or "").strip()
    if status not in {"started", "completed", "failed", "interrupted"} or not label:
        return None
    result = {"stage": stage, "status": status, "label": label}
    kind = str(value.get("kind") or "")
    if kind == "evidence_compaction":
        result["kind"] = kind
    detail = str(value.get("detail") or "").strip()
    if detail:
        result["detail"] = detail
    return result


