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
  beginRemoteRead: () => () => boolean;
  isRemoteModelCurrent: (model: RemoteModel) => boolean;
  selectedProvider: ProviderSummary | undefined;
  selectedDraft: ProviderDraft | undefined;
  setModelPickerOpen: Dispatch<SetStateAction<boolean>>;
  setModelPickerLoading: Dispatch<SetStateAction<boolean>>;
  setModelPickerError: Dispatch<SetStateAction<string>>;
  setRemoteModels: Dispatch<SetStateAction<RemoteModel[]>>;
  autoSaveProviderDraft: (providerId: string, draft: ProviderDraft) => Promise<ProviderDraft | false>;
  setTestStates: Dispatch<SetStateAction<Record<string, TestState>>>;
  setAddingRemoteModelIds: Dispatch<SetStateAction<string[]>>;
  setAddedModels: (next: SetStateAction<AddedModel[]>) => void;
  chatDefaultModelId: string;
  setModelDefaults: (next: SetStateAction<ModelDefaults>) => void;
  modelProbeAbortControllersRef: RefObject<Map<string, AbortController>>;
  setProbingModelIds: Dispatch<SetStateAction<string[]>>;
  refreshModels: () => Promise<void>;
  setSavingModelIds: Dispatch<SetStateAction<string[]>>;
};

export function createModelSettingsActions({
  beginRemoteRead,
  isRemoteModelCurrent,
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
  modelProbeAbortControllersRef,
  setProbingModelIds,
  refreshModels,
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
    const isCurrent = beginRemoteRead();
    setModelPickerLoading(true);
    setModelPickerError("");
    setRemoteModels([]);
    try {
      if (!await autoSaveProviderDraft(providerId, selectedDraft)) throw new Error("提供方设置尚未保存，请重试。");
      if (!isCurrent()) return;
      const result = await apiClient.fetchProviderModels(providerId);
      if (!isCurrent()) return;
      setRemoteModels(result.models);
      setTestStates((current) => ({
        ...current,
        [providerId]: {
          status: "success",
          message: "已加载。"
        }
      }));
    } catch (error) {
      if (!isCurrent()) return;
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
      if (isCurrent()) setModelPickerLoading(false);
    }
  }

  function retryLoadRemoteModels() {
    void loadRemoteModels();
  }

  async function addRemoteModel(model: RemoteModel) {
    if (!selectedProvider || !isRemoteModelCurrent(model)) {
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
        message: "模型已添加，正在检测模型。"
      }
    }));
    showStatusNotification({
      id: `model-add-${addedModel.model_id}`,
      message: "已加入模型列表，模型检测将在提供方详情中继续进行。",
      title: "模型已添加",
      tone: "success"
    });
    void probeAddedModel(addedModel.model_id);

  }

  async function probeAddedModel(modelId: string) {
    const activeProbe = modelProbeAbortControllersRef.current.get(modelId);
    if (activeProbe) {
      activeProbe.abort();
      return;
    }
    const abortController = new AbortController();
    modelProbeAbortControllersRef.current.set(modelId, abortController);
    setProbingModelIds((current) => [...new Set([...current, modelId])]);
    try {
      const result = await apiClient.probeModelCapabilities(
        modelId,
        abortController.signal
      );
      if (abortController.signal.aborted) return;
      await refreshModels();
      if (abortController.signal.aborted) return;

      if (abortController.signal.aborted) return;
      const unverifiedCount = [
        ...Object.values(result.checks).flatMap(Object.values)
      ].filter(
        (status) => status === "unverified"
      ).length;
      const metadataIncomplete = result.metadata.status !== "refreshed";
      const partiallyCompleted = metadataIncomplete || unverifiedCount > 0;
      showStatusNotification({
        id: `model-probe-${modelId}`,
        message: [
          result.metadata.message,
          capabilityProbeSummary(result.checks),
          ...Object.values(result.errors).flatMap(Object.values),
          result.cleared_defaults?.length ? "已清空不再适用的默认模型。" : ""
        ].filter(Boolean).join("；"),
        title: partiallyCompleted ? "模型检测部分完成" : "模型检测完成",
        tone: partiallyCompleted ? "warning" : "success"
      });
    } catch (error) {
      if (abortController.signal.aborted) return;
      showStatusNotification({
        id: `model-probe-${modelId}`,
        message: error instanceof Error ? error.message : "模型检测失败。",
        title: "模型检测未完成",
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
    modelProbeAbortControllersRef.current.get(modelId)?.abort();
    setSavingModelIds((current) => [...new Set([...current, modelId])]);
    try {
      const updated = await apiClient.updateModel(modelId, patch);
      if (updated.cleared_defaults?.length) showStatusNotification({ message: "已清空不再适用的默认模型，请重新选择。", tone: "warning" });
      await refreshModels();

      if (notify) {
        showStatusNotification({
          id: `model-update-${modelId}`,
          message: "更新已生效。",
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
      await refreshModels();

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
