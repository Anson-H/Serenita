import { useMemo } from "react";

import type { ConversationModelRecord } from "../../api/client";
import { ChevronDownIcon } from "../../components/icons";
import {
  firstTokenCount,
  recordObject,
  resolvedModelUsage
} from "./modelTokenUsage";

function formatTokenCount(value: number | null) {
  return value === null ? "—" : value.toLocaleString("zh-CN");
}

const TOKEN_METRIC_LABELS: Record<string, string> = {
  cached_tokens: "缓存命中",
  image_tokens: "图像",
  text_tokens: "文本",
  reasoning_tokens: "推理"
};

function TokenUsageGroup({
  kind,
  label,
  metrics
}: {
  kind: "input" | "output";
  label: string;
  metrics: ReadonlyArray<readonly [string, number | null]>;
}) {
  return (
    <span className="model-token-usage-group root-disclosure-row" data-kind={kind}>
      <span className="model-token-usage-group-label">{label}</span>
      <span className="model-token-usage-metrics">
        {metrics.map(([name, value]) => (
          <span
            className="model-token-usage-metric"
            data-missing={value === null ? "true" : undefined}
            key={`${kind}-${name}`}
            title={`${name}: ${formatTokenCount(value)}`}
          >
            <span className="model-token-usage-metric-label">
              {TOKEN_METRIC_LABELS[name] ?? name}
            </span>
            <span className="model-token-usage-metric-value">
              {formatTokenCount(value)}
            </span>
          </span>
        ))}
      </span>
    </span>
  );
}

type ModelTokenCounts = {
  prompt_tokens: number | null;
  input_text_tokens: number | null;
  image_tokens: number | null;
  cached_tokens: number | null;
  completion_tokens: number | null;
  output_text_tokens: number | null;
  reasoning_tokens: number | null;
};

function modelTokenCounts(record: ConversationModelRecord): ModelTokenCounts {
  const usage = resolvedModelUsage(record);
  const inputDetails = {
    ...(recordObject(usage.input_tokens_details) ?? {}),
    ...(recordObject(usage.prompt_tokens_details) ?? {})
  };
  const outputDetails = {
    ...(recordObject(usage.output_tokens_details) ?? {}),
    ...(recordObject(usage.completion_tokens_details) ?? {})
  };
  const completionTokens = firstTokenCount(usage.completion_tokens, usage.output_tokens);
  const outputTextTokens = firstTokenCount(outputDetails.text_tokens);
  const reasoningTokens = firstTokenCount(outputDetails.reasoning_tokens, usage.reasoning_tokens);
  return {
    prompt_tokens: firstTokenCount(usage.prompt_tokens, usage.input_tokens),
    input_text_tokens: firstTokenCount(inputDetails.text_tokens),
    image_tokens: firstTokenCount(inputDetails.image_tokens, usage.image_tokens),
    cached_tokens: firstTokenCount(inputDetails.cached_tokens, usage.cached_tokens),
    completion_tokens: completionTokens,
    output_text_tokens: outputTextTokens,
    reasoning_tokens: reasoningTokens
  };
}

function hasTokenUsage(counts: readonly ModelTokenCounts[]) {
  return counts.some((entry) =>
    Object.values(entry).some((value) => value !== null)
  );
}

export function hasConversationTokenUsage(
  records: readonly ConversationModelRecord[] | undefined
) {
  return Boolean(records?.length && hasTokenUsage(records.map(modelTokenCounts)));
}

function sumTokenCount(
  counts: ModelTokenCounts[],
  metric: keyof ModelTokenCounts
) {
  const values = counts
    .map((entry) => entry[metric])
    .filter((value): value is number => value !== null);
  return values.length ? values.reduce((total, value) => total + value, 0) : null;
}

function ModelTokenUsageLine({
  counts
}: {
  counts: ModelTokenCounts[];
}) {
  const inputMetrics = [
    ["text_tokens", sumTokenCount(counts, "input_text_tokens")],
    ["image_tokens", sumTokenCount(counts, "image_tokens")],
    ["cached_tokens", sumTokenCount(counts, "cached_tokens")]
  ] as const;
  const outputMetrics = [
    ["text_tokens", sumTokenCount(counts, "output_text_tokens")],
    ["reasoning_tokens", sumTokenCount(counts, "reasoning_tokens")]
  ] as const;
  const promptTotal = sumTokenCount(counts, "prompt_tokens");
  const completionTotal = sumTokenCount(counts, "completion_tokens");

  return (
    <details
      aria-label="模型词元用量"
      className="model-token-usage assistant-turn-disclosure root-disclosure-list"
    >
      <summary className="model-token-usage-summary root-disclosure-toggle">
        <span className="model-token-usage-title">词元用量</span>
        <span className="model-token-usage-totals">
          输入 <span className="model-token-usage-total-value">{formatTokenCount(promptTotal)}</span>
          <span aria-hidden="true">·</span>
          输出 <span className="model-token-usage-total-value">{formatTokenCount(completionTotal)}</span>
        </span>
        <ChevronDownIcon className="assistant-turn-disclosure-chevron" />
      </summary>
      <div className="model-token-usage-details root-disclosure-content">
        <TokenUsageGroup kind="input" label="输入" metrics={inputMetrics} />
        <TokenUsageGroup kind="output" label="输出" metrics={outputMetrics} />
      </div>
    </details>
  );
}

export function ConversationTurnTokenUsage({
  records
}: {
  records: ConversationModelRecord[];
}) {
  const counts = useMemo(() => records.map(modelTokenCounts), [records]);
  if (!hasTokenUsage(counts)) {
    return null;
  }
  return (
    <div className="assistant-turn-token-usage">
      <ModelTokenUsageLine counts={counts} />
    </div>
  );
}
