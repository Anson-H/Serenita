import { captureAuthContext, subscribeAuthLifecycle } from "../../api/authLifecycle";
import type { MedicalLogFilters } from "../../api/medicalLogApi";
type Position = { filters: MedicalLogFilters; scrollTop: number };
const positions = new Map<string, Position>();
subscribeAuthLifecycle(() => positions.clear());
const key = (memberId: string) => `${captureAuthContext().accountId}:${memberId}`;
export const medicalLogPosition = (memberId: string): Position => positions.get(key(memberId)) ?? { filters: { query: "" }, scrollTop: 0 };
export const saveMedicalLogPosition = (memberId: string, position: Position) => { positions.set(key(memberId), position); };
