import { request } from "../transport/request";
import type { ModelDefaults } from "./modelTypes";

export const modelConfigurationChanged = () => window.dispatchEvent(new Event("serenita:model-configuration-changed"));
export type ConnectionStatus = {
  deployment_mode: "official" | "self_hosted";
  api_url: string;
  service_available: boolean;
  connected: boolean;
  connection_error?: string | null;
  account_name: string | null;
  expires_at: string | null;
  onboarding_status: "pending" | "completed" | "skipped";
  needs_onboarding: boolean;
  readiness: Record<keyof ModelDefaults, { ready: boolean; model_id: string | null; reason: string | null }>;
  user_code: string | null;
  verification_uri: string | null;
  device_expires_at: string | null;
  next_poll_at: string | null;
  authorization_status?: string;
  authorization_error?: string | null;
};
export const connectionStatus = () => request<ConnectionStatus>("/serenita-connection");
export const chooseModels = (choice: "serenita" | "own_api" | "later") => request<ConnectionStatus>("/model-onboarding", { method: "POST", body: JSON.stringify({ choice }) });
export const authorizeModels = () => request<ConnectionStatus>("/serenita-connection/authorize", { method: "POST" });
export const pollAuthorization = (userCode: string) => request<ConnectionStatus>("/serenita-connection/poll", { method: "POST", body: JSON.stringify({ user_code: userCode }) });
export const disconnectModels = () => request<{ remote_revoked: boolean }>("/serenita-connection", { method: "DELETE" });
