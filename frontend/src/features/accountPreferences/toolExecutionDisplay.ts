import type { ToolExecutionDisplayType as ApiToolExecutionDisplayType } from "../../api/client";
import {
  readConversationPreferences,
  useConversationPreferences,
  writeConversationPreferences
} from "./conversationPreferences";

export type ToolExecutionDisplayType = ApiToolExecutionDisplayType;

type ToolExecutionDisplayOption = {
  description: string;
  label: string;
  type: ToolExecutionDisplayType;
};

export const toolExecutionDisplayOptions: readonly ToolExecutionDisplayOption[] = [
  {
    type: "model_tool_request",
    label: "请求工具调用",
    description: "直接显示模型返回的工具请求内容，不拼接或补充字段。"
  },
  {
    type: "tool_call",
    label: "工具调用结果",
    description: "下一次真实模型输入中可读的 Tool Observation 内容。"
  }
];

const defaultToolExecutionDisplayTypes: readonly ToolExecutionDisplayType[] = [
  "model_tool_request",
  "tool_call"
];

const availableToolExecutionDisplayTypes = new Set<ToolExecutionDisplayType>(
  toolExecutionDisplayOptions.map((option) => option.type)
);
function normalizeToolExecutionDisplayTypes(value: unknown): ToolExecutionDisplayType[] {
  const requested = new Set(
    Array.isArray(value)
      ? value.filter((item): item is ToolExecutionDisplayType =>
        typeof item === "string" &&
        availableToolExecutionDisplayTypes.has(item as ToolExecutionDisplayType)
      )
      : defaultToolExecutionDisplayTypes
  );
  return toolExecutionDisplayOptions
    .map((option) => option.type)
    .filter((type) => requested.has(type));
}

export function useToolExecutionDisplayTypes(accountId: string) {
  return normalizeToolExecutionDisplayTypes(
    useConversationPreferences(accountId).tool_display_types
  );
}

export function writeToolExecutionDisplayTypes(
  accountId: string,
  displayTypes: readonly string[]
) {
  const normalized = normalizeToolExecutionDisplayTypes(displayTypes);
  writeConversationPreferences(accountId, {
    ...readConversationPreferences(accountId),
    tool_display_types: normalized
  });
  return normalized;
}
