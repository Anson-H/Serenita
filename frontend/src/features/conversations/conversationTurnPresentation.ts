import type { ConversationMessage, ConversationToolRecord } from "../../api/client";
import { reportContextResourceFromRecord } from "../reports/reportContext";
import type {
  RelatedReportReference,
  RelatedReportRelationship
} from "./RelatedReports";

const RELATED_REPORT_RELATIONSHIP_ORDER: Record<RelatedReportRelationship, number> = {
  created: 0,
  deleted: 1,
  modified: 2,
  reclassified: 2,
  analysis_written: 2,
  source_linked: 2,
  read: 3
};

export function modelInputTextByResourceId(content: unknown) {
  if (!content || typeof content !== "object" || Array.isArray(content)) {
    return {};
  }
  const messageContent = (content as Record<string, unknown>).content;
  if (!Array.isArray(messageContent)) {
    return {};
  }
  const inputTextByResourceId: Record<string, string> = {};
  for (const part of messageContent) {
    if (!part || typeof part !== "object" || Array.isArray(part)) {
      continue;
    }
    const value = part as Record<string, unknown>;
    const text = typeof value.text === "string" ? value.text : "";
    const resourceRef = value.model_resource_ref;
    if (resourceRef && typeof resourceRef === "object" && !Array.isArray(resourceRef)) {
      const resourceId = (resourceRef as Record<string, unknown>).resource_id;
      if (typeof resourceId === "string" && text) {
        inputTextByResourceId[resourceId] = text;
        continue;
      }
    }
    const markerEnd = text.indexOf("\n");
    if (markerEnd < 0) {
      continue;
    }
    const marker = text.slice(0, markerEnd);
    if (
      marker !== "ATTACHED ANNOTATION"
      && marker !== "ATTACHED EXISTING CONTENT"
    ) {
      continue;
    }
    try {
      const payload = JSON.parse(text.slice(markerEnd + 1)) as Record<string, unknown>;
      const report = payload.report;
      const resourceId = marker === "ATTACHED ANNOTATION"
        ? payload.resource_id
        : report && typeof report === "object" && !Array.isArray(report)
          ? (report as Record<string, unknown>).report_id
          : undefined;
      if (typeof resourceId === "string" && resourceId) {
        inputTextByResourceId[resourceId] = text;
      }
    } catch {
      // Unknown user text remains visible in the current-user-message trace,
      // but cannot be associated with an attachment-like resource label.
    }
  }
  return inputTextByResourceId;
}

export function relatedReportResourcesForAssistant(
  message: ConversationMessage,
  toolRecords: ConversationToolRecord[]
) {
  const reports = new Map<string, RelatedReportReference>();
  const relationshipForChange = (change: unknown): RelatedReportRelationship => {
    if (change === "deleted") return "deleted";
    if (change === "reclassified") return "reclassified";
    if (change === "analysis_written") return "analysis_written";
    if (change === "source_linked") return "source_linked";
    return "modified";
  };
  const mergeRelationship = (
    current: RelatedReportRelationship | undefined,
    next: RelatedReportRelationship
  ): RelatedReportRelationship => {
    if (next === "deleted" || current === "deleted") return "deleted";
    if (next === "created" || current === "created") return "created";
    return next === "read" && current ? current : next;
  };

  toolRecords.forEach((record) => {
    if (record.turn_id !== message.turn_id || !record.result || typeof record.result !== "object") {
      return;
    }
    const effects = (record.result as Record<string, unknown>).effects;
    if (!effects || typeof effects !== "object") {
      return;
    }
    const effectRecord = effects as Record<string, unknown>;
    const createdIds = new Set(
      Array.isArray(effectRecord.created_entities)
        ? effectRecord.created_entities
          .filter((entity): entity is Record<string, unknown> =>
            Boolean(entity) && typeof entity === "object" && !Array.isArray(entity)
          )
          .filter((entity) => entity.entity_type === "report")
          .map((entity) => String(entity.entity_id ?? ""))
        : []
    );
    const changes = new Map<string, unknown>();
    if (Array.isArray(effectRecord.changed_entities)) {
      effectRecord.changed_entities.forEach((entity) => {
        if (
          entity && typeof entity === "object" && !Array.isArray(entity)
          && (entity as Record<string, unknown>).entity_type === "report"
        ) {
          changes.set(
            String((entity as Record<string, unknown>).entity_id ?? ""),
            (entity as Record<string, unknown>).change
          );
        }
      });
    }
    const refs = [
      ...(Array.isArray(effectRecord.resource_refs) ? effectRecord.resource_refs : []),
      ...(Array.isArray(effectRecord.affected_resource_refs)
        ? effectRecord.affected_resource_refs
        : [])
    ];
    refs.forEach((reference) => {
      if (!reference || typeof reference !== "object" || Array.isArray(reference)) {
        return;
      }
      const resource = reportContextResourceFromRecord(reference as Record<string, unknown>);
      if (!resource) return;
      const nextRelationship = createdIds.has(resource.resource_id)
        ? "created"
        : changes.has(resource.resource_id)
          ? relationshipForChange(changes.get(resource.resource_id))
          : "read";
      const current = reports.get(resource.resource_id);
      reports.set(resource.resource_id, {
        relationship: mergeRelationship(current?.relationship, nextRelationship),
        resource
      });
    });
  });
  return [...reports.values()].sort(
    (left, right) => (
      RELATED_REPORT_RELATIONSHIP_ORDER[left.relationship]
      - RELATED_REPORT_RELATIONSHIP_ORDER[right.relationship]
    )
  );
}
