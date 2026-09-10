from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ReportType = Literal["检验报告", "检查报告", "病理报告", "手术报告", "门诊病历", "急诊病历", "其它医疗报告"]
FlagText = Literal["未标记", "正常", "异常", "偏高", "偏低"]

DETAILED_REPORT_CORE_FIELDS = frozenset(
    {
        "report_id",
        "report_type",
        "report_name",
        "report_time",
    }
)
DETAILED_REPORT_OPTIONAL_FIELDS = frozenset(
    {
        "institution_name",
        "lab_test_results",
        "examination_report",
        "pathology_report",
        "surgery_report",
        "outpatient_report",
        "emergency_report",
        "other_report",
    }
)
DETAILED_REPORT_SOURCE_FIELD = "sources"
DETAILED_REPORT_SELECTABLE_FIELDS = frozenset(
    DETAILED_REPORT_OPTIONAL_FIELDS | {DETAILED_REPORT_SOURCE_FIELD}
)


class ParsedLabResult(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    item_id: str = Field(
        min_length=1,
        max_length=128,
        description="检验指标的稳定唯一 ID。",
    )
    item_name_zh: str = Field(
        min_length=1,
        max_length=128,
        description="检验指标的规范中文名称。",
    )
    aliases: list[str] = Field(
        default_factory=list,
        description="原件中出现的其它指标名称。",
    )
    category_name: str = Field(
        min_length=1,
        max_length=64,
        description="检验指标所属的主分类名称。",
    )
    result_text: str = Field(
        min_length=1,
        description="检验结果原文，包含原件中的单位。",
    )
    reference_text: Optional[str] = Field(
        default=None,
        description="原件中的参考范围或参考说明。",
    )
    flag_text: FlagText = Field(
        default="未标记",
        description="检验结果状态，只能为未标记、正常、异常、偏高或偏低。",
    )

    @field_validator("aliases", mode="before")
    @classmethod
    def normalize_model_aliases(cls, value):
        """Normalize the two harmless shapes vision models commonly emit."""
        if value is None:
            return []
        if isinstance(value, str):
            stripped = value.strip()
            return [stripped] if stripped else []
        return value

    @field_validator("item_id", "item_name_zh", "category_name")
    @classmethod
    def require_non_blank_identifier_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("字段不能为空白")
        return normalized
    @field_validator("aliases")
    @classmethod
    def normalize_alias_values(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(alias.strip() for alias in value if alias.strip()))


class ParsedExaminationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    exam_name: str = Field(
        title="检查名称",
        min_length=1,
        max_length=255,
        description="检查项目名称。",
    )
    clinical_diagnosis: Optional[str] = Field(
        title="临床诊断",
        default=None,
        description="医疗报告记载的临床诊断。",
    )
    exam_method: Optional[str] = Field(
        title="检查方法",
        default=None,
        description="检查方法或技术。",
    )
    exam_findings: Optional[str] = Field(
        title="检查所见",
        default=None,
        description="检查所见原文。",
    )
    exam_diagnosis: Optional[str] = Field(
        title="检查诊断",
        default=None,
        description="检查结论或诊断原文。",
    )


class ParsedPathology(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    submitted_specimen: Optional[str] = Field(
        title="送检标本",
        default=None,
        description="送检标本说明。",
    )
    gross_examination: Optional[str] = Field(
        title="巨检",
        default=None,
        description="肉眼检查或大体所见。",
    )
    diagnosis: Optional[str] = Field(
        title="诊断",
        default=None,
        description="病理诊断原文。",
    )
    sampling_location: Optional[str] = Field(
        title="取材位置",
        default=None,
        description="取材或采样部位。",
    )


class ParsedSurgery(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    preoperative_diagnosis: Optional[str] = Field(
        title="术前诊断",
        default=None,
        description="术前诊断。",
    )
    intraoperative_diagnosis: Optional[str] = Field(
        title="术中诊断",
        default=None,
        description="术中诊断。",
    )
    anesthesia_method: Optional[str] = Field(
        title="麻醉方法",
        default=None,
        description="麻醉方式。",
    )
    started_at: Optional[str] = Field(
        title="开始时间",
        default=None,
        description="手术开始的本地时间。",
    )
    ended_at: Optional[str] = Field(
        title="结束时间",
        default=None,
        description="手术结束的本地时间。",
    )
    blood_transfusion: Optional[str] = Field(
        title="是否输血",
        default=None,
        description="输血情况。",
    )
    intraoperative_blood_loss: Optional[str] = Field(
        title="术中失血量",
        default=None,
        description="术中失血量。",
    )
    intraoperative_urine_output: Optional[str] = Field(
        title="术中尿量",
        default=None,
        description="术中尿量。",
    )
    intraoperative_transfusion: Optional[str] = Field(
        title="术中输血量",
        default=None,
        description="术中输血记录。",
    )
    intraoperative_infusion: Optional[str] = Field(
        title="术中输液量",
        default=None,
        description="术中输液记录。",
    )
    intraoperative_other_drugs: Optional[str] = Field(
        title="术中其他用药",
        default=None,
        description="术中其它用药记录。",
    )
    procedure_description: Optional[str] = Field(
        title="手术经过",
        default=None,
        description="手术经过原文。",
    )
    postoperative_vital_signs: Optional[str] = Field(
        title="术后生命体征",
        default=None,
        description="术后生命体征。",
    )


class ParsedOutpatientReport(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    chief_complaint: Optional[str] = Field(default=None, title="主诉", description="原件记载的主诉，未记载时留空，保留不确定性。")
    present_illness: Optional[str] = Field(default=None, title="现病史", description="原件记载的现病史，未记载时留空，保留不确定性。")
    physical_examination: Optional[str] = Field(default=None, title="体格检查", description="原件记载的体格检查，未记载时留空，保留不确定性。")
    auxiliary_examinations: Optional[str] = Field(default=None, title="辅助检查", description="原件记载的辅助检查，未记载时留空，保留不确定性。")
    diagnosis: Optional[str] = Field(default=None, title="诊断", description="原件记载的诊断，未记载时留空，保留不确定性。")
    treatment_plan: Optional[str] = Field(default=None, title="处理意见", description="原件记载的处理意见，未记载时留空，保留不确定性。")
    additional_content: Optional[str] = Field(default=None, title="补充内容", description="原件记载的补充内容，未记载时留空，保留不确定性。")


class ParsedEmergencyReport(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    chief_complaint: Optional[str] = Field(default=None, title="主诉", description="原件记载的主诉，未记载时留空，保留不确定性。")
    present_illness: Optional[str] = Field(default=None, title="现病史", description="原件记载的现病史，未记载时留空，保留不确定性。")
    physical_examination: Optional[str] = Field(default=None, title="体格检查", description="原件记载的体格检查，未记载时留空，保留不确定性。")
    auxiliary_examinations: Optional[str] = Field(default=None, title="辅助检查", description="原件记载的辅助检查，未记载时留空，保留不确定性。")
    diagnosis: Optional[str] = Field(default=None, title="诊断", description="原件记载的诊断，未记载时留空，保留不确定性。")
    treatment_plan: Optional[str] = Field(default=None, title="处理意见", description="原件记载的处理意见，未记载时留空，保留不确定性。")
    rescue_course: Optional[str] = Field(default=None, title="抢救经过", description="原件记载的抢救经过，未记载时留空，保留不确定性。")
    observation_details: Optional[str] = Field(default=None, title="留观情况", description="原件记载的留观情况，未记载时留空，保留不确定性。")
    discharge_diagnosis: Optional[str] = Field(default=None, title="出院诊断", description="原件记载的出院诊断，未记载时留空，保留不确定性。")
    discharge_instructions: Optional[str] = Field(default=None, title="出院医嘱", description="原件记载的出院医嘱，未记载时留空，保留不确定性。")
    additional_content: Optional[str] = Field(default=None, title="补充内容", description="原件记载的补充内容，未记载时留空，保留不确定性。")


class ParsedOtherReport(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    report_body: str = Field(
        min_length=1,
        description="无法归入其它类型的医疗报告正文。",
    )


class ParsedReport(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    report_type: ReportType = Field(description="医疗报告类型。")
    report_name: str = Field(
        min_length=1,
        max_length=255,
        description="医疗报告名称。",
    )
    report_time: str = Field(
        min_length=4,
        description="医疗报告的本地日期或日期时间。",
    )
    source_kind: Literal["screenshot", "scan", "pdf", "photo", "unknown"] = Field(
        default="unknown",
        description="原始来源的呈现形式。",
    )
    institution_name: Optional[str] = Field(
        default=None,
        description="出具医疗报告的机构名称。",
    )
    lab_test_results: list[ParsedLabResult] = Field(
        default_factory=list,
        description="检验报告的指标结果列表。",
    )
    examination_report: Optional[ParsedExaminationReport] = Field(
        default=None,
        description="检查报告的结构化内容。",
    )
    pathology_report: Optional[ParsedPathology] = Field(
        default=None,
        description="病理报告的结构化内容。",
    )
    surgery_report: Optional[ParsedSurgery] = Field(
        default=None,
        description="手术报告的结构化内容。",
    )
    outpatient_report: Optional[ParsedOutpatientReport] = Field(default=None, description="门诊病历的结构化内容。")
    emergency_report: Optional[ParsedEmergencyReport] = Field(default=None, description="急诊病历的结构化内容。")
    other_report: Optional[ParsedOtherReport] = Field(
        default=None,
        description="其它医疗报告的结构化内容。",
    )

    @field_validator("report_name")
    @classmethod
    def require_non_blank_report_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("医疗报告名称不能为空白")
        return normalized

    @model_validator(mode="after")
    def validate_typed_payload(self):
        payload_by_type = {
            "检验报告": bool(self.lab_test_results),
            "检查报告": self.examination_report is not None,
            "病理报告": self.pathology_report is not None,
            "手术报告": self.surgery_report is not None,
            "门诊病历": self.outpatient_report is not None,
            "急诊病历": self.emergency_report is not None,
            "其它医疗报告": self.other_report is not None,
        }
        if not payload_by_type[self.report_type]:
            raise ValueError(f"{self.report_type}缺少对应结构化字段")
        unexpected = [
            report_type
            for report_type, populated in payload_by_type.items()
            if populated and report_type != self.report_type
        ]
        if unexpected:
            raise ValueError(
                f"{self.report_type}不能同时包含其它医疗报告类型的结构化字段"
            )
        return self


class CreateReportRequest(BaseModel):
    """Explicit report-page creation payload for manually entered evidence."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    report_type: ReportType
    report_name: str = Field(min_length=1, max_length=255)
    report_time: str = Field(min_length=4)
    institution_name: Optional[str] = None
    lab_test_results: list[ParsedLabResult] = Field(default_factory=list)
    examination_report: Optional[ParsedExaminationReport] = None
    pathology_report: Optional[ParsedPathology] = None
    surgery_report: Optional[ParsedSurgery] = None
    outpatient_report: Optional[ParsedOutpatientReport] = Field(default=None, description="门诊病历的结构化内容。")
    emergency_report: Optional[ParsedEmergencyReport] = Field(default=None, description="急诊病历的结构化内容。")
    other_report: Optional[ParsedOtherReport] = None

    @field_validator("report_name")
    @classmethod
    def require_non_blank_report_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("医疗报告名称不能为空白")
        return normalized

    @model_validator(mode="after")
    def validate_typed_payload(self):
        ParsedReport.model_validate(
            {**self.model_dump(mode="json"), "source_kind": "unknown"}
        )
        return self



REPORT_STRUCTURES = {
    "检查报告": ("examination_report", ParsedExaminationReport),
    "病理报告": ("pathology_report", ParsedPathology),
    "手术报告": ("surgery_report", ParsedSurgery),
    "门诊病历": ("outpatient_report", ParsedOutpatientReport),
    "急诊病历": ("emergency_report", ParsedEmergencyReport),
    "其它医疗报告": ("other_report", ParsedOtherReport),
}
REPORT_TYPED_FIELDS = {table: tuple(model.model_fields) for table, model in REPORT_STRUCTURES.values()}
REPORT_TYPED_STORAGE_FIELDS = {
    report_type: {name: (table, name) for name in model.model_fields}
    for report_type, (table, model) in REPORT_STRUCTURES.items()
}
REPORT_AGENT_EDITABLE_FIELDS = frozenset({
    "report_time", "report_name", "institution_name", "lab_result", "lab_reference", "lab_flag",
    *(name for fields in REPORT_TYPED_FIELDS.values() for name in fields),
})
REPORT_EDITABLE_FIELDS = REPORT_AGENT_EDITABLE_FIELDS | {"analysis_content"}
REPORT_REQUIRED_EDITABLE_FIELDS = {"report_time", "report_name", "lab_result"} | {
    name for _, model in REPORT_STRUCTURES.values()
    for name, field in model.model_fields.items() if field.is_required()
}
EditableReportField = Literal[*sorted(REPORT_EDITABLE_FIELDS)]


class UpdateReportFieldRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    field: EditableReportField
    value: Optional[str] = None
    item_id: Optional[str] = None


class AddLabReportItemRequest(BaseModel):
    """Explicit report-page request to append one dictionary-backed lab result."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    item_id: str = Field(min_length=1, max_length=128)
    result_text: str = Field(min_length=1)
    reference_text: Optional[str] = None
    flag_text: FlagText = "未标记"

    @field_validator("item_id", "result_text")
    @classmethod
    def require_non_blank_lab_item_value(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("字段不能为空白")
        return normalized


def report_snapshot_fields(table: str) -> tuple[tuple[str, str], ...]:
    model = next(model for name, model in REPORT_STRUCTURES.values() if name == table)
    return tuple((name, field.title or name) for name, field in model.model_fields.items())
