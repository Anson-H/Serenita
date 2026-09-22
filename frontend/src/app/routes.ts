import { isSettingsRoute, type SettingsPath } from "./settingsRoutes";
export { SETTING_PATH, isSettingsRoute } from "./settingsRoutes";

export const SIGN_IN_PATH = "/login";
export const SIGN_UP_PATH = "/register";
export const DEVICE_AUTH_PATH = "/authorize";
type DeviceAuthorizationPath = `${typeof DEVICE_AUTH_PATH}?user_code=${string}`;
type DeviceLoginPath = `${typeof SIGN_IN_PATH | typeof SIGN_UP_PATH}?user_code=${string}`;
export const APP_PATH = "/";
export const HEALTH_PATH_PREFIX = "/health/";
type HealthRoutePath = `${typeof HEALTH_PATH_PREFIX}${string}`;
export const REPORTS_PATH = "/reports";
const REPORT_PATH_PREFIX = "/reports/";
export const NOTIFICATIONS_PATH = "/notifications";
export const KNOWLEDGE_PATH = "/knowledge";
export const FAVORITES_PATH = "/favorites";
export const NOT_FOUND_PATH = "/404";
export const CHAT_PATH_PREFIX = "/chat/";

type ChatRoutePath = `${typeof CHAT_PATH_PREFIX}${string}`;
type ReportRoutePath = `${typeof REPORT_PATH_PREFIX}${string}`;
export type RoutePath =
  | DeviceLoginPath
  | DeviceAuthorizationPath
  | typeof DEVICE_AUTH_PATH
  | typeof NOT_FOUND_PATH
  | typeof SIGN_IN_PATH
  | typeof SIGN_UP_PATH
  | typeof APP_PATH
  | typeof REPORTS_PATH
  | typeof NOTIFICATIONS_PATH
  | typeof KNOWLEDGE_PATH
  | typeof FAVORITES_PATH
  | SettingsPath
  | HealthRoutePath
  | ChatRoutePath
  | ReportRoutePath;

export function currentRoute(): RoutePath {
  if (memberIdFromHealthPath(window.location.pathname)) {
    return (window.location.pathname + window.location.search) as HealthRoutePath;
  }
  if (window.location.pathname.startsWith(CHAT_PATH_PREFIX)) {
    return window.location.pathname as ChatRoutePath;
  }
  if (reportIdFromReportPath(window.location.pathname)) {
    return window.location.pathname as ReportRoutePath;
  }
  if (window.location.pathname === APP_PATH) {
    return APP_PATH;
  }
  if (window.location.pathname === NOTIFICATIONS_PATH) return NOTIFICATIONS_PATH;
  if (window.location.pathname === KNOWLEDGE_PATH) return KNOWLEDGE_PATH;
  if (window.location.pathname === FAVORITES_PATH) {
    return FAVORITES_PATH;
  }
  if (window.location.pathname === REPORTS_PATH) {
    return REPORTS_PATH;
  }
  if (isSettingsRoute(window.location.pathname)) {
    return window.location.pathname;
  }
  if (window.location.pathname === DEVICE_AUTH_PATH) {
    const code = new URLSearchParams(window.location.search).get("user_code");
    return code ? deviceAuthorizationPath(code) : DEVICE_AUTH_PATH;
  }
  if (window.location.pathname === SIGN_UP_PATH || window.location.pathname === SIGN_IN_PATH) {
    const code = new URLSearchParams(window.location.search).get("user_code");
    return code ? deviceLoginPath(window.location.pathname, code) : window.location.pathname;
  }
  return NOT_FOUND_PATH;
}

export function chatPathForSession(sessionId: string): ChatRoutePath {
  return `${CHAT_PATH_PREFIX}${encodeURIComponent(sessionId)}` as ChatRoutePath;
}

export function reportPathForReport(reportId: string, memberId: string): ReportRoutePath {
  return `${REPORT_PATH_PREFIX}${encodeURIComponent(memberId)}/${encodeURIComponent(reportId)}` as ReportRoutePath;
}

export function memberIdFromReportPath(path: string): string | null {
  if (!path.startsWith(REPORT_PATH_PREFIX)) return null;
  const pieces = path.slice(REPORT_PATH_PREFIX.length).split("/");
  if (pieces.length !== 2 || !pieces[0] || !pieces[1]) return null;
  try { const id = decodeURIComponent(pieces[0]); return id.includes("/") ? null : id; } catch { return null; }
}

