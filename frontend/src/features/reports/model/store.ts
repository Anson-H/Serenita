/** Observable report state; only the owning controller can publish changes. */
export class ReportStore<T extends object> {
  private listeners = new Set<() => void>();
  constructor(protected state: Readonly<T>) {}
  snapshot = (): Readonly<T> => this.state;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  };
  protected publish(changes: Partial<T>) {
    this.state = { ...this.state, ...changes };
    this.listeners.forEach(listener => listener());
  }
}
