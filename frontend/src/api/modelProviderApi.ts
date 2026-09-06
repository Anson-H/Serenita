import { SerialTasks } from "../utils/serialTasks";
import { captureAuthContext, isAuthContextCurrent } from "./authLifecycle";

const defaultWrites = new SerialTasks();

import { request } from "./request";
import {
  AddedModel,
  CredentialRevealResponse,
  ModelCapabilityProbeResponse,
  ModelDefaultsResponse,
  ModelUpdatePayload,
  ProviderListResponse,
  ProviderSummary,
  ProviderTestResponse,
  RemoteModel
} from "./types";

export function fetchModelProviders() {
  return request<ProviderListResponse>("/model-providers");
}

export function revealModelProviderCredential(providerId: string) {
  return request<CredentialRevealResponse>(
    `/model-providers/${encodeURIComponent(providerId)}/credential/reveal`,
    { method: "POST" }
  );
}

export function saveModelProvider(
  providerId: string,
  apiUrl: string,
  officialUrl: string,
  apiKey: string
) {
  const payload: {
    provider_id: string;
    api_url: string;
    official_url: string;
    api_key?: string;
  } = {
    provider_id: providerId,
    api_url: apiUrl,
    official_url: officialUrl
  };
  if (apiKey.trim()) {
    payload.api_key = apiKey.trim();
  }
  return request<ProviderSummary>("/model-providers", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function testModelProvider(providerId: string, apiUrl: string, apiKey: string) {
  const payload: { api_url: string; api_key?: string } = { api_url: apiUrl };
  if (apiKey.trim()) {
    payload.api_key = apiKey.trim();
  }
  return request<ProviderTestResponse>(`/model-providers/${providerId}/test`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function fetchProviderModels(providerId: string) {
  return request<{ provider_id: string; models: RemoteModel[] }>(
    `/model-providers/${providerId}/models`
  );
}

export function addModel(
  providerId: string,
  remoteModelId: string,
  model: RemoteModel
) {
  return request<AddedModel>("/models", {
    method: "POST",
    body: JSON.stringify({
      provider_id: providerId,
      remote_model_id: remoteModelId,
      thinking_modes: model.thinking_modes,
      capability_profiles: model.capability_profiles,
      context_window_tokens: model.context_window_tokens,
      max_output_tokens: model.max_output_tokens
    })
  });
}

export function fetchModels() {
  return request<{ models: AddedModel[] }>("/models");
}

export function updateModel(modelId: string, payload: ModelUpdatePayload) {
  return request<AddedModel>(`/models/${encodeURIComponent(modelId)}`, {
    method: "PATCH",
    body: JSON.stringify(payload)
  });
}

export function probeModelCapabilities(modelId: string, signal?: AbortSignal) {
  return request<ModelCapabilityProbeResponse>(
    `/models/capability-probe/${encodeURIComponent(modelId)}`,
    { method: "POST", signal }
  );
}

export function fetchModelDefaults() {
  return request<ModelDefaultsResponse>("/model-access-settings");
}

export function updateModelDefaults(defaults: Partial<Record<keyof ModelDefaultsResponse["defaults"], string | null>>) {
  const context = captureAuthContext();
  return defaultWrites.run(`defaults:${context.generation}`, () => request<ModelDefaultsResponse>("/model-access-settings", {
    method: "PATCH",
    body: JSON.stringify(defaults)
  }), () => isAuthContextCurrent(context));
}

export function deleteModel(modelId: string) {
  return request<{ model_id: string; deleted: boolean }>(`/models/${encodeURIComponent(modelId)}`, {
    method: "DELETE"
  });
}
