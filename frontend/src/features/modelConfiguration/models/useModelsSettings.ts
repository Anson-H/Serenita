import { useModelSettingsApi } from "../ModelSettingsApi";
import { useEffect, useRef, type Dispatch, type SetStateAction } from "react";
import {
  type AddedModel,
  type ModelDefaults,
  type ProviderSummary,
  type RemoteModel,
} from "../../../api/models/modelTypes";
import { useScopedState } from "../../../utils/useScopedState";
import type { ModelCatalog } from "../modelCatalog";
import { createModelSettingsActions } from "./modelSettingsActions";
import type { createProviderSettingsActions } from "../providers/providerSettingsActions";
import { type DefaultModelUsage } from "./modelSettingsTypes";
import { type ProviderDraft } from "../providers/providerDraft";
import { type TestState } from "../../../utils/requestStatus";
const defaultModelUsages: Array<{ key: DefaultModelUsage; label: string }> = [
  { key: "chat", label: "聊天模型" },
  { key: "title", label: "标题生成模型" },
  { key: "vision_parse", label: "视觉解析模型" },
  { key: "compact", label: "压缩上下文模型" },
  { key: "memory_generation", label: "长期记忆生成模型" },
  { key: "text_embedding", label: "文本向量模型" },
  { key: "multimodal_embedding", label: "多模态向量模型" },
];

export function useModelsSettings({
  modelCatalog,
  onModelsChanged,
  refreshModels,
  isCurrentScope,
  selectedProvider,
  selectedDraft,
  autoSaveProviderDraft,
  setTestStates,
}: {
  modelCatalog: ModelCatalog;
  onModelsChanged: Dispatch<SetStateAction<ModelCatalog>>;
  refreshModels: (isRelevant?: () => boolean) => Promise<void>;
  isCurrentScope: () => boolean;
  selectedProvider: ProviderSummary | undefined;
  selectedDraft: ProviderDraft | undefined;
  autoSaveProviderDraft: ReturnType<
    typeof createProviderSettingsActions
  >["autoSaveProviderDraft"];
  setTestStates: Dispatch<SetStateAction<Record<string, TestState>>>;
}) {
  const api = useModelSettingsApi();
  const remoteRequest = useRef({ provider: selectedProvider?.provider_id, sequence: 0 });
  if (remoteRequest.current.provider !== selectedProvider?.provider_id)
    remoteRequest.current = { provider: selectedProvider?.provider_id, sequence: remoteRequest.current.sequence + 1 };

  const [remoteModels, setRemoteModels] = useScopedState<RemoteModel[]>(
    [],
    isCurrentScope,
  );

  const [modelPickerOpen, setModelPickerOpenState] = useScopedState(
    false,
    isCurrentScope,
  );

  const [modelPickerLoading, setModelPickerLoading] = useScopedState(
    false,
    isCurrentScope,
  );

  const [modelPickerError, setModelPickerError] = useScopedState(
    "",
    isCurrentScope,
  );
  function setModelPickerOpen(next: SetStateAction<boolean>) {
    const open = typeof next === "function" ? next(modelPickerOpen) : next;
    if (!open) { remoteRequest.current.sequence++; setModelPickerLoading(false); }
    setModelPickerOpenState(open);
  }
  function beginRemoteRead() {
    const provider = selectedProvider?.provider_id;
    const sequence = ++remoteRequest.current.sequence;
    return () => isCurrentScope() && remoteRequest.current.provider === provider && remoteRequest.current.sequence === sequence;
  }

  const addedModels = modelCatalog.models;

  function setAddedModels(next: SetStateAction<AddedModel[]>) {
    if (isCurrentScope())
      onModelsChanged((current) => ({
        ...current,
        models: typeof next === "function" ? next(current.models) : next,
      }));
  }

  function setModelDefaults(next: SetStateAction<ModelDefaults>) {
    if (isCurrentScope())
      onModelsChanged((current) => ({
        ...current,
        defaults: typeof next === "function" ? next(current.defaults) : next,
      }));
  }

  const [addingRemoteModelIds, setAddingRemoteModelIds] = useScopedState<
    string[]
  >([], isCurrentScope);

  const [probingModelIds, setProbingModelIds] = useScopedState<string[]>(
    [],
    isCurrentScope,
  );

  const [savingModelIds, setSavingModelIds] = useScopedState<string[]>(
    [],
    isCurrentScope,
  );

  const modelDefaults = modelCatalog.defaults;

  const modelProbeAbortControllersRef = useRef(
    new Map<string, AbortController>(),
  );

  const defaultModelItems = defaultModelUsages.map((item) => ({
    ...item,
    selectedModelId: modelDefaults[item.key]?.model_id ?? "",
  }));

  const chatDefaultModelId = modelDefaults.chat?.model_id ?? "";

  const {
    openAddModelModal,
    retryLoadRemoteModels,
    addRemoteModel,
    probeAddedModel,
    updateAddedModel,
    deleteAddedModel,
  } = createModelSettingsActions({
    api,
    beginRemoteRead,
    isRemoteModelCurrent: () => isCurrentScope() && selectedProvider?.provider_id === remoteRequest.current.provider,
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
    refreshModels: () => refreshModels(isCurrentScope),
    setSavingModelIds,
  });

  useEffect(() => () => {
    for (const controller of modelProbeAbortControllersRef.current.values()) controller.abort();
    modelProbeAbortControllersRef.current.clear();
  }, []);

  const [loadError, setLoadError] = useScopedState("", isCurrentScope);
  useEffect(() => {
    void refreshModels(isCurrentScope)
      .catch((cause) =>
        setLoadError(
          cause instanceof Error ? cause.message : "模型设置读取失败。",
        ),
      );
  }, []);

  return {
    remoteModels,
    setRemoteModels,
    modelPickerOpen,
    setModelPickerOpen,
    modelPickerLoading,
    modelPickerError,
    setModelPickerError,
    addedModels,
    addingRemoteModelIds,
    probingModelIds,
    savingModelIds,
    defaultModelItems,
    openAddModelModal,
    retryLoadRemoteModels,
    addRemoteModel,
    probeAddedModel,
    updateAddedModel,
    deleteAddedModel,
    loadError,
  };
}
