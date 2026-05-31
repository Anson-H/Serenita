import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import assert from "node:assert/strict";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const lifecycleSource = readFileSync(
  join(root, "src/features/conversations/useConversationLifecycle.ts"),
  "utf8"
);
const modelControlSource = readFileSync(
  join(root, "src/features/conversations/useConversationModelControl.ts"),
  "utf8"
);
const settingsPanelSource = readFileSync(
  join(root, "src/features/settings/SettingsWorkspacePanel.tsx"),
  "utf8"
);

assert(
  lifecycleSource.includes("apiClient.fetchModels()") &&
    lifecycleSource.includes("mergeModelsWithChatDefault(") &&
    lifecycleSource.includes("setModels(mergeModelsWithChatDefault(modelResponse.models, defaultsResponse?.defaults.chat ?? null));"),
  "conversation workspace should load all added models and prefer the default chat model first"
);

assert(
  settingsPanelSource.includes("apiClient.fetchModels()") &&
    settingsPanelSource.includes("onModelsChanged(mergeModelsWithChatDefault(modelResponse.models, defaultsResponse.defaults.chat));"),
  "settings refresh should keep the composer model list aligned with the full model database"
);

assert(
  modelControlSource.includes("refreshConversationModels") &&
    modelControlSource.includes("apiClient.fetchModels()") &&
    modelControlSource.includes("[composerModelControlRef, modelPickerOpen]") &&
    modelControlSource.includes("setModels(mergeModelsWithChatDefault(modelResponse.models, defaultsResponse?.defaults.chat ?? null));"),
  "opening the composer model picker should refresh the full model database instead of relying on stale page state"
);

assert(
  modelControlSource.includes("apiClient.updateModelDefaults({ chat: modelId })"),
  "choosing a composer model should persist it as the shared chat default model"
);

assert(
  modelControlSource.includes("selectedModelId !== defaultModel.model_id") &&
    modelControlSource.includes("setSelectedModelId(defaultModel.model_id)"),
  "composer selected model should follow the refreshed chat default model"
);
