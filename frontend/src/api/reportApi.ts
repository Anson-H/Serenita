import type {
  AddLabReportItemInput,
  CreateReportInput,
  DeleteReportResponse,
  ReportDetail,
  ReportEditableField,
  ReportListResponse,
  ReportType
} from "./reportTypes";
import { request, requestResponse } from "./request";

export function fetchReports(memberId: string, input: {
  report_type?: ReportType | "all";
} = {}) {
  const query = new URLSearchParams();
  if (input.report_type && input.report_type !== "all") {
    query.set("report_type", input.report_type);
  }
  const suffix = query.size ? `?${query.toString()}` : "";
  return request<ReportListResponse>(`/members/${encodeURIComponent(memberId)}/reports${suffix}`);
}

export function getReport(memberId: string, reportId: string) {
  return request<ReportDetail>(`/members/${encodeURIComponent(memberId)}/reports/${encodeURIComponent(reportId)}`);
}

export function createReport(memberId: string, input: CreateReportInput) {
  return request<ReportDetail>(`/members/${encodeURIComponent(memberId)}/reports`, {
    method: "POST",
    body: JSON.stringify(input)
  });
}

export function addReportSourceFiles(
  memberId: string,
  reportId: string,
  files: File[]
) {
  const body = new FormData();
  files.forEach((file) => body.append("files", file));
  return request<ReportDetail>(
    `/members/${encodeURIComponent(memberId)}/reports/${encodeURIComponent(reportId)}/source-files`,
    { method: "POST", body }
  );
}

export function updateReportField(
  memberId: string,
  reportId: string,
  input: {
    field: ReportEditableField;
    value: string | null;
    item_id?: string;
  }
) {
  return request<ReportDetail>(
    `/members/${encodeURIComponent(memberId)}/reports/${encodeURIComponent(reportId)}/fields`,
    { method: "PATCH", body: JSON.stringify(input) }
  );
}

export function addReportLabItem(
  memberId: string,
  reportId: string,
  input: AddLabReportItemInput
) {
  return request<ReportDetail>(
    `/members/${encodeURIComponent(memberId)}/reports/${encodeURIComponent(reportId)}/lab-items`,
    { method: "POST", body: JSON.stringify(input) }
  );
}

export function deleteReportLabItem(memberId: string, reportId: string, itemId: string) {
  return request<ReportDetail>(
    `/members/${encodeURIComponent(memberId)}/reports/${encodeURIComponent(reportId)}/lab-items/${encodeURIComponent(itemId)}`,
    { method: "DELETE" }
  );
}

export function deleteReport(memberId: string, reportId: string) {
  return request<DeleteReportResponse>(
    `/members/${encodeURIComponent(memberId)}/reports/${encodeURIComponent(reportId)}`,
    { method: "DELETE" }
  );
}

export async function fetchReportSourceBlob(
  memberId: string,
  reportId: string,
  resourceId: string,
  signal?: AbortSignal
) {
  return fetchReportBlob(
    `/members/${encodeURIComponent(memberId)}/reports/${encodeURIComponent(reportId)}/source-files/${encodeURIComponent(resourceId)}`,
    signal
  );
}

export async function fetchReportSourceThumbnailBlob(
  memberId: string,
  reportId: string,
  resourceId: string,
  signal?: AbortSignal
) {
  return fetchReportBlob(
    `/members/${encodeURIComponent(memberId)}/reports/${encodeURIComponent(reportId)}/source-files/${encodeURIComponent(resourceId)}/thumbnail`,
    signal
  );
}

async function fetchReportBlob(path: string, signal?: AbortSignal) {
  const response = await requestResponse(path, { cache: "no-store", signal });
  return response.blob();
}
