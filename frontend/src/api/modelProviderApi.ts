import {
  AddedModel,
  ModelDefaultsResponse,
  ProviderListResponse,
  ProviderSummary,
  ProviderTestResponse,
  RemoteModel
} from "./types";
import { request } from "./request";

export function fetchModelProviders() {
  return request<ProviderListResponse>("/model-providers");
}

export function saveModelProvider(
  providerId: string,
  baseUrl: string,
  officialUrl: string,
  apiKey: string,
  makeDefault: boolean
) {
  return request<ProviderSummary>("/model-providers", {
    method: "POST",
    body: JSON.stringify({
      provider_id: providerId,
      base_url: baseUrl,
      official_url: officialUrl,
      api_key: apiKey,
      default: makeDefault
    })
  });
}

export function updateModelProvider(
  providerId: string,
  baseUrl: string,
  officialUrl: string,
  apiKey: string,
  makeDefault: boolean
) {
  return request<ProviderSummary>(`/model-providers/${providerId}`, {
    method: "PATCH",
    body: JSON.stringify({
      base_url: baseUrl,
      official_url: officialUrl,
      api_key: apiKey,
      default: makeDefault
    })
  });
}

export function testModelProvider(providerId: string, baseUrl: string, apiKey: string) {
  return request<ProviderTestResponse>(`/model-providers/${providerId}/test`, {
    method: "POST",
    body: JSON.stringify({ base_url: baseUrl, api_key: apiKey })
  });
}

export function fetchProviderModels(providerId: string) {
  return request<{ account: string; provider_id: string; models: RemoteModel[] }>(
    `/model-providers/${providerId}/models`
  );
}

export function addModel(
  providerId: string,
  remoteModelId: string,
  modelName: string,
  model: RemoteModel
) {
  return request<AddedModel>("/models", {
    method: "POST",
    body: JSON.stringify({
      provider_id: providerId,
      remote_model_id: remoteModelId,
      model_name: modelName,
      supports_text: model.supports_text,
      file_mime_types: model.file_mime_types,
      thinking_modes: model.thinking_modes,
      supports_tool_calling: model.supports_tool_calling,
      supports_json_output: model.supports_json_output,
      context_window_tokens: model.context_window_tokens,
      max_output_tokens: model.max_output_tokens
    })
  });
}

export function fetchModels() {
  return request<{ models: AddedModel[] }>("/models");
}

export function fetchModelDefaults() {
  return request<ModelDefaultsResponse>("/model-defaults");
}

export function updateModelDefaults(defaults: Partial<Record<keyof ModelDefaultsResponse["defaults"], string | null>>) {
  return request<ModelDefaultsResponse>("/model-defaults", {
    method: "PATCH",
    body: JSON.stringify(defaults)
  });
}

export function deleteModel(modelId: string) {
  return request<{ model_id: string; deleted: boolean }>(`/models/${encodeURIComponent(modelId)}`, {
    method: "DELETE"
  });
}
