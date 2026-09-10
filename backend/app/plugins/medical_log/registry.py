from pathlib import Path

from backend.app.agent_runtime.skills.loader import discover_skills
from backend.app.plugins.medical_log.resources import resolve_resource_state as resolve_resource_state
from backend.app.plugins.medical_log.tools import (
    CreateMedicalLogTool,
    DeleteMedicalLogTool,
    ReadMedicalLogTool,
    UpdateMedicalLogTool,
)

PLUGIN_ID = "medical_log"


def build_skills():
    return discover_skills(Path(__file__).parent / "skills")


def build_tools(*, runtime_context):
    if not runtime_context.member_id:
        return []
    return [cls(runtime_context) for cls in (ReadMedicalLogTool, CreateMedicalLogTool, UpdateMedicalLogTool, DeleteMedicalLogTool)]
