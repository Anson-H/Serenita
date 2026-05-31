from backend.app.agent_runtime.agents.base import AgentResult, BaseAgent


class ReportAnalysisAgent(BaseAgent):
    agent_id = "report_analysis"
    name = "Report Analysis Agent"
    supported_tasks = frozenset({"report_analysis"})

    def run(self, context):
        return AgentResult(
            agent_id=self.agent_id,
            output={
                "status": "not_implemented",
                "message": "Report analysis agent slot is ready.",
            },
            events=[],
        )
