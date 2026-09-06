export const SIGN_IN_PATH = "/sign_in";
export const SIGN_UP_PATH = "/sign_up";
export const APP_PATH = "/";
export const HEALTH_PATH_PREFIX = "/health/";
type HealthRoutePath = `${typeof HEALTH_PATH_PREFIX}${string}`;
export const REPORTS_PATH = "/reports";
const REPORT_PATH_PREFIX = "/reports/";
export const FAVORITES_PATH = "/favorites";
export const SETTING_PATH = "/setting";
export const CHAT_PATH_PREFIX = "/chat/";

type ChatRoutePath = `${typeof CHAT_PATH_PREFIX}${string}`;
type ReportRoutePath = `${typeof REPORT_PATH_PREFIX}${string}`;
export type RoutePath =
  | typeof SIGN_IN_PATH
  | typeof SIGN_UP_PATH
  | typeof APP_PATH
  | typeof REPORTS_PATH
  | typeof FAVORITES_PATH
  | typeof SETTING_PATH
  | HealthRoutePath
  | ChatRoutePath
  | ReportRoutePath;

export function currentRoute(): RoutePath {
  if (memberIdFromHealthPath(window.location.pathname)) {
    return window.location.pathname as HealthRoutePath;
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
  if (window.location.pathname === FAVORITES_PATH) {
    return FAVORITES_PATH;
  }
  if (window.location.pathname === REPORTS_PATH) {
    return REPORTS_PATH;
  }
  if (window.location.pathname === SETTING_PATH) {
    return SETTING_PATH;
  }
  if (window.location.pathname === SIGN_UP_PATH) {
    return SIGN_UP_PATH;
  }
  return SIGN_IN_PATH;
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
  return path === SIGN_IN_PATH || path === SIGN_UP_PATH;
}

export function healthPathForMember(memberId: string): HealthRoutePath {
  return `${HEALTH_PATH_PREFIX}${encodeURIComponent(memberId)}`;
}

export function memberIdFromHealthPath(path: string): string | null {
  if (!path.startsWith(HEALTH_PATH_PREFIX)) return null;
  try {
    const id = decodeURIComponent(path.slice(HEALTH_PATH_PREFIX.length));
    return id && !id.includes("/") ? id : null;
  } catch { return null; }
}
