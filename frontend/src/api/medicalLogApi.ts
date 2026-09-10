import { request } from "./request";

export type MedicalLogSummary = {
  medical_log_id: string; member_id: string; recorded_on: string;
  title: string; summary: string; created_at: string; updated_at: string;
};
export type MedicalLog = Omit<MedicalLogSummary, "summary"> & {
  content: string;
};
export type MedicalLogInput = Pick<MedicalLog, "title" | "content" | "recorded_on">;
export type MedicalLogChanges = Partial<MedicalLogInput>;
export type MedicalLogFilters = { after_date?: string; before_date?: string; query?: string; cursor?: string; limit?: number };
const base = (memberId: string) => `/members/${encodeURIComponent(memberId)}/medical-logs`;
const detail = (memberId: string, logId: string) => `${base(memberId)}/${encodeURIComponent(logId)}`;
export function fetchMedicalLogs(memberId: string, filters: MedicalLogFilters = {}, signal?: AbortSignal) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => { if (value !== undefined && value !== "") params.set(key, String(value)); });
  return request<{ member_id: string; medical_logs: MedicalLogSummary[]; total: number; next_cursor: string | null }>(`${base(memberId)}?${params}`, { signal });
}
export const getMedicalLog = (memberId: string, logId: string, signal?: AbortSignal) => request<{ medical_log: MedicalLog }>(detail(memberId, logId), { signal });
export const createMedicalLog = (memberId: string, input: MedicalLogInput) => request<{ medical_log: MedicalLog }>(base(memberId), { method: "POST", body: JSON.stringify(input) });
export const updateMedicalLog = (memberId: string, logId: string, changes: MedicalLogChanges) => request<{ medical_log: MedicalLog }>(detail(memberId, logId), { method: "PATCH", body: JSON.stringify(changes) });
export const deleteMedicalLog = (memberId: string, logId: string) => request<{ deleted: boolean }>(detail(memberId, logId), { method: "DELETE" });
