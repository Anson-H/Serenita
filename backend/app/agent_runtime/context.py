from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class AgentContext:
    account_id: str
    task_type: str
    member_id: Optional[str] = None
    input_text: str = ""
    session_id: Optional[str] = None
    model_id: Optional[str] = None
    resources: List[Dict[str, Any]] = field(default_factory=list)
    memory: Dict[str, Any] = field(default_factory=dict)
