from typing import Dict, Iterable

from backend.app.agent_runtime.agents.base import AgentResult, BaseAgent
from backend.app.agent_runtime.context import AgentContext


class AgentNotFoundError(ValueError):
    pass


class AgentOrchestrator:
    def __init__(self, agents: Iterable[BaseAgent] = ()):
        self._agents: Dict[str, BaseAgent] = {}
        for agent in agents:
            self.register_agent(agent)

    def register_agent(self, agent: BaseAgent) -> None:
        self._agents[agent.agent_id] = agent

    def run(self, context: AgentContext) -> AgentResult:
        for agent in self._agents.values():
            if agent.can_handle(context.task_type):
                return agent.run(context)
        raise AgentNotFoundError("No agent registered for task type: %s" % context.task_type)
