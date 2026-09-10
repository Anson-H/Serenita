import type { ConversationRecord } from "../../api/client";
import { bodyMetricPath, medicalLogPath, medicationBatchPath, medicationPath } from "../../app/routes";

export const RESOURCE_LABELS = {
  medical_log: "健康日记", medication: "药品资料", medication_plan: "用药计划",
  medication_batch: "药品批次", body_record: "身体指标",
};
export type RelatedResourceType = keyof typeof RESOURCE_LABELS;
export type RelatedResourceReference = {
  resource_type: RelatedResourceType; resource_id: string; member_id: string;
  name: string; created_at: string; updated_at: string;
  recorded_on?: string; medication_id?: string; category?: string;
  relationship: "created" | "modified" | "source_linked" | "deleted" | "read";
};
export const RESOURCE_RELATIONSHIPS = {
  created: "创建", modified: "更新", source_linked: "补充原件", deleted: "删除", read: "查阅",
};
const relationshipOrder = { created: 0, deleted: 1, modified: 2, source_linked: 2, read: 3 };
export function resourceKey(item: { member_id: string; resource_type: string; resource_id: string }) {
  return JSON.stringify([item.member_id, item.resource_type, item.resource_id]);
}
function object(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
}
function array(value: unknown): unknown[] { return Array.isArray(value) ? value : []; }

export function relatedResourcesForTurn(records: ConversationRecord[], turnId: string): RelatedResourceReference[] {
  const refs = new Map<string, RelatedResourceReference>();
  for (const record of records) {
    if (record.kind !== "tool" || record.turn_id !== turnId) continue;
    const effects = object(object(record.result)?.effects);
    if (!effects) continue;
    for (const raw of [...array(effects.resource_refs), ...array(effects.affected_resource_refs)]) {
      const item = object(raw);
      if (!item || typeof item.resource_type !== "string" || !Object.hasOwn(RESOURCE_LABELS, item.resource_type)) continue;
      if (!["resource_id", "member_id", "name", "created_at", "updated_at"].every(key => typeof item[key] === "string" && item[key])) continue;
      if (item.resource_type === "medication_batch" && (typeof item.medication_id !== "string" || !item.medication_id)) continue;
      if (item.resource_type === "body_record" && (typeof item.category !== "string" || !item.category)) continue;
      const matches = (value: unknown) => {
        const entity = object(value);
        return entity?.entity_type === item.resource_type && entity?.entity_id === item.resource_id;
      };
      const change = object(array(effects.changed_entities).find(matches))?.change;
      let relationship: RelatedResourceReference["relationship"] = change === "deleted" ? "deleted"
        : array(effects.created_entities).some(matches) ? "created"
        : change === "source_linked" ? "source_linked" : change ? "modified" : "read";
      const resource = item as Omit<RelatedResourceReference, "relationship">;
      const key = resourceKey(resource);
      const previous = refs.get(key);
      if (previous) {
        if (previous.relationship === "deleted") relationship = "deleted";
        else if (relationship !== "deleted" && previous.relationship === "created") relationship = "created";
        else if (relationship === "read") relationship = previous.relationship;
      }
      refs.set(key, { ...resource, relationship });
    }
  }
  return [...refs.values()].sort((a, b) => relationshipOrder[a.relationship] - relationshipOrder[b.relationship]);
}

export function relatedResourcePath(item: RelatedResourceReference) {
  switch (item.resource_type) {
    case "medical_log": return medicalLogPath(item.member_id, item.resource_id);
    case "medication": return medicationPath(item.member_id, "catalog", item.resource_id);
    case "medication_plan": return medicationPath(item.member_id, "plans", item.resource_id);
    case "medication_batch": return medicationBatchPath(item.member_id, item.medication_id!, item.resource_id);
    case "body_record": return `${bodyMetricPath(item.member_id, item.category)}?record=${encodeURIComponent(item.resource_id)}`;
  }
}
