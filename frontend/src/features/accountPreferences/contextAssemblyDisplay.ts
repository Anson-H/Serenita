import type {
  BaseContextAssemblyDisplayMode as ApiBaseContextAssemblyDisplayMode,
  BaseContextAssemblyType as ApiBaseContextAssemblyType,
  ConversationPreferences,
  ConversationRecord
} from "../../api/client";
import {
  readConversationPreferences,
  useConversationPreferences,
  writeConversationPreferences
} from "./conversationPreferences";

export type BaseContextAssemblyType = ApiBaseContextAssemblyType;

export type BaseContextAssemblyDisplayMode = ApiBaseContextAssemblyDisplayMode;

type ContextAssemblyDisplayOption = {
  contextType: string;
  description: string;
  group: "基础装配" | "输入追溯";
  label: string;
};

export type ContextAssemblyDisplaySettings = {
  baseModes: Record<BaseContextAssemblyType, BaseContextAssemblyDisplayMode>;
  showContextWindowUsage: boolean;
  showRelatedContent: boolean;
  showTokenUsage: boolean;
  visibleContextTypes: string[];
};

export const contextAssemblyDisplayOptions: readonly ContextAssemblyDisplayOption[] = [
  {
    contextType: "system_prompt",
    label: "系统提示词",
    description: "Serenita 的行为原则、能力边界与安全要求。",
    group: "基础装配"
  },
  {
    contextType: "tool_catalog",
    label: "可用工具",
    description: "本次模型请求可以调用的工具目录。",
    group: "基础装配"
  },
  {
    contextType: "skill_catalog",
    label: "可用技能",
    description: "本次模型请求可以按需读取的技能目录。",
    group: "基础装配"
  },
  {
    contextType: "runtime_context",
    label: "运行时元数据",
    description: "当前日期、聊天状态等运行时信息；不包含报告附件。",
    group: "基础装配"
  },
  {
    contextType: "current_user_message",
    label: "当前用户输入（含附件）",
    description: "本轮实际发送给模型的用户消息，以及报告、文件等输入片段。",
    group: "输入追溯"
  },
  {
    contextType: "conversation_history",
    label: "历史聊天",
    description: "再次装配进本次模型请求的历史用户与模型消息。",
    group: "输入追溯"
  },
  {
    contextType: "model_tool_request",
    label: "历史请求工具调用",
    description: "作为聊天历史再次装配的模型工具调用请求。",
    group: "输入追溯"
  },
  {
    contextType: "tool_observation",
    label: "历史工具调用结果",
    description: "作为聊天历史再次装配的工具真实结果。",
    group: "输入追溯"
  },
  {
    contextType: "compacted_summary",
    label: "压缩历史摘要",
    description: "长聊天压缩后再次装配给模型的历史摘要。",
    group: "输入追溯"
  }
];

export const baseContextAssemblyDisplayModeOptions: Array<{
  label: string;
  value: BaseContextAssemblyDisplayMode;
}> = [
    { label: "每个步骤都显示", value: "every_step" },
    { label: "每次聊天开始时显示", value: "turn_start" },
    { label: "仅在该聊天中首次显示", value: "conversation_start" },
    { label: "不显示", value: "hidden" }
  ];

const baseContextAssemblyTypes = [
  "system_prompt",
  "tool_catalog",
  "skill_catalog",
  "runtime_context"
] as const satisfies readonly BaseContextAssemblyType[];

const defaultBaseContextAssemblyDisplayModes: Record<
  BaseContextAssemblyType,
  BaseContextAssemblyDisplayMode
> = {
  system_prompt: "conversation_start",
  tool_catalog: "conversation_start",
  skill_catalog: "conversation_start",
  runtime_context: "conversation_start"
};

const defaultContextAssemblyDisplayTypes: readonly string[] = [];
const defaultShowContextWindowUsage = false;
const defaultShowRelatedContent = true;
const defaultShowTokenUsage = true;

const baseContextAssemblyTypeSet = new Set<string>(baseContextAssemblyTypes);
const availableContextTypes = new Set(
  contextAssemblyDisplayOptions.map((option) => option.contextType)
);
const availableDisplayModes = new Set<BaseContextAssemblyDisplayMode>(
  baseContextAssemblyDisplayModeOptions.map((option) => option.value)
);
export function isBaseContextAssemblyType(
  contextType: string
): contextType is BaseContextAssemblyType {
  return baseContextAssemblyTypeSet.has(contextType);
}

