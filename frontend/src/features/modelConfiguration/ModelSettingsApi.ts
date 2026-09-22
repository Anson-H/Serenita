import { createContext, useContext } from "react";
import type {
  AddedModel, CredentialRevealResponse, ModelCapabilityProbeResponse,
  ModelUpdatePayload, ProviderListResponse, ProviderSummary, ProviderTestResponse, RemoteModel,
} from "../../api/models/modelTypes";
export type CustomProviderInput = { provider_name: string; api_url: string; official_url: string; api_key?: string };
/** Model configuration contract shared by the health and administrator workspaces. */
export interface ModelSettingsApi {
  fetchModelProviders(): Promise<ProviderListResponse>;
  revealModelProviderCredential(providerId: string): Promise<CredentialRevealResponse>;
  saveModelProvider(providerId: string, apiUrl: string, officialUrl: string, apiKey: string): Promise<ProviderSummary>;
  testModelProvider(providerId: string, apiUrl: string, apiKey: string, signal?: AbortSignal): Promise<ProviderTestResponse>;
  fetchProviderModels(providerId: string): Promise<{ provider_id: string; models: RemoteModel[] }>;
  addModel(providerId: string, remoteModelId: string, model: RemoteModel): Promise<AddedModel>;
  updateModel(modelId: string, payload: ModelUpdatePayload): Promise<AddedModel>;
  deleteModel(modelId: string): Promise<{ model_id: string; deleted: boolean }>;
  probeModelCapabilities(modelId: string, signal?: AbortSignal): Promise<ModelCapabilityProbeResponse>;
  saveCustomProvider(providerId: string | undefined, input: CustomProviderInput): Promise<ProviderSummary>;
  deleteCustomProvider(providerId: string): Promise<unknown>;
}

export const ModelSettingsApiContext = createContext<ModelSettingsApi | null>(null);
export function useModelSettingsApi() {
  const api = useContext(ModelSettingsApiContext);
  if (!api) throw new Error("模型设置接口尚未装配。");
  return api;
}
