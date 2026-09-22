from backend.app.agent_runtime.tools.base import Tool
from backend.app.application.medical_history_service import MedicalHistoryService


class MedicalHistoryTool(Tool):
    model_exposure = "direct"

    def __init__(self, context):
        self.account_id = context.account_id
        self.member_id = context.member_id
        self.service = context.service("medical_history", MedicalHistoryService)

    def bind_runtime_arguments(self, arguments, *, context, observations):
        if context.account_id != self.account_id or context.member_id != self.member_id:
            raise PermissionError("既往史工具与当前任务的成员不一致。")
        return dict(arguments)
