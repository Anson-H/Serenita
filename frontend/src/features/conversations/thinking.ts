const MIN_THINKING_DURATION_MS = 100;

const thinkingModeLabels: Record<string, string> = {
  default: "默认",
  off: "关闭",
  minimal: "最小",
  low: "低",
  medium: "中",
  high: "高",
  xhigh: "超高",
  max: "最高"
};

export function thinkingModeLabel(mode: string) {
  return thinkingModeLabels[mode] ?? mode;
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

export function liveModelRecordDurationMs(
  nowMs: number,
  persistedDurationMs: number,
  startedAtMs: number | null,
  fallbackStartedAtMs: number
) {
  return Math.max(
    MIN_THINKING_DURATION_MS,
    persistedDurationMs,
    nowMs - (startedAtMs ?? fallbackStartedAtMs)
  );
}

export function isAbortError(error: unknown) {
  return Boolean(error && typeof error === "object" && "name" in error && error.name === "AbortError");
}
