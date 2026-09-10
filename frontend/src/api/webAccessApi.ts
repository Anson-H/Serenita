import { request } from "./request";
import type {
  CredentialRevealResponse,
  WebAccessSettings,
  WebProviderTestResponse
} from "./types";

export function fetchWebAccessSettings() {
  return request<WebAccessSettings>("/account-settings/web-access");
}

export function updateWebAccessSettings(patch: {
  is_enabled?: boolean;
  active_provider_id?: "tavily" | "exa";
}) {
  return request<WebAccessSettings>("/account-settings/web-access", {
    method: "PATCH",
    body: JSON.stringify(patch)
  });
}

export function updateWebProviderSettings(providerId: string, apiUrl: string) {
  return request<WebAccessSettings>(
    `/account-settings/web-access/providers/${encodeURIComponent(providerId)}`,
    {
      method: "PATCH",
      body: JSON.stringify({ api_url: apiUrl })
    }
  );
}

export function saveWebProviderCredential(providerId: string, apiKey: string) {
  return request<WebAccessSettings>(
    `/account-settings/web-access/providers/${encodeURIComponent(providerId)}/credential`,
    {
      method: "PUT",
      body: JSON.stringify({ api_key: apiKey })
    }
  );
}

export function revealWebProviderCredential(providerId: string) {
  return request<CredentialRevealResponse>(
    `/account-settings/web-access/providers/${encodeURIComponent(providerId)}/credential/reveal`,
    { method: "POST" }
  );
}

export function testWebProvider(providerId: string, apiKey?: string, signal?: AbortSignal) {
  return request<WebProviderTestResponse>(
    `/account-settings/web-access/providers/${encodeURIComponent(providerId)}/test`,
    {
      method: "POST",
      signal,
      body: JSON.stringify(apiKey ? { api_key: apiKey } : {})
    }
  );
}
