import { request } from "./request";
import type { MedicalHistory, MedicalHistoryChanges } from "./medicalHistoryTypes";
export * from "./medicalHistoryTypes";

export const fetchMedicalHistory = (memberId: string, signal?: AbortSignal) => request<MedicalHistory>(`/members/${encodeURIComponent(memberId)}/medical-history`, { signal });
export const updateMedicalHistory = (memberId: string, changes: MedicalHistoryChanges) => request<MedicalHistory>(`/members/${encodeURIComponent(memberId)}/medical-history`, { method: "PATCH", body: JSON.stringify(changes) });
