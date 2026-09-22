import type {MemoryProcessingStep} from "../../api/memory/memoryApi";

export function stepTimingLabel(step: MemoryProcessingStep | undefined, now: number, terminal: boolean): string {
  const timing = step?.details.timing;
  if (!timing) return step ? '未记录耗时' : '';
  const running = !terminal && ['running', 'retrying'].includes(step!.status) && !timing.finished_at;
  const start = Date.parse(timing.started_at);
  const seconds = running && Number.isFinite(start)
    ? Math.max(timing.elapsed_seconds, (now - start) / 1000) : timing.elapsed_seconds;
  const duration = seconds < 60 ? `${seconds.toFixed(3)} 秒`
    : `${Math.floor(seconds / 60)} 分 ${(seconds % 60).toFixed(1)} 秒`;
  return `${running ? '已用' : timing.finished_at ? '耗时' : '已记录耗时'} ${duration}`;
}
