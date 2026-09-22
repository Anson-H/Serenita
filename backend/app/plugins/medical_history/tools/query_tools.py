from backend.app.agent_runtime.tools.base import ToolResult
from backend.app.plugins.medical_history.tools.base import MedicalHistoryTool
from backend.app.schemas.medical_history import MEDICAL_HISTORY_FIELDS


class ReadMedicalHistoryTool(MedicalHistoryTool):
    name = "read_history"
    description = "读取当前成员的既往史，返回已保存内容。"
    input_schema = {
        "type": "object",
        "properties": {"fields": {
            "type": "array", "minItems": 1, "uniqueItems": True,
            "items": {"type": "string", "enum": list(MEDICAL_HISTORY_FIELDS)},
            "description": "要读取的既往史项目，可选择一项或多项。省略时读取全部项目；数组不能为空，项目不能重复，也不能传入 null。各项内容："
                + "；".join(f"{key}：{label}，{meaning}" for key, (label, meaning) in MEDICAL_HISTORY_FIELDS.items())
                + "。返回 member_id 和 history，每项内容包含 text 和 updated_at。member_id 表示资料所属的当前成员，更新时无需提交，也不能用作访问凭据。",
        }},
        "additionalProperties": False,
    }

    def run(self, arguments):
        return ToolResult(name=self.name, output=self.service.read(self.account_id, self.member_id, arguments.get("fields")))
