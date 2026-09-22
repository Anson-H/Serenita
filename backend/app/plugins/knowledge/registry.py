from pathlib import Path

from backend.app.agent_runtime.skills.loader import discover_skills
from backend.app.application.knowledge_service import KnowledgeService
from backend.app.plugins.knowledge.tools import ReadKnowledgeFileTool, SearchKnowledgeTool


PLUGIN_ID = "knowledge"


def build_skills():
    return discover_skills(Path(__file__).parent / "skills")


def build_tools(*, runtime_context):
    return [SearchKnowledgeTool(runtime_context), ReadKnowledgeFileTool(runtime_context)]


def resolve_model_resource(*, runtime_context, reference):
    if reference.get("resource_type") not in {"knowledge_text", "knowledge_pdf"}:
        return None
    if runtime_context.cancellation_token:
        runtime_context.cancellation_token.raise_if_cancelled()
    service = runtime_context.service(PLUGIN_ID, KnowledgeService)
    return service.model_resource(runtime_context.account_id, reference)
