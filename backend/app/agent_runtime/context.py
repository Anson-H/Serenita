from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class AgentContext:
    account: str
    task_type: str
    input_text: str = ""
    session_id: Optional[str] = None
    model_id: Optional[str] = None
    resources: List[Dict[str, Any]] = field(default_factory=list)
    memory: Dict[str, Any] = field(default_factory=dict)
