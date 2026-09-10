import type {
  Medication, MedicationIdentity, MedicationItem, MedicationKind,
  MedicationPlan, MedicationPlanInput, MedicationValues,
} from '../../api/medicationTypes';
import { emptyPlan } from './medicationPresentation';

export type MedicationEditorDraft =
  | { kind: 'medication'; values: MedicationValues }
  | { kind: 'plan'; values: MedicationPlanInput; identity: MedicationIdentity };

function isMedicationPlan(item: MedicationItem): item is MedicationPlan {
  return typeof item.medication_plan_id === 'string';
}

function identityValues(item: Partial<MedicationIdentity>): Required<MedicationIdentity> {
  return {
    generic_name: item.generic_name ?? '',
    brand_name: item.brand_name ?? null,
    strength: item.strength ?? null,
    package_specification: item.package_specification ?? null,
  };
}

export function medicationValues(item: Medication | null): MedicationValues {
  return {
    ...identityValues(item ?? {}),
    prescription_type: item?.prescription_type ?? 'unknown',
    notes: item?.notes ?? null,
    leaflet_url: item?.leaflet_url ?? null,
  };
}

export function medicationPlanValues(item: MedicationPlan | null): MedicationPlanInput {
  const plan = item ?? emptyPlan();
  return {
    medication_id: item?.medication_id ?? '',
    starts_at: plan.starts_at,
    ends_at: plan.ends_at,
    start_precision: plan.start_precision,
    end_precision: plan.end_precision,
    timezone: plan.timezone,
    dose_text: plan.dose_text ?? null,
    route: plan.route ?? null,
    schedule: plan.schedule,
    usage_status: plan.usage_status,
    notes: item?.notes ?? null,
  };
}

export function medicationEditorDraft(kind: MedicationKind, item: MedicationItem | null): MedicationEditorDraft {
  if (kind === 'plan') {
    if (item && !isMedicationPlan(item)) throw new Error('用药计划编辑器需要用药计划。');
    return { kind, values: medicationPlanValues(item), identity: identityValues(item?.medication_identity ?? {}) };
  }
  if (item && isMedicationPlan(item)) throw new Error('药品编辑器需要药品资料。');
  return { kind, values: medicationValues(item) };
}

/** Compare only the editable fields selected by the domain's draft projection. */
export function changedMedicationValues<T extends object>(value: T, previous: T | null): Partial<T> {
  const changes: Partial<T> = {};
  for (const key in value) {
    if (!previous || JSON.stringify(previous[key]) !== JSON.stringify(value[key])) changes[key] = value[key];
  }
  return changes;
}
