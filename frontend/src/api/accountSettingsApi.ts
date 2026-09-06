import { request } from "./request";
import type { AuthenticatedSession, ConversationPreferences } from "./types";

export function updateAccount(account: string, accountName: string) {
  return request<AuthenticatedSession>("/auth/account", {
    method: "PATCH",
    body: JSON.stringify({ account, account_name: accountName })
  });
}

export function changePassword(currentPassword: string, newPassword: string, confirmPassword: string) {
  return request<{ success: boolean; message: string }>("/auth/password", {
    method: "PATCH",
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
      confirm_password: confirmPassword
    })
  });
}

export function fetchConversationPreferences() {
  return request<ConversationPreferences>("/account-settings/conversation-preferences");
}

export function replaceConversationPreferences(preferences: ConversationPreferences) {
  return request<ConversationPreferences>("/account-settings/conversation-preferences", {
    method: "PUT",
    body: JSON.stringify(preferences)
  });
}
