import type { Dispatch, RefObject, SetStateAction } from "react";
import {
  AddedModel,
  ModelDefaults,
  ModelUpdatePayload,
  ProviderSummary,
  RemoteModel,
  apiClient
} from "../../api/client";
import { showStatusNotification } from "../../components/StatusNotificationCenter";
import { capabilityProbeSummary } from './modelProbePresentation';
import {
  type ProviderDraft,
  type TestState
} from "./settingsTypes";

type Dependencies = {
  selectedProvider: ProviderSummary | undefined;
  selectedDraft: ProviderDraft | undefined;
  setModelPickerOpen: Dispatch<SetStateAction<boolean>>;
  setModelPickerLoading: Dispatch<SetStateAction<boolean>>;
  setModelPickerError: Dispatch<SetStateAction<string>>;
  setRemoteModels: Dispatch<SetStateAction<RemoteModel[]>>;
  autoSaveProviderDraft: (providerId: string, draft: ProviderDraft) => Promise<void>;
  setTestStates: Dispatch<SetStateAction<Record<string, TestState>>>;
  setAddingRemoteModelIds: Dispatch<SetStateAction<string[]>>;
  setAddedModels: (next: SetStateAction<AddedModel[]>) => void;
  chatDefaultModelId: string;
  setModelDefaults: (next: SetStateAction<ModelDefaults>) => void;
  modelProbeAbortControllersRef: RefObject<Map<string, AbortController>>;
  setProbingModelIds: Dispatch<SetStateAction<string[]>>;
  publishModelCatalog: (models: AddedModel[], defaults: ModelDefaults) => void;
  setSavingModelIds: Dispatch<SetStateAction<string[]>>;
};

