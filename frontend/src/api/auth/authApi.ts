import { request } from "../transport/request";
import type { AuthenticatedSession, AuthSession } from "../types";

export function checkSession() {
  return request<AuthSession>("/auth/session");
}

export function signUp(account: string, accountName: string, password: string, confirmPassword: string, userCode?: string) {
  return request<AuthenticatedSession>(userCode ? "/serenita/device/sign_up" : "/auth/sign_up", {
    method: "POST",
    body: JSON.stringify({
      account,
      account_name: accountName,
      password,
      confirm_password: confirmPassword,
      ...(userCode ? { user_code: userCode } : {})
    })
  });
}

export function signIn(account: string, password: string, userCode?: string) {
  return request<AuthenticatedSession>(userCode ? "/serenita/device/sign_in" : "/auth/sign_in", {
    method: "POST",
    body: JSON.stringify({ account, password, ...(userCode ? { user_code: userCode } : {}) })
  });
}

export function signOut() {
  return request<{ success: boolean; message: string }>("/auth/sign_out", {
    method: "POST"
  });
}
