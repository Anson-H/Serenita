from backend.app.agent_runtime.agents.base import AgentResult, BaseAgent


class ComprehensiveAnalysisAgent(BaseAgent):
    agent_id = "comprehensive_analysis"
    name = "Comprehensive Analysis Agent"
    supported_tasks = frozenset({"comprehensive_analysis"})

    def run(self, context):
        return AgentResult(
            agent_id=self.agent_id,
            output={
                "status": "not_implemented",
                "message": "Comprehensive analysis agent slot is ready.",
            },
            events=[],
        )