function defaultContextAssemblyDisplaySettings(): ContextAssemblyDisplaySettings {
  return {
    baseModes: { ...defaultBaseContextAssemblyDisplayModes },
    showContextWindowUsage: defaultShowContextWindowUsage,
    showRelatedContent: defaultShowRelatedContent,
    showTokenUsage: defaultShowTokenUsage,
    visibleContextTypes: [...defaultContextAssemblyDisplayTypes]
  };
}

function normalizedContextTypes(value: unknown) {
  const requested = new Set(
    Array.isArray(value)
      ? value.filter((item): item is string => typeof item === "string")
      : defaultContextAssemblyDisplayTypes
  );
  return contextAssemblyDisplayOptions
    .map((option) => option.contextType)
    .filter((contextType) => (
      !isBaseContextAssemblyType(contextType) &&
      requested.has(contextType) &&
      availableContextTypes.has(contextType)
    ));
}

function normalizedBaseModes(value: unknown) {
  const requested = value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
  return Object.fromEntries(baseContextAssemblyTypes.map((contextType) => {
    const mode = requested[contextType];
    return [
      contextType,
      typeof mode === "string" && availableDisplayModes.has(mode as BaseContextAssemblyDisplayMode)
        ? mode
        : defaultBaseContextAssemblyDisplayModes[contextType]
    ];
  })) as Record<BaseContextAssemblyType, BaseContextAssemblyDisplayMode>;
}

function normalizedSettings(value: unknown): ContextAssemblyDisplaySettings {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    return defaultContextAssemblyDisplaySettings();
  }
  const requested = value as Record<string, unknown>;
  return {
    baseModes: normalizedBaseModes(requested.baseModes),
    showContextWindowUsage: requested.showContextWindowUsage === true,
    showRelatedContent: requested.showRelatedContent !== false,
    showTokenUsage: requested.showTokenUsage !== false,
    visibleContextTypes: normalizedContextTypes(requested.visibleContextTypes)
  };
}

function contextSettingsFromPreferences(
  preferences: ConversationPreferences
): ContextAssemblyDisplaySettings {
  return {
    baseModes: preferences.base_context_display_modes,
    showContextWindowUsage: preferences.is_context_window_usage_visible,
    showRelatedContent: preferences.is_related_content_visible,
    showTokenUsage: preferences.is_token_usage_visible,
    visibleContextTypes: preferences.visible_context_types
  };
}

export function useContextAssemblyDisplaySettings(accountId: string) {
  return contextSettingsFromPreferences(
    useConversationPreferences(accountId)
  );
}

export function writeContextAssemblyDisplaySettings(
  accountId: string,
  settings: ContextAssemblyDisplaySettings
) {
  const normalized = normalizedSettings(settings);
  writeConversationPreferences(accountId, {
    ...readConversationPreferences(accountId),
    base_context_display_modes: normalized.baseModes,
    is_context_window_usage_visible: normalized.showContextWindowUsage,
    is_related_content_visible: normalized.showRelatedContent,
    is_token_usage_visible: normalized.showTokenUsage,
    visible_context_types: normalized.visibleContextTypes as ConversationPreferences["visible_context_types"]
  });
  return normalized;
}

export function visibleBaseContextRecordIds(
  records: readonly ConversationRecord[],
  modes: Readonly<Record<BaseContextAssemblyType, BaseContextAssemblyDisplayMode>>
) {
  const visibleRecordIds = new Set<string>();
  const shownInConversation = new Set<BaseContextAssemblyType>();
  const shownByTurn = new Map<string, Set<BaseContextAssemblyType>>();

  for (const record of records) {
    if (record.kind !== "context" || !isBaseContextAssemblyType(record.context_type)) {
      continue;
    }
    const contextType = record.context_type;
    const mode = modes[contextType];
    if (mode === "hidden") {
      continue;
    }
    if (mode === "every_step") {
      visibleRecordIds.add(record.record_id);
      continue;
    }
    if (mode === "conversation_start") {
      if (!shownInConversation.has(contextType)) {
        shownInConversation.add(contextType);
        visibleRecordIds.add(record.record_id);
      }
      continue;
    }
    const shownInTurn = shownByTurn.get(record.turn_id) ?? new Set<BaseContextAssemblyType>();
    if (!shownInTurn.has(contextType)) {
      shownInTurn.add(contextType);
      shownByTurn.set(record.turn_id, shownInTurn);
      visibleRecordIds.add(record.record_id);
    }
  }

  return visibleRecordIds;
}
