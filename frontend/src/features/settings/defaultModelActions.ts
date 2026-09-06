import type { RefObject, SetStateAction } from "react";
import {
  AddedModel,
  ModelDefaults,
  apiClient
} from "../../api/client";
import { showStatusNotification } from "../../components/StatusNotificationCenter";
import { SerialTasks } from "../../utils/serialTasks";
import {
  type DefaultModelUsage
} from "./settingsTypes";

type Dependencies = {
  defaultSaveSequences: RefObject<Record<string, number>>;
  addedModels: AddedModel[];
  setModelDefaults: (next: SetStateAction<ModelDefaults>) => void;
  serialTasks: RefObject<SerialTasks>;
  isCurrentScope: () => boolean;
};

export function createDefaultModelActions({ defaultSaveSequences, addedModels, setModelDefaults, serialTasks, isCurrentScope }: Dependencies) {
  async function updateDefaultModel(usage: DefaultModelUsage, nextModelId: string) {
    const sequence = (defaultSaveSequences.current[usage] ?? 0) + 1;
    defaultSaveSequences.current[usage] = sequence;
    try {
      const nextModel = addedModels.find((model) => model.model_id === nextModelId) ?? null;
      setModelDefaults((current) => ({
        ...current,
        [usage]: nextModel
      }));
      const defaultsResponse = await serialTasks.current.run("defaults", () => apiClient.updateModelDefaults({ [usage]: nextModelId || null }), isCurrentScope);
      if (!isCurrentScope()) return;
      if (defaultSaveSequences.current[usage] === sequence) {
        setModelDefaults(current => ({ ...current, [usage]: defaultsResponse.defaults[usage] }));
      }

      showStatusNotification({
        id: `default-model-${usage}`,
        message: "默认模型已更新。",
        tone: "success"
      });
    } catch (error) {
      if (!isCurrentScope() || defaultSaveSequences.current[usage] !== sequence) return;
      showStatusNotification({
        id: `default-model-${usage}`,
        message: error instanceof Error ? error.message : "默认模型更新失败。",
        title: "默认模型未更新",
        tone: "error"
      });
    }
  }
  return {
    updateDefaultModel
  };
}
