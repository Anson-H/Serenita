import { AuthResponse, AuthSession } from "./types";
import { request } from "./request";

export function checkSession() {
  return request<AuthSession>("/auth/session");
}

export function signUp(account: string, userName: string, password: string, confirmPassword: string) {
  return request<AuthResponse>("/auth/sign_up", {
    method: "POST",
    body: JSON.stringify({
      account,
      user_name: userName,
      password,
      confirm_password: confirmPassword
    })
  });
}

export function signIn(account: string, password: string) {
  return request<AuthResponse>("/auth/sign_in", {
    method: "POST",
    body: JSON.stringify({ account, password })
  });
}

export function signOut() {
  return request<{ success: boolean; message: string }>("/auth/sign_out", {
    method: "POST"
  });
}
