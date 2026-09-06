import {
  type Dispatch,
  type MutableRefObject,
  type SetStateAction,
  useEffect,
  useRef,
  useState
} from "react";
import { captureAuthContext, isAuthContextCurrent } from "../../api/authLifecycle";

import {
  apiClient
} from "../../api/client";
import { fetchModelCatalog, type ModelCatalog } from "../modelConfiguration/modelCatalog";

type ConversationModelControlOptions = {
  composerModelControlRef: MutableRefObject<HTMLDivElement | null>;
  modelCatalog: ModelCatalog;
  setComposerError: Dispatch<SetStateAction<string>>;
  setModelCatalog: Dispatch<SetStateAction<ModelCatalog>>;
};

export function useConversationModelControl(options: ConversationModelControlOptions) {
  const {
    composerModelControlRef,
    modelCatalog,
    setComposerError,
    setModelCatalog
  } = options;
  const models = modelCatalog.models;
  const requestSequence = useRef(0);
  const saveSequence = useRef(0);
  const [selectedModelId, setSelectedModelId] = useState("");
  const [preferredThinkingMode, setPreferredThinkingMode] = useState("default");
  const [effectiveThinkingMode, setEffectiveThinkingMode] = useState<string | null>(null);
  const [modelPickerOpen, setModelPickerOpen] = useState(false);
  const defaultModel = modelCatalog.defaults.chat ?? undefined;
  const selectedModel = models.find((model) => model.model_id === selectedModelId) ?? defaultModel;
  const selectedThinkingModes = selectedModel?.thinking_modes.length
    ? selectedModel.thinking_modes
    : ["default"];

  useEffect(() => {
    if (!defaultModel) {
      if (selectedModelId) {
        setSelectedModelId("");
      }
      setPreferredThinkingMode("default");
      setEffectiveThinkingMode(null);
      return;
    }
    setSelectedModelId(defaultModel.model_id);
  }, [defaultModel?.model_id]);

  useEffect(() => {
    const activeModel = models.find((model) => model.model_id === selectedModelId);
    if (!activeModel) {
      return;
    }
    if (!activeModel.thinking_modes.includes(preferredThinkingMode)) {
      setPreferredThinkingMode(activeModel.thinking_modes[0] ?? "default");
    }
  }, [models, preferredThinkingMode, selectedModelId]);

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

    function closeModelPickerOnEscape(event: KeyboardEvent) {
      if (event.key !== "Escape") {
        return;
      }
      setModelPickerOpen(false);
      composerModelControlRef.current
        ?.querySelector<HTMLButtonElement>(".composer-model-trigger")
        ?.focus();
    }

    document.addEventListener("pointerdown", closeModelPickerOnOutsidePointerDown);
    document.addEventListener("keydown", closeModelPickerOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeModelPickerOnOutsidePointerDown);
      document.removeEventListener("keydown", closeModelPickerOnEscape);
    };
  }, [composerModelControlRef, modelPickerOpen]);

  async function refreshConversationModels() {
    const sequence = ++requestSequence.current;
    const context = captureAuthContext();
    try {
      const catalog = await fetchModelCatalog();
      if (isAuthContextCurrent(context) && sequence === requestSequence.current) setModelCatalog(catalog);
    } catch (error) {
      if (!isAuthContextCurrent(context) || sequence !== requestSequence.current) return;
      const message = error instanceof Error ? error.message : "模型列表刷新失败。";
      setModelCatalog(current => ({ ...current, status: "error", error: message }));
      setComposerError(message);
    }
  }

  async function chooseSessionModel(modelId: string) {
    const nextModel = models.find((model) => model.model_id === modelId);
    if (!nextModel) {
      return;
    }
    const sequence = ++saveSequence.current;
    const context = captureAuthContext();
    requestSequence.current += 1;
    setSelectedModelId(modelId);
    setPreferredThinkingMode((currentMode) =>
      nextModel.thinking_modes.includes(currentMode)
        ? currentMode
        : nextModel.thinking_modes[0] ?? "default"
    );
    setEffectiveThinkingMode(null);
    setModelPickerOpen(false);
    setComposerError("");
    try {
      const defaultsResponse = await apiClient.updateModelDefaults({ chat: modelId });
      if (!isAuthContextCurrent(context) || sequence !== saveSequence.current) return;
      setModelCatalog(current => ({ ...current, defaults: defaultsResponse.defaults, status: "ready", error: "" }));
    } catch (error) {
      if (!isAuthContextCurrent(context) || sequence !== saveSequence.current) return;
      setComposerError(error instanceof Error ? error.message : "聊天模型更新失败。");
    }
  }

  function chooseThinkingMode(mode: string) {
    setPreferredThinkingMode(mode);
  }

  function applyEffectiveThinkingMode(mode: string) {
    setEffectiveThinkingMode(mode);
  }

  function clearEffectiveThinkingMode() {
    setEffectiveThinkingMode(null);
  }

  function resetModelControl() {
    setSelectedModelId("");
    setPreferredThinkingMode("default");
    setEffectiveThinkingMode(null);
    setModelPickerOpen(false);
  }

  return {
    applyEffectiveThinkingMode,
    chooseSessionModel,
    chooseThinkingMode,
    clearEffectiveThinkingMode,
    defaultModel,
    effectiveThinkingMode,
    modelPickerOpen,
    resetModelControl,
    selectedModel,
    selectedModelId: selectedModel?.model_id ?? "",
    selectedThinkingModes: effectiveThinkingMode && !selectedThinkingModes.includes(effectiveThinkingMode)
      ? [effectiveThinkingMode, ...selectedThinkingModes]
      : selectedThinkingModes,
    setModelPickerOpen,
    preferredThinkingMode,
    temporaryThinkingModeActive: effectiveThinkingMode !== null,
    thinkingMode: effectiveThinkingMode ?? preferredThinkingMode
  };
}
