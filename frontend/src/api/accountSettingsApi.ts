import { request } from "./request";

export function updateAccount(userName: string) {
  return request<{ account: string; user_name: string; updated_at: string }>("/auth/account", {
    method: "PATCH",
    body: JSON.stringify({ user_name: userName })
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
