export type DraftSnapshot<T> = {
  server: T;
  confirmed: T;
  draft: T;
  submitted: T | undefined;
  revision: number;
  pending: boolean;
  error: string;
  dirty: boolean;
};

/** One resource's draft survives refreshes, slow acknowledgements and failures. */
export class ResourceDraft<T> {
  private state: DraftSnapshot<T>;
  private listeners = new Set<() => void>();
  private running?: Promise<boolean>;
  private composing?: { done: Promise<void>; resolve: () => void };
  private paused = false;
  pause() { this.paused = true; this.composition(false); }
  resume() { this.paused = false; }
  settled() { return this.running ?? Promise.resolve(true); }
  constructor(
    server: T,
    private same = (a: T, b: T) => JSON.stringify(a) === JSON.stringify(b),
  ) {
    this.state = {
      server,
      confirmed: server,
      draft: server,
      submitted: undefined,
      revision: 0,
      pending: false,
      error: "",
      dirty: false,
    };
  }
  snapshot = () => this.state;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };
  private publish(patch: Partial<DraftSnapshot<T>>) {
    this.state = { ...this.state, ...patch };
    this.state.dirty = !this.same(this.state.draft, this.state.confirmed);
    this.listeners.forEach((listener) => listener());
  }
  update = (draft: T) => {
    if (!this.same(draft, this.state.draft))
      this.publish({ draft, revision: this.state.revision + 1, error: "" });
  };
  restore = (draft: T) => {
    if (!this.same(draft, this.state.draft))
      this.publish({ draft, revision: this.state.revision + 1 });
  };
  receive(server: T, editing = false) {
    if (this.state.pending) return;
    if (this.same(server, this.state.server) && (this.state.dirty || editing || (this.same(server, this.state.draft) && this.same(server, this.state.confirmed)))) return;
    this.publish({
      server,
      ...(!this.state.dirty && !editing
        ? { draft: server, confirmed: server }
        : {}),
    });
  }
  cancel() {
    if (!this.state.pending)
      this.publish({
        draft: this.state.server,
        confirmed: this.state.server,
        error: "",
      });
  }
  composition(start: boolean) {
    if (start && !this.composing) {
      let resolve!: () => void;
      this.composing = {
        done: new Promise<void>((done) => {
          resolve = done;
        }),
        resolve: () => resolve(),
      };
    } else if (!start) {
      this.composing?.resolve();
      this.composing = undefined;
    }
  }
  flush(
    save: (value: T) => Promise<T>,
    validate: (value: T) => string = () => "",
    force = false,
  ): Promise<boolean> {
    if (this.running) return this.running;
    const execute = async () => {
      while (true) {
        if (this.paused) return !this.state.dirty;
        if (this.composing) await this.composing.done;
        if (this.paused) return !this.state.dirty;
        if (!this.state.dirty && !force) return true;
        force = false;
        const submitted = this.state.draft;
        const revision = this.state.revision;
        const error = validate(submitted);
        if (error) {
          this.publish({ error });
          return false;
        }
        this.publish({ submitted, pending: true, error: "" });
        try {
          const server = await save(submitted);
          this.publish({
            server,
            confirmed: server,
            pending: false,
            ...(revision === this.state.revision ? { draft: server } : {}),
          });
        } catch (reason) {
          this.publish({
            pending: false,
            error:
              reason instanceof Error ? reason.message : "保存失败，请重试。",
          });
          return false;
        }
      }
    };
    this.running = Promise.resolve()
      .then(execute)
      .finally(() => {
        this.running = undefined;
      });
    return this.running;
  }
}
