import { SerialTasks } from "../utils/serialTasks";
import { captureAuthContext, isAuthContextCurrent } from "./authLifecycle";

const defaultWrites = new SerialTasks();

import { request } from "./request";
import {
  AddedModel,
  CredentialRevealResponse,
  ModelDefaultsResponse,
  ModelUpdatePayload,
  ProviderListResponse,
  ProviderSummary,
  ProviderTestResponse,
  ModelCapabilityProbeResponse,
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

export function testModelProvider(providerId: string, apiUrl: string, apiKey: string, signal?: AbortSignal) {
  const payload: { api_url: string; api_key?: string } = { api_url: apiUrl };
  if (apiKey.trim()) {
    payload.api_key = apiKey.trim();
  }
  return request<ProviderTestResponse>(`/model-providers/${providerId}/test`, {
    signal,
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
  _model: RemoteModel
) {
  return request<AddedModel>("/models", {
    method: "POST",
    body: JSON.stringify({
      provider_id: providerId,
      remote_model_id: remoteModelId
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

const activeProbeIds = new Map<string, string>();

export async function probeModelCapabilities(modelId: string, signal?: AbortSignal) {
  if (signal?.aborted) throw new DOMException("检测已取消", "AbortError");
  const probeId = crypto.randomUUID();
  activeProbeIds.set(modelId, probeId);
  const cancel = () => { void cancelModelCapabilityProbe(modelId, probeId).catch(() => {}); };
  signal?.addEventListener("abort", cancel, { once: true });
  try {
    return await request<ModelCapabilityProbeResponse>(
      `/models/capability-probe/${encodeURIComponent(modelId)}`,
      { method: "POST", signal, body: JSON.stringify({ probe_id: probeId }) }
    );
  } finally {
    signal?.removeEventListener("abort", cancel);
    if (activeProbeIds.get(modelId) === probeId) activeProbeIds.delete(modelId);
  }
}

export function cancelModelCapabilityProbe(modelId: string, probeId = activeProbeIds.get(modelId)) {
  return request(`/models/capability-probe-cancel/${encodeURIComponent(modelId)}`, { method: "POST", body: JSON.stringify({ probe_id: probeId }) });
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
