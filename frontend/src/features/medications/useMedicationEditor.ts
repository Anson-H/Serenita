import { useEffect, useRef } from "react";
import { saveMedication, deleteMedication, saveMedicationCatalog, deleteMedicationCatalog } from "../../api/medicationApi";
import type { MedicationIdentity, MedicationItem, MedicationKind, MedicationPlanInput, MedicationValues } from "../../api/medicationTypes";
import { itemId } from "./medicationPresentation";
import { changedMedicationValues, medicationEditorDraft, type MedicationEditorDraft } from "./medicationDraft";
import { useAutosaveResource } from "../../utils/useAutosaveResource";
import { useActiveScope } from "../../utils/useActiveScope";

export function useMedicationEditor(member: string, kind: MedicationKind, item: MedicationItem | null, canEdit: boolean, onSaved: (item: MedicationItem) => void, onDeleted: () => void, catalogMode = false) {
  const key = `${member}:${kind}:${item ? itemId(item, kind) : "new"}`;
  const isCurrent = useActiveScope(key);
  const persisted = useRef(item);
  useEffect(() => { if (item) persisted.current = item; }, [item]);
  const requestId = useRef(crypto.randomUUID());
  const editor = useAutosaveResource<MedicationEditorDraft>({
    resourceKey: key, server: medicationEditorDraft(kind, item), enabled: canEdit && (kind === 'plan' || catalogMode), isNew: !persisted.current,
    validate: draft => {
      if (draft.kind === "medication" && !draft.values.generic_name.trim()) return "药品通用名不能为空。";
      if (draft.kind === "plan" && !draft.values.medication_id) return "请从药品目录中选择药品。";
      if (draft.kind === "plan" && (!draft.values.starts_at || !draft.values.start_precision)) return "请填写用药周期的开始日期。";
      return "";
    },
    save: async draft => {
      const previous = persisted.current ? medicationEditorDraft(kind, persisted.current) : null;
      const id = persisted.current ? itemId(persisted.current, kind) : undefined;
      const saved = draft.kind === "medication"
        ? await saveMedicationCatalog( changedMedicationValues(draft.values, previous?.kind === "medication" ? previous.values : null), id, requestId.current)
        : await saveMedication(member, "plan", changedMedicationValues(draft.values, previous?.kind === "plan" ? previous.values : null), id, requestId.current);
      persisted.current = saved;
      if (isCurrent()) onSaved(saved);
      return medicationEditorDraft(kind, saved);
    },
    onRemoved: onDeleted,
    remove: async () => { if (persisted.current) { if(kind === "medication" && catalogMode) await deleteMedicationCatalog(itemId(persisted.current, kind));
      else if(kind === "plan") await deleteMedication(member, kind, itemId(persisted.current, kind));  } },
  });
  const shared = {
    dirty: editor.dirty, saving: editor.saving, error: editor.error,
    flush: editor.flush, flushOnBlur: editor.flushOnBlur, compose: editor.compose, remove: editor.remove,
  };
  if (editor.draft.kind === "medication") {
    return {
      ...shared, kind: "medication" as const, draft: editor.draft.values,
      change: (changes: Partial<MedicationValues>, immediate = false) => {
        const current = editor.controller.snapshot().draft;
        if (current.kind === "medication") editor.change({ values: { ...current.values, ...changes } }, immediate);
      },
    };
  }
  return {
    ...shared, kind: "plan" as const, draft: editor.draft.values, identity: editor.draft.identity,
    change: (changes: Partial<MedicationPlanInput>, immediate = false) => {
      const current = editor.controller.snapshot().draft;
      if (current.kind === "plan") editor.change({ values: { ...current.values, ...changes } }, immediate);
    },
    selectMedication: (id: string | null, identity: MedicationIdentity) => {
      const current = editor.controller.snapshot().draft;
      if (current.kind === "plan") editor.change({ values: { ...current.values, medication_id: id ?? "" }, identity }, true);
    },
  };
}
