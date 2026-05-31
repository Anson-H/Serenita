from backend.app.agent_runtime.agents.comprehensive_analysis_agent import ComprehensiveAnalysisAgent
from backend.app.agent_runtime.agents.lifestyle_agent import LifestyleAdviceAgent
from backend.app.agent_runtime.agents.report_analysis_agent import ReportAnalysisAgent


def build_default_agents():
    return [
        ReportAnalysisAgent(),
        ComprehensiveAnalysisAgent(),
        LifestyleAdviceAgent(),
    ]
