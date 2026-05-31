from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass(frozen=True)
class AgentEvent:
    type: str
    payload: Dict[str, Any] = field(default_factory=dict)