export function createModelSettingsActions({
  selectedProvider,
  selectedDraft,
  setModelPickerOpen,
  setModelPickerLoading,
  setModelPickerError,
  setRemoteModels,
  autoSaveProviderDraft,
  setTestStates,
  setAddingRemoteModelIds,
  setAddedModels,
  chatDefaultModelId,
  setModelDefaults,
  modelProbeAbortControllersRef,
  setProbingModelIds,
  publishModelCatalog,
  setSavingModelIds
}: Dependencies) {
  async function openAddModelModal() {
    if (!selectedProvider || !selectedDraft) {
      return;
    }
    setModelPickerOpen(true);
    await loadRemoteModels();
  }

  async function loadRemoteModels() {
    if (!selectedProvider || !selectedDraft) {
      return;
    }
    const providerId = selectedProvider.provider_id;
    setModelPickerLoading(true);
    setModelPickerError("");
    setRemoteModels([]);
    try {
      await autoSaveProviderDraft(providerId, selectedDraft);
      const result = await apiClient.fetchProviderModels(providerId);
      setRemoteModels(result.models);
      setTestStates((current) => ({
        ...current,
        [providerId]: {
          status: "success",
          message: "已加载。"
        }
      }));
    } catch (error) {
      const message = error instanceof Error ? error.message : "模型列表加载失败。";
      setModelPickerError(message);
      setTestStates((current) => ({
        ...current,
        [providerId]: {
          status: "error",
          message
        }
      }));
    } finally {
      setModelPickerLoading(false);
    }
  }

  function retryLoadRemoteModels() {
    void loadRemoteModels();
  }

  async function addRemoteModel(model: RemoteModel) {
    if (!selectedProvider) {
      return;
    }
    const providerId = selectedProvider.provider_id;
    setAddingRemoteModelIds((current) => [...new Set([...current, model.remote_model_id])]);
    let addedModel: AddedModel;
    try {
      addedModel = await apiClient.addModel(
        providerId,
        model.remote_model_id,
        model
      );
    } catch (error) {
      setTestStates((current) => ({
        ...current,
        [providerId]: {
          status: "error",
          message: error instanceof Error ? error.message : "模型保存失败。"
        }
      }));
      return;
    } finally {
      setAddingRemoteModelIds((current) => current.filter((id) => id !== model.remote_model_id));
    }

    setAddedModels((current) => [
      ...current.filter((item) => item.model_id !== addedModel.model_id),
      addedModel
    ]);
    setTestStates((current) => ({
      ...current,
      [providerId]: {
        status: "success",
        message: "模型已添加，正在识别能力。"
      }
    }));
    showStatusNotification({
      id: `model-add-${addedModel.model_id}`,
      message: "已加入模型列表，能力识别将在提供方详情中继续进行。",
      title: "模型已添加",
      tone: "success"
    });
    void probeAddedModel(addedModel.model_id);

    try {
      if (!chatDefaultModelId) {
        const defaultsResponse = await apiClient.updateModelDefaults({
          chat: addedModel.model_id
        });
        setModelDefaults(defaultsResponse.defaults);
      }

    } catch (error) {
      showStatusNotification({
        id: `model-add-refresh-${addedModel.model_id}`,
        message: error instanceof Error ? error.message : "模型列表刷新失败。",
        title: "模型已添加，配置刷新未完成",
        tone: "warning"
      });
    }
  }

  async function probeAddedModel(modelId: string) {
    modelProbeAbortControllersRef.current.get(modelId)?.abort();
    const abortController = new AbortController();
    modelProbeAbortControllersRef.current.set(modelId, abortController);
    setProbingModelIds((current) => [...new Set([...current, modelId])]);
    try {
      const result = await apiClient.probeModelCapabilities(
        modelId,
        abortController.signal
      );
      if (abortController.signal.aborted) return;
      const [modelsResponse, defaultsResponse] = await Promise.all([
        apiClient.fetchModels(),
        apiClient.fetchModelDefaults()
      ]);
      if (abortController.signal.aborted) return;
      publishModelCatalog(modelsResponse.models, defaultsResponse.defaults);

      if (abortController.signal.aborted) return;
      const unverifiedCount = [
        ...Object.values(result.checks.thinking_modes),
        ...Object.values(result.checks.non_thinking),
        ...Object.values(result.checks.thinking)
      ].filter(
        (status) => status === "unverified"
      ).length;
      const metadataIncomplete = result.metadata.status !== "refreshed";
      const partiallyCompleted = metadataIncomplete || unverifiedCount > 0;
      showStatusNotification({
        id: `model-probe-${modelId}`,
        message: [
          result.metadata.message,
          capabilityProbeSummary(result.checks)
        ].filter(Boolean).join("；"),
        title: partiallyCompleted ? "能力识别部分完成" : "能力识别完成",
        tone: partiallyCompleted ? "warning" : "success"
      });
    } catch (error) {
      if (abortController.signal.aborted) return;
      showStatusNotification({
        id: `model-probe-${modelId}`,
        message: error instanceof Error ? error.message : "能力识别失败。",
        title: "能力识别未完成",
        tone: "error"
      });
    } finally {
      if (modelProbeAbortControllersRef.current.get(modelId) === abortController) {
        modelProbeAbortControllersRef.current.delete(modelId);
        setProbingModelIds((current) => current.filter((id) => id !== modelId));
      }
    }
  }

  async function updateAddedModel(
    modelId: string,
    patch: ModelUpdatePayload,
    { notify = true }: { notify?: boolean } = {}
  ) {
    setSavingModelIds((current) => [...new Set([...current, modelId])]);
    try {
      await apiClient.updateModel(modelId, patch);
      const [modelsResponse, defaultsResponse] = await Promise.all([
        apiClient.fetchModels(),
        apiClient.fetchModelDefaults()
      ]);
      publishModelCatalog(modelsResponse.models, defaultsResponse.defaults);

      if (notify) {
        showStatusNotification({
          id: `model-update-${modelId}`,
          message: "修改已生效。",
          title: "模型设置已保存",
          tone: "success"
        });
      }
    } catch (error) {
      if (notify) {
        showStatusNotification({
          id: `model-update-${modelId}`,
          message: error instanceof Error ? error.message : "模型设置保存失败。",
          title: "模型设置未保存",
          tone: "error"
        });
      }
      throw error;
    } finally {
      setSavingModelIds((current) => current.filter((id) => id !== modelId));
    }
  }

  async function deleteAddedModel(modelId: string): Promise<boolean> {
    if (!selectedProvider) {
      return false;
    }
    const activeProbe = modelProbeAbortControllersRef.current.get(modelId);
    if (activeProbe) {
      activeProbe.abort();
      modelProbeAbortControllersRef.current.delete(modelId);
      setProbingModelIds((current) => current.filter((id) => id !== modelId));
    }
    try {
      await apiClient.deleteModel(modelId);
      const [modelResponse, defaultsResponse] = await Promise.all([
        apiClient.fetchModels(),
        apiClient.fetchModelDefaults()
      ]);
      publishModelCatalog(modelResponse.models, defaultsResponse.defaults);

      setTestStates((current) => ({
        ...current,
        [selectedProvider.provider_id]: {
          status: "success",
          message: "模型已删除。"
        }
      }));
      return true;
    } catch (error) {
      setTestStates((current) => ({
        ...current,
        [selectedProvider.provider_id]: {
          status: "error",
          message: error instanceof Error ? error.message : "模型删除失败。"
        }
      }));
      return false;
    }
  }
  return {
    openAddModelModal,
    retryLoadRemoteModels,
    addRemoteModel,
    probeAddedModel,
    updateAddedModel,
    deleteAddedModel
  };
}
