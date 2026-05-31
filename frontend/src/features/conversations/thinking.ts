import type { ConversationMessage } from "../../api/client";

export const MIN_THINKING_DURATION_MS = 100;

const thinkingModeLabels: Record<string, string> = {
  default: "默认强度推理",
  fast: "关闭推理",
  low: "低强度推理",
  medium: "中强度推理",
  high: "高强度推理",
  xhigh: "超高强度推理"
};

export function thinkingModeLabel(mode: string) {
  return thinkingModeLabels[mode] ?? mode;
}

export function composerThinkingModeLabel(mode: string) {
  const label = thinkingModeLabel(mode);
  return label === "关闭推理" ? "关闭" : label.replace(/强度推理$/, "");
}

export function formatThinkingDuration(durationMs: number | undefined) {
  if (typeof durationMs !== "number" || !Number.isFinite(durationMs) || durationMs <= 0) {
    return "0 秒";
  }
  if (durationMs < 1000) {
    const seconds = Math.max(MIN_THINKING_DURATION_MS / 1000, Math.round(durationMs / 100) / 10);
    return `${seconds.toFixed(1).replace(/\.0$/, "")} 秒`;
  }
  const totalSeconds = Math.round(durationMs / 1000);
  if (totalSeconds < 60) {
    return `${totalSeconds} 秒`;
  }
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return seconds ? `${minutes} 分 ${seconds} 秒` : `${minutes} 分`;
}

export function thinkingSummaryText(message: ConversationMessage, isStreaming: boolean) {
  if (isStreaming && !message.duration_ms) {
    return "正在思考";
  }
  return `思考完成（用时 ${formatThinkingDuration(message.duration_ms)}）`;
}

export function isAbortError(error: unknown) {
  return Boolean(error && typeof error === "object" && "name" in error && error.name === "AbortError");
}
