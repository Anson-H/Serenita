from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List

from backend.app.agent_runtime.context import AgentContext
from backend.app.agent_runtime.events import AgentEvent


@dataclass(frozen=True)
class AgentResult:
    agent_id: str
    output: Dict[str, Any]
    events: List[AgentEvent] = field(default_factory=list)


class BaseAgent:
    agent_id = "base"
    name = "Base Agent"
    supported_tasks: FrozenSet[str] = frozenset()

    def can_handle(self, task_type: str) -> bool:
        return task_type in self.supported_tasks

    def run(self, context: AgentContext) -> AgentResult:
        raise NotImplementedError
