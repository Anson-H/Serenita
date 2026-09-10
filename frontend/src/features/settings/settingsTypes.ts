export type SettingsSection =
  | "theme"
  | "members"
  | "account"
  | "providers"
  | "defaults"
  | "conversation"
  | "web"
  | "lab-categories"
  | "lab-items"
  | "medication-catalog";
export type AccountPanel = "profile" | "password" | "grants" | "notifications";
export type DefaultModelUsage = "chat" | "title" | "vision_parse" | "compact" | "text_embedding" | "multimodal_embedding";
export type ConversationSettingsSection =
  | "composer"
  | "response";
export type LabCatalog = "categories" | "items";
export type SettingsMobileLayer =
  | "root"
  | "provider-list"
  | "conversation-list"
  | "dictionary-list";

export type ProviderDraft = {
  officialUrl: string;
  apiUrl: string;
  apiKey: string;
};

export type TestState = {
  status: "idle" | "saving" | "testing" | "success" | "error";
  message: string;
};

export type ProviderConnectionTestState = {
  status: "idle" | "testing" | "success" | "error";
  message: string;
};

export const settingsAutoSaveDelayMs = 650;
export const accountIdentifierPattern = /^[A-Za-z0-9_-]{1,20}$/;

export function draftsMatch(left?: ProviderDraft, right?: ProviderDraft) {
  return (
    Boolean(left && right) &&
    left?.officialUrl === right?.officialUrl &&
    left?.apiUrl === right?.apiUrl &&
    left?.apiKey === right?.apiKey
  );
}

export function accountNameLength(value: string) {
  return Array.from(value).length;
}
