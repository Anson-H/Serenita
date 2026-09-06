import type { ConversationModelRecord, ConversationRecord } from "../../api/client";

export type ContextWindowUsage = {
  contextWindowTokens: number;
  percent: number;
  usedTokens: number;
};

export function contextWindowUsageCopy(usage: ContextWindowUsage) {
  const roundedPercent = Math.min(Math.max(Math.round(usage.percent), 0), 100);
  const remainingPercent = 100 - roundedPercent;
  return {
    ariaLabel: `上下文用量：${roundedPercent}%`,
    tokenLabel: `已用 ${Math.round(usage.usedTokens / 1000)}k 标记，共 ${Math.round(usage.contextWindowTokens / 1000)}k`,
    usageLabel: roundedPercent < 50
      ? `${roundedPercent}% 已用（剩余 ${remainingPercent}%）`
      : `${roundedPercent}% 已用`
  };
}

export function recordObject(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

export function firstTokenCount(...values: unknown[]) {
  for (const value of values) {
    if (typeof value === "number" && Number.isFinite(value) && value >= 0) {
      return value;
    }
    if (typeof value === "string" && /^\d+$/.test(value.trim())) {
      return Number(value);
    }
  }
  return null;
}

export function resolvedModelUsage(record: ConversationModelRecord) {
  const result = recordObject(record.value);
  const embeddedUsage = recordObject(result?.usage);
  return {
    ...(embeddedUsage ?? {}),
    ...(record.usage ?? {})
  };
}

function totalModelTokens(record: ConversationModelRecord) {
  const usage = resolvedModelUsage(record);
  if (usage.total_tokens !== undefined && usage.total_tokens !== null) {
    return firstTokenCount(usage.total_tokens);
  }
  const inputTokens = firstTokenCount(usage.prompt_tokens, usage.input_tokens);
  const outputTokens = firstTokenCount(usage.completion_tokens, usage.output_tokens);
  return inputTokens !== null && outputTokens !== null
    ? inputTokens + outputTokens
    : null;
}

function positiveContextWindow(value: unknown) {
  return typeof value === "number" &&
    Number.isFinite(value) &&
    Number.isInteger(value) &&
    value > 0
    ? value
    : null;
}

export function contextWindowUsageFromRecords(
  records: readonly ConversationRecord[]
): ContextWindowUsage | null {
  let latestUsage: ContextWindowUsage | null = null;
  for (const record of records) {
    if (
      record.kind !== "model" ||
      record.channel !== "result" ||
      record.purpose !== "agent_action"
    ) {
      continue;
    }
    const contextWindowTokens = positiveContextWindow(record.context_window_tokens);
    const totalTokens = totalModelTokens(record);
    if (contextWindowTokens === null || totalTokens === null) {
      continue;
    }
    const usedTokens = Math.min(totalTokens, contextWindowTokens);
    const percent = Math.min(Math.max((usedTokens / contextWindowTokens) * 100, 0), 100);
    if (!Number.isFinite(percent)) {
      continue;
    }
    latestUsage = {
      contextWindowTokens,
      percent,
      usedTokens
    };
  }
  return latestUsage;
}
