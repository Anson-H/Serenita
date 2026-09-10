import { RelatedContent } from "../../src/features/conversations/RelatedContent";
import { relatedResourcesForTurn } from "../../src/features/conversations/relatedResources";
import type { ConversationRecord, ConversationResourceState } from "../../src/api/client";
import { createRoot } from "react-dom/client";
import { type RelatedReportReference } from "../../src/features/conversations/RelatedReports";
import { reportResourceStateMap } from "../../src/features/reports/reportContext";
import "../../src/styles/index.css";

const reports: RelatedReportReference[] = ["deleted", "forbidden", "available"].map(member => ({
  relationship: "read",
  resource: {
    resource_type: "report", resource_id: "same-report", member_id: member,
    report_name: member, report_type: "检验报告",
    report_time: "2026-09-05T10:00:00+08:00",
    captured_created_at: "2026-09-05T10:00:00+08:00",
    captured_updated_at: "2026-09-05T10:00:00+08:00"
  }
}));
const states = reportResourceStateMap((["deleted", "forbidden", "available"] as const).map(availability => ({
  resource_type: "report", resource_id: "same-report", member_id: availability, availability,
  current_created_at: "2026-09-05T10:00:00+08:00", current_updated_at: "2026-09-05T10:00:00+08:00"
})));
const timestamp = "2026-09-10T08:00:00Z";
const mixed = new URLSearchParams(location.search).has("mixed");
const references = [
  { resource_type: "medical_log", resource_id: "diary", member_id: "available", name: "今天的随记", recorded_on: "2026-09-10" },
  { resource_type: "medication_plan", resource_id: "plan", member_id: "available", name: "早间用药安排" },
  { resource_type: "medication_batch", resource_id: "batch", medication_id: "drug", member_id: "available", name: "现有药品库存" },
  { resource_type: "body_record", resource_id: "weight", category: "body", member_id: "available", name: "体重" },
  { resource_type: "medical_log", resource_id: "diary", member_id: "forbidden", name: "共享日记" },
  { resource_type: "medical_log", resource_id: "removed", member_id: "available", name: "删除的日记" },
].map(item => ({ ...item, created_at: timestamp, updated_at: timestamp }));
const toolRecords = references.map(item => ({ kind: "tool", turn_id: "turn", result: { effects: {
  [item.resource_id === "removed" ? "affected_resource_refs" : "resource_refs"]: [item],
  changed_entities: [{ entity_type: item.resource_type, entity_id: item.resource_id, change: item.resource_id === "removed" ? "deleted" : "modified" }],
} } })) as unknown as ConversationRecord[];
const resourceStates = references.map(item => ({ ...item, availability: item.member_id === "forbidden" ? "forbidden" : item.resource_id === "removed" ? "deleted" : "available",
  current_created_at: timestamp, current_updated_at: item.resource_id === "diary" ? "2026-09-11T08:00:00Z" : timestamp,
})) as ConversationResourceState[];
createRoot(document.getElementById("root")!).render(<RelatedContent
  messageId="historical-answer" reports={reports} resourceStateByReportId={states}
  resources={mixed ? relatedResourcesForTurn(toolRecords, "turn") : []} resourceStates={resourceStates}
  onOpenReport={() => { document.body.dataset.opened = "true"; }}
/>);
