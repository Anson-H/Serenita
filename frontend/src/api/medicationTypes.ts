export type MedicationKind = 'medication' | 'plan';
export type MedicationSection = 'catalog' | 'plans';
export type MedicationIdentity = { generic_name: string; brand_name?: string | null; strength?: string | null; package_specification?: string | null };
export type MedicationPrescriptionType = 'prescription' | 'nonprescription' | 'unknown';
export type MedicationValues = Required<MedicationIdentity> & {
  prescription_type: MedicationPrescriptionType;
  notes: string | null;
  leaflet_url: string | null;
};
export type DoseTime = { time: string };
export type MedicationSchedule = { kind: 'daily' | 'weekly' | 'every_n_days' | 'as_needed'; times?: DoseTime[]; times_per_day?: number | null; weekdays?: number[]; interval_days?: number | null; anchor_date?: string | null; };
// ends_at: 带偏移 ISO 结束边界、long_term（明确长期）或 null（未知）。
export type MedicationPlanValues = { starts_at: string | null; ends_at: string | null; start_precision: 'date' | 'minute' | null; end_precision: 'date' | 'minute' | null; timezone: string; dose_text?: string | null; route?: string | null; schedule: MedicationSchedule | null; usage_status: 'taking' | 'paused' | 'stopped' | 'completed' | 'unknown' };
export type MedicationPlanInput = MedicationPlanValues & { medication_id: string; notes: string | null };
export type MedicationSource = { resource_id: string; is_primary: boolean | number; source_index: number; original_filename: string; mime_type: string; purpose: string; size_bytes: number };
export type MedicationBatch = { medication_batch_id: string; medication_id: string; quantity: string; expires_on: string | null; notes: string | null };
type MedicationAudit = {
  member_id?: string; created_at: string; updated_at: string;
  notes?: string | null;
};
export type Medication = MedicationAudit & MedicationIdentity & Partial<Record<keyof MedicationPlanValues, never>> & {
  medication_id: string; medication_plan_id?: never; medication_identity?: never;
  time_status?: never;
  prescription_type?: MedicationPrescriptionType; leaflet_url?: string | null;
  sources?: MedicationSource[]; batches?: MedicationBatch[];
};
export type MedicationPlan = MedicationAudit & MedicationPlanValues & {
  member_id: string;
  medication_plan_id: string; medication_id: string; medication_identity: MedicationIdentity;
  generic_name?: never; brand_name?: never; strength?: never; package_specification?: never;
  time_status?: string; sources?: never; batches?: never;
};
export type MedicationItem = Medication | MedicationPlan;
export type MedicationOfKind<K extends MedicationKind> = K extends 'medication' ? Medication : MedicationPlan;
export type MedicationChanges = Partial<MedicationValues>;
export type MedicationPlanChanges = Partial<MedicationPlanInput>;
export type MedicationChangesByKind = { medication: MedicationChanges; plan: MedicationPlanChanges };
export type MedicationFilters = { query: string; status: string; after_date: string; before_date: string; undated: boolean; inventory_only?: boolean };
