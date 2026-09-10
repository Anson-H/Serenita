export const REPORT_TYPES = [
  "检验报告",
  "检查报告",
  "病理报告",
  "手术报告",
  "门诊病历",
  "急诊病历",
  "其它医疗报告"
] as const;

export type ReportType = (typeof REPORT_TYPES)[number];

export const LAB_FLAG_TEXTS = ["未标记", "正常", "异常", "偏高", "偏低"] as const;
export type LabFlagText = (typeof LAB_FLAG_TEXTS)[number];

export type ReportFacts = {
  report_id: string;
  member_id: string;
  report_type: ReportType;
  report_name: string;
  report_time: string;
  institution_name?: string | null;
  has_analysis: boolean;
  analysis_outdated: boolean;
  created_at: string;
  updated_at: string;
};

export type ReportSourceFile = {
  resource_id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  source_kind: "screenshot" | "scan" | "pdf" | "photo" | "unknown";
  source_type: "uploaded_file" | "conversation_text";
  download_url: string;
  thumbnail_url?: string;
  created_at: string;
  is_primary: boolean;
};

export type LabTestResult = {
  report_id?: string;
  item_id: string;
  item_name_zh: string;
  category_name?: string;
  result_text: string;
  reference_text?: string | null;
  flag_text: LabFlagText;
};

export type AddLabReportItemInput = {
  item_id: string;
  result_text: string;
  reference_text?: string | null;
  flag_text: LabFlagText;
};

export type ExaminationReport = {
  exam_name?: string | null;
  clinical_diagnosis?: string | null;
  exam_method?: string | null;
  exam_findings?: string | null;
  exam_diagnosis?: string | null;
};

export type PathologyReport = {
  submitted_specimen?: string | null;
  gross_examination?: string | null;
  diagnosis?: string | null;
  sampling_location?: string | null;
};

export type SurgeryReport = {
  preoperative_diagnosis?: string | null;
  intraoperative_diagnosis?: string | null;
  anesthesia_method?: string | null;
  started_at?: string | null;
  ended_at?: string | null;
  blood_transfusion?: string | null;
  intraoperative_blood_loss?: string | null;
  intraoperative_urine_output?: string | null;
  intraoperative_transfusion?: string | null;
  intraoperative_infusion?: string | null;
  intraoperative_other_drugs?: string | null;
  procedure_description?: string | null;
  postoperative_vital_signs?: string | null;
};

export type OutpatientReport = {
  chief_complaint?: string | null;
  present_illness?: string | null;
  physical_examination?: string | null;
  auxiliary_examinations?: string | null;
  diagnosis?: string | null;
  treatment_plan?: string | null;
  additional_content?: string | null;
};

export type EmergencyReport = {
  chief_complaint?: string | null;
  present_illness?: string | null;
  physical_examination?: string | null;
  auxiliary_examinations?: string | null;
  diagnosis?: string | null;
  treatment_plan?: string | null;
  rescue_course?: string | null;
  observation_details?: string | null;
  discharge_diagnosis?: string | null;
  discharge_instructions?: string | null;
  additional_content?: string | null;
};

type OtherReport = {
  report_body?: string | null;
};

export type ReportSummary = ReportFacts & { flagged_count: number; total_count: number };

export type ReportDetail = ReportFacts & {
  analysis_updated_at: string | null;
  report_name: string;
  sources: ReportSourceFile[];
  lab_test_results?: LabTestResult[];
  examination_report?: ExaminationReport | null;
  pathology_report?: PathologyReport | null;
  surgery_report?: SurgeryReport | null;
  outpatient_report?: OutpatientReport | null;
  emergency_report?: EmergencyReport | null;
  other_report?: OtherReport | null;
  analysis_content?: string | null;
};

export type CreateReportInput = {
  report_type: ReportType;
  report_name: string;
  report_time: string;
  institution_name?: string | null;
  lab_test_results?: Array<{
    item_id: string;
    item_name_zh: string;
    aliases: string[];
    category_name: string;
    result_text: string;
    reference_text?: string | null;
    flag_text: LabFlagText;
  }>;
  examination_report?: ExaminationReport | null;
  pathology_report?: PathologyReport | null;
  surgery_report?: SurgeryReport | null;
  outpatient_report?: OutpatientReport | null;
  emergency_report?: EmergencyReport | null;
  other_report?: OtherReport | null;
};

export type DeleteReportResponse = {
  report_id: string;
  deleted: true;
};

export type ReportEditableField =
  | "report_name"
  | "institution_name"
  | "report_time"
  | "analysis_content"
  | "lab_result"
  | "lab_reference"
  | "lab_flag"
  | "exam_name"
  | "clinical_diagnosis"
  | "exam_method"
  | "exam_findings"
  | "exam_diagnosis"
  | "submitted_specimen"
  | "gross_examination"
  | "diagnosis"
  | "sampling_location"
  | "preoperative_diagnosis"
  | "intraoperative_diagnosis"
  | "anesthesia_method"
  | "started_at"
  | "ended_at"
  | "blood_transfusion"
  | "intraoperative_blood_loss"
  | "intraoperative_urine_output"
  | "intraoperative_transfusion"
  | "intraoperative_infusion"
  | "intraoperative_other_drugs"
  | "procedure_description"
  | "postoperative_vital_signs"
  | "chief_complaint"
  | "present_illness"
  | "physical_examination"
  | "auxiliary_examinations"
  | "treatment_plan"
  | "rescue_course"
  | "observation_details"
  | "discharge_diagnosis"
  | "discharge_instructions"
  | "additional_content"
  | "report_body";

export type ReportListResponse = {
  reports: ReportSummary[];
  total: number;
};

export type ReportContextResource = {
  resource_type: "report";
  resource_id: string;
  member_id: string;
  report_time: string;
  report_type: ReportType;
  report_name: string;
  captured_created_at: string;
  captured_updated_at: string;
};
