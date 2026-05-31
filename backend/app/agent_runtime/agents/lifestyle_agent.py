from backend.app.agent_runtime.agents.base import AgentResult, BaseAgent


class LifestyleAdviceAgent(BaseAgent):
    agent_id = "lifestyle_advice"
    name = "Lifestyle Advice Agent"
    supported_tasks = frozenset({"lifestyle_advice"})

    def run(self, context):
        return AgentResult(
            agent_id=self.agent_id,
            output={
                "status": "not_implemented",
                "message": "Lifestyle advice agent slot is ready.",
            },
            events=[],
        )
