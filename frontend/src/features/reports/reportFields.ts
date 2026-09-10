import type { ReportEditableField, ReportType } from "../../api/client";

export type EntryField = {
  key: ReportEditableField;
  label: string;
  placeholder?: string;
  required?: boolean;
  textarea?: boolean;
  type?: "datetime-local" | "text";
};

export const ENTRY_FIELDS: Partial<Record<ReportType, EntryField[]>> = {
  "门诊病历": [
    { key: "chief_complaint", label: "主诉", textarea: true },
    { key: "present_illness", label: "现病史", textarea: true },
    { key: "physical_examination", label: "体格检查", textarea: true },
    { key: "auxiliary_examinations", label: "辅助检查", textarea: true },
    { key: "diagnosis", label: "诊断", textarea: true },
    { key: "treatment_plan", label: "处理意见", textarea: true },
    { key: "additional_content", label: "补充内容", textarea: true }
  ],
  "急诊病历": [
    { key: "chief_complaint", label: "主诉", textarea: true },
    { key: "present_illness", label: "现病史", textarea: true },
    { key: "physical_examination", label: "体格检查", textarea: true },
    { key: "auxiliary_examinations", label: "辅助检查", textarea: true },
    { key: "diagnosis", label: "诊断", textarea: true },
    { key: "treatment_plan", label: "处理意见", textarea: true },
    { key: "rescue_course", label: "抢救经过", textarea: true },
    { key: "observation_details", label: "留观情况", textarea: true },
    { key: "discharge_diagnosis", label: "出院诊断", textarea: true },
    { key: "discharge_instructions", label: "出院医嘱", textarea: true },
    { key: "additional_content", label: "补充内容", textarea: true }
  ],
  "其它医疗报告": [
    { key: "report_body", label: "医疗报告正文", textarea: true, required: true, placeholder: "录入医疗报告正文" }
  ],
  "检查报告": [
    { key: "exam_name", label: "名称", required: true, placeholder: "例如：腹部超声" },
    { key: "clinical_diagnosis", label: "临床诊断", textarea: true },
    { key: "exam_method", label: "方法与技术" },
    { key: "exam_findings", label: "表现", textarea: true },
    { key: "exam_diagnosis", label: "诊断", textarea: true }
  ],
  "病理报告": [
    { key: "submitted_specimen", label: "送检标本", textarea: true },
    { key: "gross_examination", label: "巨检", textarea: true },
    { key: "diagnosis", label: "诊断", textarea: true },
    { key: "sampling_location", label: "取材位置", textarea: true }
  ],
  "手术报告": [
    { key: "preoperative_diagnosis", label: "术前诊断", textarea: true },
    { key: "intraoperative_diagnosis", label: "术中诊断", textarea: true },
    { key: "anesthesia_method", label: "麻醉方法" },
    { key: "started_at", label: "开始时间", type: "datetime-local" },
    { key: "ended_at", label: "结束时间", type: "datetime-local" },
    { key: "blood_transfusion", label: "是否输血" },
    { key: "intraoperative_blood_loss", label: "术中失血量" },
    { key: "intraoperative_urine_output", label: "术中尿量" },
    { key: "intraoperative_transfusion", label: "术中输血量" },
    { key: "intraoperative_infusion", label: "术中输液量" },
    { key: "intraoperative_other_drugs", label: "术中其他用药", textarea: true },
    { key: "procedure_description", label: "手术经过", textarea: true },
    { key: "postoperative_vital_signs", label: "术后生命体征", textarea: true }
  ]
};

export const REPORT_DETAIL_KEYS = {
  "检查报告": "examination_report", "病理报告": "pathology_report",
  "门诊病历": "outpatient_report", "急诊病历": "emergency_report",
  "手术报告": "surgery_report", "其它医疗报告": "other_report"
} as const;
