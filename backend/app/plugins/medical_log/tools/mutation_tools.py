from backend.app.plugins.medical_log.tools.base import MedicalLogTool
from backend.app.plugins.medical_log.tools.parameters import FIELDS, LOG_ID


class CreateMedicalLogTool(MedicalLogTool):
    name = "create_log"
    description = "为当前成员创建健康日记，返回创建结果。"
    input_schema = {"type": "object", "properties": FIELDS, "required": ["recorded_on", "title", "content"], "additionalProperties": False}


class UpdateMedicalLogTool(MedicalLogTool):
    name = "update_log"
    description = "更新当前成员的一条健康日记，返回更新后的健康日记。"
    input_schema = {"type": "object", "properties": {"medical_log_id": {**LOG_ID, "description": LOG_ID["description"] + "必填；此外至少提交日期、标题或正文中的一项，任一字段无效整次失败。"}, **FIELDS}, "required": ["medical_log_id"], "minProperties": 2, "additionalProperties": False}


class DeleteMedicalLogTool(MedicalLogTool):
    name = "delete_log"
    description = "删除当前成员的一条健康日记，返回删除结果。"
    input_schema = {"type": "object", "properties": {"medical_log_id": LOG_ID}, "required": ["medical_log_id"], "additionalProperties": False}
