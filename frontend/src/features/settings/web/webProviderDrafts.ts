import type { WebAccessSettings } from "../../../api/web/webTypes";
import { ResourceDraft } from "../../../utils/resourceDraft";
import { SerialTasks } from "../../../utils/serialTasks";
import type { TestState } from "../../../utils/requestStatus";

export interface WebDraftApi {
  updateWebProviderSettings(providerId: string, value: string): Promise<WebAccessSettings>;
  saveWebProviderCredential(providerId: string, value: string): Promise<WebAccessSettings>;
}
type Field = "url" | "credential";
type ProviderDrafts = { url: ResourceDraft<string>; credential: ResourceDraft<string> };

/** Owns submitted snapshots and acknowledgements; the view never manages a second save queue. */
export class WebProviderDrafts {
  private providers = new Map<string, ProviderDrafts>();
  private listeners = new Set<() => void>();
  private revision = 0;
  private composing = false;
  constructor(private readonly dependencies: {
    api: WebDraftApi;
    serialTasks: SerialTasks;
    isCurrentScope: () => boolean;
    onSaved: (providerId: string, settings: WebAccessSettings) => void;
    onFeedback: (providerId: string, field: Field, feedback: TestState) => void;
  }) { }
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  snapshot = () => this.revision;
  private publish = () => { this.revision += 1; this.listeners.forEach(listener => listener()); };
  private entry(id: string) {
    let entry = this.providers.get(id);
    if (!entry) {
      entry = { url: new ResourceDraft(""), credential: new ResourceDraft("") };
      for (const draft of Object.values(entry)) { draft.subscribe(this.publish); draft.composition(this.composing); }
      this.providers.set(id, entry);
    }
    return entry;
  }
  receive(settings: WebAccessSettings) {
    for (const provider of settings.providers) this.entry(provider.provider_id).url.receive(provider.api_url);
    this.publish();
  }
  values(field: Field): Record<string, string> {
    return Object.fromEntries([...this.providers].map(([id, entry]) => [id, entry[field].snapshot().draft]));
  }
  value(id: string, field: Field) { return this.entry(id)[field].snapshot().draft; }
  update(id: string, field: Field, value: string) { this.entry(id)[field].update(value); }
  credentialRevision(id: string) { return this.entry(id).credential.snapshot().revision; }
  receiveCredential(id: string, value: string, revision: number) {
    const draft = this.entry(id).credential;
    if (draft.snapshot().revision !== revision || draft.snapshot().dirty) return false;
    draft.receive(value.trim());
    return true;
  }
  hasCredential(id: string) { return Boolean(this.entry(id).credential.snapshot().confirmed.trim()); }
  composition(value: boolean) {
    this.composing = value;
    for (const entry of this.providers.values()) for (const draft of Object.values(entry)) draft.composition(value);
  }
  dispose() { for (const entry of this.providers.values()) for (const draft of Object.values(entry)) draft.pause(); }
  resume() { for (const entry of this.providers.values()) for (const draft of Object.values(entry)) draft.resume(); }
  async flushField(id: string, field: Field) {
    const { api, serialTasks, isCurrentScope, onSaved, onFeedback } = this.dependencies;
    const draft = this.entry(id)[field];
    const saved = await draft.flush(async (submitted) => {
      const value = field === "url" ? submitted.trim().replace(/\/+$/, "") : submitted.trim();
      if (!value) throw new Error(field === "url" ? "API 地址不能为空。" : "请输入 API key。");
      onFeedback(id, field, { status: "saving", message: "" });
      const result = await serialTasks.run(`web:${id}`, () => field === "url"
        ? api.updateWebProviderSettings(id, value) : api.saveWebProviderCredential(id, value), isCurrentScope);
      if (!isCurrentScope()) throw new Error("设置作用域已改变。");
      onSaved(id, result);
      return field === "url" ? result.providers.find(provider => provider.provider_id === id)?.api_url ?? value : value;
    });
    if (isCurrentScope()) onFeedback(id, field, saved
      ? { status: "idle", message: "" }
      : { status: "error", message: draft.snapshot().error });
    return saved;
  }
  async flush() {
    const results = await Promise.all([...this.providers.keys()].flatMap(id => [this.flushField(id, "url"), this.flushField(id, "credential")]));
    return results.every(Boolean);
  }
}
