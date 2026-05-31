export type SettingsSection = "account" | "providers" | "defaults";
export type AccountPanel = "profile" | "password";
export type DefaultModelUsage = "chat" | "title" | "vision_parse" | "compact";
export type SettingsMobileLayer =
  | "root"
  | "provider-list"
  | "default-models"
  | "account-profile"
  | "account-password"
  | "provider-detail";

export type ProviderDraft = {
  officialUrl: string;
  baseUrl: string;
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

export const accountAutoSaveDelayMs = 650;

export function draftsMatch(left?: ProviderDraft, right?: ProviderDraft) {
  return (
    Boolean(left && right) &&
    left?.officialUrl === right?.officialUrl &&
    left?.baseUrl === right?.baseUrl &&
    left?.apiKey === right?.apiKey
  );
}

export const userNameSpacePattern = /\s/;
