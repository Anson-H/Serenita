/** Owns scheduled edits, per-target coalescing, rename tracking and completion waits. */
export class LabAutosaveQueue<Job extends { targetKey: string }> {
  private jobs: Job[] = [];
  private timer: ReturnType<typeof setTimeout> | null = null;
  private scheduled: (() => void) | null = null;
  private pending: Promise<void> | null = null;
  private targets = new Map<string, string>();
  constructor(private readonly save: (job: Job) => Promise<void>, private readonly onChange: () => void, private readonly onError: (error: unknown) => void) { }
  get running() { return this.pending !== null; }
  resolve(target: string) {
    let value = this.targets.get(target) ?? "";
    const visited = new Set<string>();
    while (value && !visited.has(value)) {
      visited.add(value);
      const next = this.targets.get(value);
      if (!next) break;
      value = next;
    }
    return value;
  }
  remember(from: string, to: string) { this.targets.set(from, to); }
  enqueue(job: Job) {
    this.jobs = [...this.jobs.filter(queued => queued.targetKey !== job.targetKey), job];
    void this.drain();
  }
  schedule(submit: (() => void) | null, immediate: boolean) {
    this.cancelTimer();
    if (!submit) return;
    if (immediate) { submit(); return; }
    this.scheduled = submit;
    this.timer = setTimeout(() => this.flushScheduled(), 550);
  }
  flushScheduled() {
    const submit = this.scheduled;
    this.cancelTimer();
    submit?.();
  }
  private cancelTimer() {
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = null; this.scheduled = null;
  }
  cancelTargets(targets: Set<string>, selected: string) {
    if (targets.has(selected)) this.cancelTimer();
    this.jobs = this.jobs.filter(job => !targets.has(job.targetKey));
  }
  discard() { this.jobs = []; }
  dispose() { this.cancelTimer(); this.discard(); }
  private drain() {
    if (this.pending) return this.pending;
    this.pending = Promise.resolve().then(async () => {
      try { while (this.jobs.length) await this.save(this.jobs.shift()!); }
      catch (error) { this.discard(); this.onError(error); }
    }).finally(() => { this.pending = null; this.onChange(); });
    this.onChange();
    return this.pending;
  }
}
