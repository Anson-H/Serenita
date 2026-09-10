"""The shared vocabulary and partial-update contract for member history."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator

MEDICAL_HISTORY_FIELDS = {
    "past_medical_history": ("既往疾病史", "以前得过什么病，做过什么治疗？"),
    "surgical_trauma_history": ("手术外伤史", "做过手术或受过外伤吗？"),
    "allergy_history": ("过敏史", "有药物、食物或其他物质过敏或不适吗？请说明对象和反应。"),
    "transfusion_vaccination_history": ("输血接种史", "有输血或接种经历吗？"),
    "birth_occupational_history": ("出生与职业史", "可以说说出生、居住和工作经历吗？"),
    "lifestyle_history": ("生活史", "平时的生活和饮食怎么样？"),
    "family_history": ("家族病史", "家里有人得过相关疾病吗？"),
    "special_history": ("特殊史", "还有其他想补充的吗？"),
}
MedicalHistoryField = Literal[*MEDICAL_HISTORY_FIELDS]


class HistoryUpdateBase(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    @model_validator(mode="after")
    def require_changes(self):
        if not self.model_fields_set:
            raise ValueError("至少提交一项既往史。")
        return self


MedicalHistoryUpdate = create_model(
    "MedicalHistoryUpdate",
    __base__=HistoryUpdateBase,
    **{
        name: (str | None, Field(default=None, title=label, description=(
            f"{meaning}。省略此项时保留已保存的内容；提交文本时替换该项内容；提交 null、空字符串或仅含空白的字符串时清空该项。"
        )))
        for name, (label, meaning) in MEDICAL_HISTORY_FIELDS.items()
    },
)


def selected_history_fields(fields: list[str] | None) -> list[str]:
    if fields is None:
        return list(MEDICAL_HISTORY_FIELDS)
    if not fields or len(set(fields)) != len(fields) or any(name not in MEDICAL_HISTORY_FIELDS for name in fields):
        raise ValueError("既往史项目必须是非空、不重复的有效字段名列表。")
    return fields
