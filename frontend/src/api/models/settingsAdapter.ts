import type { ModelSettingsApi } from "../../features/modelConfiguration/ModelSettingsApi";
import type { ProviderSummary } from "./modelTypes";
import {
  addModel, deleteModel, fetchModelProviders, fetchProviderModels,
  probeModelCapabilities, revealModelProviderCredential, saveModelProvider,
  testModelProvider, updateModel,
} from "./modelProviderApi";
import { request } from "../transport/request";

export const clientModelSettingsApi: ModelSettingsApi = {
  addModel, deleteModel, fetchModelProviders, fetchProviderModels,
  probeModelCapabilities, revealModelProviderCredential, saveModelProvider,
  testModelProvider, updateModel,
  saveCustomProvider: (id, input) => request<ProviderSummary>(id ? `/model-providers/${id}` : "/model-providers", {
    method: id ? "PATCH" : "POST", body: JSON.stringify(id ? { provider_name: input.provider_name } : input),
  }),
  deleteCustomProvider: id => request(`/model-providers/${id}`, { method: "DELETE" }),
};
