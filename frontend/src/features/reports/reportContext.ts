import type {
  ConversationResourceState,
  ReportContextResource,
  ReportDetail,
  ReportSummary,
  ReportType
} from "../../api/client";
import { REPORT_TYPES } from "../../api/client";

type ReportReferenceStatus = "current" | "modified" | "deleted" | "forbidden" | "unknown";

export function reportReferenceStatus(
  resource: ReportContextResource,
  state?: ConversationResourceState
): ReportReferenceStatus {
  if (!state || state.member_id !== resource.member_id || state.resource_id !== resource.resource_id) {
    return "unknown";
  }
  if (state.availability === "forbidden") return "forbidden";
  if (
    state.availability === "deleted"
    || state.current_created_at !== resource.captured_created_at
  ) {
    return "deleted";
  }
  return state.current_updated_at !== resource.captured_updated_at
    ? "modified"
    : "current";
}

export function reportResourceKey(resource: { member_id?: string | null; resource_id: string }) {
  return JSON.stringify([resource.member_id ?? null, resource.resource_id]);
}

export function reportResourceStateMap(states: ConversationResourceState[]) {
  return new Map(
    states
      .filter((state) => state.resource_type === "report")
      .map((state) => [reportResourceKey(state), state] as const)
  );
}

export function reportContextResourceFromRecord(
  resource: Record<string, unknown>
): ReportContextResource | null {
  if (resource.resource_type !== "report" || typeof resource.resource_id !== "string") {
    return null;
  }
  const reportId = resource.resource_id.trim();
  if (!reportId) {
    return null;
  }
  const reportTime = typeof resource.report_time === "string" ? resource.report_time.trim() : "";
  const reportName = typeof resource.report_name === "string" ? resource.report_name.trim() : "";
  const reportType = typeof resource.report_type === "string"
    && REPORT_TYPES.includes(resource.report_type as ReportType)
    ? resource.report_type as ReportType
    : null;
  const capturedCreatedAt = typeof resource.captured_created_at === "string"
    ? resource.captured_created_at.trim()
    : "";
  const capturedUpdatedAt = typeof resource.captured_updated_at === "string"
    ? resource.captured_updated_at.trim()
    : "";
  if (typeof resource.member_id !== "string" || !resource.member_id || !reportTime || !reportName || !reportType || !capturedCreatedAt || !capturedUpdatedAt) {
    return null;
  }
  return {
    resource_type: "report",
    member_id: typeof resource.member_id === "string" ? resource.member_id : "",
    resource_id: reportId,
    report_time: reportTime,
    report_type: reportType,
    report_name: reportName,
    captured_created_at: capturedCreatedAt,
    captured_updated_at: capturedUpdatedAt
  };
}

export function reportContextResourceFromReport(
  report: ReportDetail | ReportSummary
): ReportContextResource {
  return {
    resource_type: "report",
    resource_id: report.report_id,
    member_id: report.member_id,
    report_time: report.report_time,
    report_type: report.report_type,
    report_name: report.report_name,
    captured_created_at: report.created_at,
    captured_updated_at: report.updated_at
  };
}
