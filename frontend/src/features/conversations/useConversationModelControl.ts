import {
  type Dispatch,
  type MutableRefObject,
  type SetStateAction,
  useEffect,
  useState
} from "react";

import {
  type AddedModel,
  apiClient
} from "../../api/client";
import { mergeModelsWithChatDefault } from "./conversationModels";

type ConversationModelControlOptions = {
  composerModelControlRef: MutableRefObject<HTMLDivElement | null>;
  models: AddedModel[];
  setComposerError: Dispatch<SetStateAction<string>>;
  setModels: Dispatch<SetStateAction<AddedModel[]>>;
  setVisionParseModel: Dispatch<SetStateAction<AddedModel | null>>;
};

export function useConversationModelControl(options: ConversationModelControlOptions) {
  const {
    composerModelControlRef,
    models,
    setComposerError,
    setModels,
    setVisionParseModel
  } = options;
  const [selectedModelId, setSelectedModelId] = useState("");
  const [thinkingMode, setThinkingMode] = useState("default");
  const [modelPickerOpen, setModelPickerOpen] = useState(false);
  const defaultModel = models[0];
  const defaultModelThinkingModesKey = defaultModel?.thinking_modes.join("|") ?? "";
  const selectedModel = models.find((model) => model.model_id === selectedModelId) ?? defaultModel;
  const selectedThinkingModes = selectedModel?.thinking_modes.length
    ? selectedModel.thinking_modes
    : ["default"];

  useEffect(() => {
    if (!defaultModel) {
      if (selectedModelId) {
        setSelectedModelId("");
      }
      setThinkingMode("default");
      return;
    }
    if (selectedModelId !== defaultModel.model_id) {
      setSelectedModelId(defaultModel.model_id);
    }
    setThinkingMode((currentMode) =>
      defaultModel.thinking_modes.includes(currentMode)
        ? currentMode
        : defaultModel.thinking_modes[0] ?? "default"
    );
  }, [defaultModel?.model_id, defaultModelThinkingModesKey, selectedModelId]);

  useEffect(() => {
    const activeModel = models.find((model) => model.model_id === selectedModelId);
    if (!activeModel) {
      return;
    }
    if (!activeModel.thinking_modes.includes(thinkingMode)) {
      setThinkingMode(activeModel.thinking_modes[0] ?? "default");
    }
  }, [models, selectedModelId, thinkingMode]);

  useEffect(() => {
    if (!modelPickerOpen) {
      return;
    }
    void refreshConversationModels();

    function closeModelPickerOnOutsidePointerDown(event: PointerEvent) {
      const control = composerModelControlRef.current;
      if (!control || !control.contains(event.target as Node)) {
        setModelPickerOpen(false);
      }
    }

    document.addEventListener("pointerdown", closeModelPickerOnOutsidePointerDown);
    return () => document.removeEventListener("pointerdown", closeModelPickerOnOutsidePointerDown);
  }, [composerModelControlRef, modelPickerOpen]);

  async function refreshConversationModels() {
    try {
      const [modelResponse, defaultsResponse] = await Promise.all([
        apiClient.fetchModels(),
        apiClient.fetchModelDefaults().catch(() => null)
      ]);
      setModels(mergeModelsWithChatDefault(modelResponse.models, defaultsResponse?.defaults.chat ?? null));
      setVisionParseModel(defaultsResponse?.defaults.vision_parse ?? null);
    } catch (error) {
      setComposerError(error instanceof Error ? error.message : "模型列表刷新失败。");
    }
  }

  async function chooseSessionModel(modelId: string) {
    const nextModel = models.find((model) => model.model_id === modelId);
    if (!nextModel) {
      return;
    }
    const previousModelId = selectedModelId;
    const previousThinkingMode = thinkingMode;
    setSelectedModelId(modelId);
    setThinkingMode((currentMode) =>
      nextModel.thinking_modes.includes(currentMode)
        ? currentMode
        : nextModel.thinking_modes[0] ?? "default"
    );
    setModelPickerOpen(false);
    setComposerError("");
    try {
      const defaultsResponse = await apiClient.updateModelDefaults({ chat: modelId });
      setModels((currentModels) =>
        mergeModelsWithChatDefault(currentModels, defaultsResponse.defaults.chat)
      );
      setVisionParseModel(defaultsResponse.defaults.vision_parse);
    } catch (error) {
      setSelectedModelId(previousModelId);
      setThinkingMode(previousThinkingMode);
      setComposerError(error instanceof Error ? error.message : "聊天模型更新失败。");
    }
  }

  function chooseThinkingMode(mode: string) {
    setThinkingMode(mode);
    setModelPickerOpen(false);
  }

  function resetModelControl() {
    setSelectedModelId("");
    setThinkingMode("default");
    setModelPickerOpen(false);
  }

  return {
    chooseSessionModel,
    chooseThinkingMode,
    defaultModel,
    modelPickerOpen,
    resetModelControl,
    selectedModel,
    selectedModelId: selectedModel?.model_id ?? "",
    selectedThinkingModes,
    setModelPickerOpen,
    thinkingMode
  };
}
