import { useRef } from "react";
import type { MedicationBatch } from "../../api/medicationTypes";
import { saveBatch, deleteBatch } from "../../api/medicationApi";
import { useAutosaveResource } from "../../utils/useAutosaveResource";
import { useActiveScope } from "../../utils/useActiveScope";
type Values = { quantity: string; expires_on: string | null; notes: string | null };
export function useBatchEditor(member: string, medication: string, original: MedicationBatch | undefined, canEdit: boolean, onSaved: (batch: MedicationBatch) => void, onDeleted: () => void) {
  const id = useRef(original?.medication_batch_id);
  const key = `${member}:${medication}:${id.current ?? "missing"}`;
  const current = useActiveScope(key);
  const values = (batch: MedicationBatch | undefined): Values => ({ quantity: batch?.quantity ?? "", expires_on: batch?.expires_on ?? null, notes: batch?.notes ?? null });
  const editor = useAutosaveResource<Values>({
    resourceKey: key, server: values(original), enabled: canEdit && Boolean(id.current),
    validate: value => /^\d+(?:\.\d+)?$/.test(value.quantity) && value.quantity.length <= 120 ? "" : "请填写有效的非负数量。",
    save: async value => { const saved = await saveBatch(member, medication, value, id.current); if (current()) onSaved(saved); return values(saved); },
    onRemoved: onDeleted,
    remove: async () => { if (id.current) { await deleteBatch(member, medication, id.current);  } },
  });
  return { ...editor, savedId: id.current };
}
