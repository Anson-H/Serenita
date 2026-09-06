import { request } from "./request";
import type { AuthenticatedSession, AuthSession } from "./types";

export function checkSession() {
  return request<AuthSession>("/auth/session");
}

export function signUp(account: string, accountName: string, password: string, confirmPassword: string) {
  return request<AuthenticatedSession>("/auth/sign_up", {
    method: "POST",
    body: JSON.stringify({
      account,
      account_name: accountName,
      password,
      confirm_password: confirmPassword
    })
  });
}

export function signIn(account: string, password: string) {
  return request<AuthenticatedSession>("/auth/sign_in", {
    method: "POST",
    body: JSON.stringify({ account, password })
  });
}

export function signOut() {
  return request<{ success: boolean; message: string }>("/auth/sign_out", {
    method: "POST"
  });
}