export function reportIdFromReportPath(path: string) {
  if (!path.startsWith(REPORT_PATH_PREFIX)) {
    return null;
  }
  if (!memberIdFromReportPath(path)) return null;
  const encodedReportId = path.slice(REPORT_PATH_PREFIX.length).split("/")[1];
  if (!encodedReportId || encodedReportId.includes("/")) {
    return null;
  }
  try {
    const reportId = decodeURIComponent(encodedReportId);
    return reportId && !reportId.includes("/") ? reportId : null;
  } catch {
    return null;
  }
}

export function isReportRoute(path: RoutePath) {
  return path === REPORTS_PATH || reportIdFromReportPath(path) !== null;
}

export function sessionIdFromChatPath(path: string) {
  if (!path.startsWith(CHAT_PATH_PREFIX)) {
    return null;
  }
  const encodedSessionId = path.slice(CHAT_PATH_PREFIX.length);
  if (!encodedSessionId) {
    return null;
  }
  try {
    return decodeURIComponent(encodedSessionId);
  } catch {
    return encodedSessionId;
  }
}

export function isAuthRoute(path: RoutePath) {
  const pathname = path.split("?")[0];
  return pathname === SIGN_IN_PATH || pathname === SIGN_UP_PATH;
}

export function deviceLoginPath(path: typeof SIGN_IN_PATH | typeof SIGN_UP_PATH, code: string): DeviceLoginPath {
  return `${path}?user_code=${encodeURIComponent(code)}`;
}

export function deviceAuthorizationPath(code: string): DeviceAuthorizationPath {
  return `${DEVICE_AUTH_PATH}?user_code=${encodeURIComponent(code)}`;
}

export function healthPathForMember(memberId: string): HealthRoutePath {
  return `${HEALTH_PATH_PREFIX}${encodeURIComponent(memberId)}`;
}

export function medicalLogPath(memberId: string, logId?: string): HealthRoutePath {
  return `${HEALTH_PATH_PREFIX}${encodeURIComponent(memberId)}/medical-logs${logId ? `/${encodeURIComponent(logId)}` : ""}`;
}

function healthParts(path: string): string[] | null {
  if (!path.startsWith(HEALTH_PATH_PREFIX)) return null;
  try {
    const parts = path.split("?")[0].slice(HEALTH_PATH_PREFIX.length).split("/").map(decodeURIComponent);
    if (parts.some(part => !part || part.includes("/"))) return null;
    if ((parts.length === 2 || parts.length === 3) && parts[1] === "body-metrics") return parts;
    if (parts.length === 2 && parts[1] === "memory") return parts;
    if (parts.length >= 3 && parts.length <= 4 && parts[1] === "medications" && ["plans", "catalog"].includes(parts[2])) return parts;
    if (parts.length === 6 && parts[1] === "medications" && parts[2] === "catalog" && parts[4] === "batches") return parts;
    if (parts.length === 1 || ((parts.length === 2 || parts.length === 3) && parts[1] === "medical-logs")) return parts;
  } catch { return null; }
  return null;
}

export function memberIdFromHealthPath(path: string): string | null { return healthParts(path)?.[0] ?? null; }
export function memoryPath(memberId: string): HealthRoutePath { return `${HEALTH_PATH_PREFIX}${encodeURIComponent(memberId)}/memory`; }
export function isMemoryRoute(path: string) { return healthParts(path)?.[1] === "memory"; }
export function isMedicalLogRoute(path: string) { return healthParts(path)?.[1] === "medical-logs"; }
export function medicalLogIdFromPath(path: string): string | null { return healthParts(path)?.[2] ?? null; }

export function medicationPath(memberId: string, section: "catalog" | "plans" = "catalog", id?: string): HealthRoutePath {
  return `${HEALTH_PATH_PREFIX}${encodeURIComponent(memberId)}/medications/${section}${id ? `/${encodeURIComponent(id)}` : ""}`;
}
export function medicationBatchPath(memberId:string,medicationId:string,batchId:string):HealthRoutePath {
  return `${medicationPath(memberId,'catalog',medicationId)}/batches/${encodeURIComponent(batchId)}`;
}
export function medicationRoute(path: string): {section: "catalog" | "plans"; id?: string; batchId?: string} | null {
  const parts=healthParts(path);
  return parts?.[1] === "medications" ? {section:parts[2] as "catalog" | "plans",id:parts[3],batchId:parts[5]} : null;
}

export function bodyMetricPath(memberId:string,category?:string):HealthRoutePath {return `${HEALTH_PATH_PREFIX}${encodeURIComponent(memberId)}/body-metrics${category?'/'+encodeURIComponent(category):''}`;}
export function isBodyMetricRoute(path:string){return healthParts(path)?.[1]==='body-metrics';}
export function bodyMetricCategory(path:string):string|null {return isBodyMetricRoute(path)?healthParts(path)?.[2]??null:null;}
