import { parentSettingsPath, settingsPath, SETTING_PATH, type SettingsLocation, type SettingsPath } from "../../app/settingsRoutes";
import type { AccountPanel, ConversationSettingsSection, SettingsMobileLayer, SettingsSection } from "./settingsTypes";

export function createSettingsNavigationActions({ location, local, onNavigate }: {
  location: SettingsLocation;
  local: boolean;
  onNavigate: (path: SettingsPath) => void;
}) {
  const activeSection: SettingsSection = location.section === "root" ? local ? "providers" : "account"
    : location.section === "notifications" ? "account" : location.section;
  const accountPanel: AccountPanel = location.section === "account" ? location.panel : location.section === "notifications" ? "notifications" : "profile";
  const conversationSection = location.section === "conversation" ? location.page ?? "composer" : "composer";
  const mobileLayer: SettingsMobileLayer = location.section === "providers" ? "provider-list" : location.section === "conversation" ? "conversation-list" : "root";
  const detailOpen = location.section !== "root"
    && !(location.section === "providers" && !location.providerId)
    && !(location.section === "conversation" && !location.page);
  const selectedProviderId = location.section === "providers" ? location.providerId ?? "" : "";
  const navigate = (target: SettingsLocation) => onNavigate(settingsPath(target));
  return {
    activeSection, accountPanel, conversationSection, mobileLayer, detailOpen, selectedProviderId,
    selectAccountPanel: (panel: AccountPanel) => navigate(panel === "notifications" ? { section: "notifications" } : { section: "account", panel }),
    selectProvidersRoot: () => navigate({ section: "providers", page: "root" }),
    selectProvider: (providerId: string) => navigate({ section: "providers", providerId, page: "root" }),
    selectDefaultsRoot: () => navigate({ section: "defaults" }),
    selectConversationRoot: () => navigate({ section: "conversation" }),
    selectConversationSection: (page: ConversationSettingsSection) => navigate({ section: "conversation", page }),
    selectThemeRoot: () => navigate({ section: "theme" }),
    selectMemoryRoot: () => navigate({ section: "memory", page: "root" }),
    selectMembersRoot: () => navigate({ section: "members" }),
    selectWebRoot: () => navigate({ section: "web" }),
    closeSettingsDetail: () => onNavigate(parentSettingsPath(location)),
    goBackSettingsLayer: () => onNavigate(SETTING_PATH),
    settingsMobileLayerTitle: () => mobileLayer === "provider-list" ? "模型提供方" : mobileLayer === "conversation-list" ? "聊天设置" : local ? "设置" : "账号设置",
  };
}
