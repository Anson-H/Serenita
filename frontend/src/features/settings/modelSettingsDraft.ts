import type {
  GenerationModel,
  ModelCapabilityProfiles,
  ModelUpdatePayload
} from "../../api/client";

export type ModelSettingsDraft = {
  modelName: string;
  thinkingModes: string[];
  capabilityProfiles: ModelCapabilityProfiles;
  contextWindowTokens: string;
  maxOutputTokens: string;
};

export type ModelAutoSaveJob = {
  signature: string;
  target: ModelUpdatePayload;
};

export function modelSettingsDraft(model: GenerationModel): ModelSettingsDraft {
  return {
    modelName: model.model_name,
    thinkingModes: model.thinking_modes,
    capabilityProfiles: model.capability_profiles,
    contextWindowTokens: model.context_window_tokens?.toString() ?? "",
    maxOutputTokens: model.max_output_tokens?.toString() ?? ""
  };
}

function optionalPositiveInteger(value: string, label: string) {
  if (!value.trim()) return null;
  const number = Number(value);
  if (!Number.isInteger(number) || number <= 0) {
    throw new Error(label + "必须是正整数或留空。");
  }
  return number;
}

export function modelSettingsPayload(draft: ModelSettingsDraft): ModelUpdatePayload {
  const normalizedName = draft.modelName.trim();
  if (!normalizedName) throw new Error("模型昵称不能为空。");
  if (!draft.thinkingModes.length) throw new Error("至少保留一个思考档位。");
  return {
    model_name: normalizedName,
    thinking_modes: draft.thinkingModes,
    capability_profiles: draft.capabilityProfiles,
    context_window_tokens: optionalPositiveInteger(
      draft.contextWindowTokens,
      "单条输入词元上限"
    ),
    max_output_tokens: optionalPositiveInteger(draft.maxOutputTokens, "单条输出词元上限")
  };
}

export function modelSettingsSignature(patch: ModelUpdatePayload) {
  return JSON.stringify(patch);
}

export function modelSettingsPatch(
  target: ModelUpdatePayload,
  baseline: ModelUpdatePayload
): ModelUpdatePayload {
  const patch: ModelUpdatePayload = {};
  if (target.model_name !== baseline.model_name) patch.model_name = target.model_name;
  if (JSON.stringify(target.thinking_modes) !== JSON.stringify(baseline.thinking_modes)) {
    patch.thinking_modes = target.thinking_modes;
  }
  if (
    JSON.stringify(target.capability_profiles)
    !== JSON.stringify(baseline.capability_profiles)
  ) {
    patch.capability_profiles = target.capability_profiles;
  }
  if (target.context_window_tokens !== baseline.context_window_tokens) {
    patch.context_window_tokens = target.context_window_tokens;
  }
  if (target.max_output_tokens !== baseline.max_output_tokens) {
    patch.max_output_tokens = target.max_output_tokens;
  }
  return patch;
}
