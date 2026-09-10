from backend.app.agent_runtime.tools.base import ToolResult
from backend.app.plugins.medical_history.tools.base import MedicalHistoryTool
from backend.app.schemas.medical_history import MedicalHistoryUpdate


class UpdateMedicalHistoryTool(MedicalHistoryTool):
    name = "update_history"
    description = "更新当前成员的既往史，返回保存结果。"
    input_schema = {**MedicalHistoryUpdate.model_json_schema(), "minProperties": 1}

    def run(self, arguments):
        return ToolResult(name=self.name, output=self.service.update(self.account_id, self.member_id, arguments))
