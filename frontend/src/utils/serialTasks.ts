/** Serializes writes to one resource without coupling unrelated resources. */
export class SerialTasks {
  private readonly pending = new Map<string, Promise<unknown>>();
  run<T>(key: string, task: () => Promise<T>, isCurrent: () => boolean): Promise<T> {
    const run = async () => {
      if (!isCurrent()) { const error = new Error('操作所属页面已改变。'); error.name = 'AbortError'; throw error; }
      return task();
    };
    const result = (this.pending.get(key) ?? Promise.resolve()).then(run, run);
    this.pending.set(key, result);
    const cleanup = () => { if (this.pending.get(key) === result) this.pending.delete(key); };
    void result.then(cleanup, cleanup);
    return result;
  }
}
