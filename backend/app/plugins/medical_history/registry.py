from backend.app.plugins.medical_history.tools import (
    ReadMedicalHistoryTool,
    UpdateMedicalHistoryTool,
)

PLUGIN_ID = "medical_history"


def build_skills():
    return []


def build_tools(*, runtime_context):
    if not runtime_context.member_id:
        return []
    return [ReadMedicalHistoryTool(runtime_context), UpdateMedicalHistoryTool(runtime_context)]
