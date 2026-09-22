export const MEDICAL_HISTORY_FIELDS = [
  ["past_medical_history", "既往疾病史", "以前得过什么病，做过什么治疗？"],
  ["surgical_trauma_history", "手术外伤史", "做过手术或受过外伤吗？"],
  ["allergy_history", "过敏史", "有药物、食物或其他物质过敏或不适吗？"],
  ["transfusion_vaccination_history", "输血接种史", "有输血或接种经历吗？"],
  ["birth_occupational_history", "出生与职业史", "可以说说出生、居住和工作经历吗？"],
  ["lifestyle_history", "生活史", "平时的生活和饮食怎么样？"],
  ["family_history", "家族病史", "家里有人得过相关疾病吗？"],
  ["special_history", "特殊史", "还有其他想补充的吗？"]
] as const;
export type MedicalHistoryField = typeof MEDICAL_HISTORY_FIELDS[number][0];
export type MedicalHistory = { member_id: string; history: Record<MedicalHistoryField, { text: string | null; updated_at: string | null }> };
export type MedicalHistoryChanges = Partial<Record<MedicalHistoryField, string | null>>;
