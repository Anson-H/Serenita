import type { AccountPanel, ConversationSettingsSection } from "../features/settings/settingsTypes";

export const SETTING_PATH = "/setting";
export type SettingsPath = typeof SETTING_PATH | `${typeof SETTING_PATH}/${string}`;
export type SettingsLocation =
  | { section: "root" }
  | { section: "account"; panel: Exclude<AccountPanel, "notifications"> }
  | { section: "notifications" | "defaults" | "web" | "theme" | "members" }
  | { section: "conversation"; page?: ConversationSettingsSection }
  | { section: "memory"; memberId?: string; page: "root" | "formation" }
  | { section: "providers"; providerId?: string; modelId?: string; page: "root" | "thinking" | "inputOutput" };

export function settingsPath(location: SettingsLocation): SettingsPath {
  const base = SETTING_PATH;
  if (location.section === "root") return base;
  if (location.section === "account") return `${base}/account/${location.panel}`;
  if (location.section === "conversation") return `${base}/conversation${location.page ? `/${location.page}` : ""}`;
  if (location.section === "memory") return `${base}/memory${location.memberId ? `/members/${encodeURIComponent(location.memberId)}` : ""}${location.page === "formation" ? "/formation" : ""}`;
  if (location.section === "providers") {
    if (!location.providerId) return `${base}/providers`;
    const provider = `${base}/providers/${encodeURIComponent(location.providerId)}` as const;
    if (!location.modelId) return provider;
    return `${provider}/models/${encodeURIComponent(location.modelId)}${location.page === "root" ? "" : location.page === "inputOutput" ? "/input-output" : "/thinking"}`;
  }
  return `${base}/${location.section}`;
}

export function readSettingsRoute(path: string): SettingsLocation | null {
  if (path === SETTING_PATH) return { section: "root" };
  if (!path.startsWith(`${SETTING_PATH}/`)) return null;
  let parts: string[];
  try {
    parts = path.slice(SETTING_PATH.length + 1).split("/").map(decodeURIComponent);
    if (parts.some((part, index) => {
      if (!part || part === "." || part === "..") return true;
      // Model identifiers are opaque values encoded within one URL segment.
      const modelId = parts[0] === "providers" && parts[2] === "models" && index === 3;
      return !modelId && /[/?#]/.test(part);
    })) return null;
  } catch { return null; }
  const [section, detail, kind, id, page] = parts;
  if (["notifications", "defaults", "web", "theme", "members"].includes(section) && parts.length === 1) {
    return { section: section as "notifications" | "defaults" | "web" | "theme" | "members" };
  }
  if (section === "account" && parts.length === 2 && ["profile", "password", "grants"].includes(detail)) {
    return { section, panel: detail as Exclude<AccountPanel, "notifications"> };
  }
  if (section === "conversation" && (parts.length === 1 || (parts.length === 2 && ["composer", "response"].includes(detail)))) {
    return { section, page: detail as ConversationSettingsSection | undefined };
  }
  if (section === "memory") {
    if (parts.length === 1 || (parts.length === 2 && detail === "formation")) return { section, page: detail === "formation" ? "formation" : "root" };
    if (detail === "members" && (parts.length === 3 || (parts.length === 4 && id === "formation"))) {
      return { section, memberId: kind, page: id === "formation" ? "formation" : "root" };
    }
  }
  if (section === "providers") {
    if (parts.length <= 2) return { section, providerId: detail, page: "root" };
    if (kind === "models" && (parts.length === 4 || (parts.length === 5 && ["thinking", "input-output"].includes(page)))) {
      return { section, providerId: detail, modelId: id, page: page === "input-output" ? "inputOutput" : page === "thinking" ? "thinking" : "root" };
    }
  }
  return null;
}

export function isSettingsRoute(path: string): path is SettingsPath {
  return readSettingsRoute(path) !== null;
}

export function parentSettingsPath(location: SettingsLocation): SettingsPath {
  if (location.section === "providers") {
    if (location.modelId && location.page !== "root") return settingsPath({ ...location, page: "root" });
    if (location.modelId) return settingsPath({ section: "providers", providerId: location.providerId, page: "root" });
    if (location.providerId) return settingsPath({ section: "providers", page: "root" });
  }
  if (location.section === "conversation" && location.page) return settingsPath({ section: "conversation" });
  if (location.section === "memory" && location.page !== "root") return settingsPath({ ...location, page: "root" });
  return SETTING_PATH;
}
