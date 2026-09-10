import type { ConversationDetail, UploadedResource } from "../../api/client";
import type { UploadingResource } from "./contextResources";
import type { AnnotatedContext, AnnotationSelection } from "./workspaceTypes";

export type ComposerDraft = {
  composerText: string;
  uploadedResources: UploadedResource[];
  uploadingResources: UploadingResource[];
  annotatedContexts: AnnotatedContext[];
  annotationSelection: AnnotationSelection | null;
  restoring: boolean;
  contextResources: Array<Record<string, unknown>>;
};
export type DraftRecord = {
  value: ComposerDraft;
  sessionId: string | null;
  detail: ConversationDetail | null;
  valid: boolean;
  uploads: Promise<unknown>;
};
const empty = (): ComposerDraft => ({ composerText: "", uploadedResources: [], uploadingResources: [], annotatedContexts: [], annotationSelection: null, restoring: false, contextResources: [] });

/** Owns unsent input and upload tasks independently of the visible route. */
export class ConversationDraftStore {
  private current = this.create();
  private listeners = new Set<() => void>();
  private sessions = new Map<string, DraftRecord>();
  private create(): DraftRecord { return { value: empty(), sessionId: null, detail: null, valid: true, uploads: Promise.resolve() }; }
  capture = () => this.current;
  isCurrent = (draft: DraftRecord) => draft.valid && this.current === draft;
  snapshot = () => this.current.value;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  private notify(draft: DraftRecord) { if (this.current === draft) for (const listener of this.listeners) listener(); }
  patch(draft: DraftRecord, changes: Partial<ComposerDraft>) {
    if (!draft.valid) return;
    if (Object.entries(changes).every(([key, value]) => draft.value[key as keyof ComposerDraft] === value)) return;
    draft.value = { ...draft.value, ...changes }; this.notify(draft);
  }
  update<K extends keyof ComposerDraft>(key: K, next: ComposerDraft[K] | ((value: ComposerDraft[K]) => ComposerDraft[K])) {
    if (this.current.value.restoring) return;
    const value = typeof next === "function" ? (next as (value: ComposerDraft[K]) => ComposerDraft[K])(this.current.value[key]) : next;
    this.patch(this.current, { [key]: value });
  }
  reset = () => { this.current = this.create(); this.notify(this.current); };
  associate = (draft: DraftRecord, sessionId: string) => { if (draft.valid) { draft.sessionId = sessionId; this.sessions.set(sessionId, draft); } };
  remember = (sessionId: string | null) => { if (sessionId) this.associate(this.current, sessionId); };
  openSession = (sessionId: string) => { const saved = this.sessions.get(sessionId); this.current = saved?.valid ? saved : this.create(); this.associate(this.current, sessionId); this.notify(this.current); };
  forgetSessions = (sessionIds: string[]) => {
    for (const id of sessionIds) { const draft = this.sessions.get(id); if (draft) draft.valid = false; this.sessions.delete(id); }
    if (this.current.sessionId && sessionIds.includes(this.current.sessionId)) { this.current.valid = false; this.reset(); }
  };
  clear = () => { for (const draft of this.sessions.values()) draft.valid = false; this.current.valid = false; this.sessions.clear(); this.reset(); };
  restore = (draft: DraftRecord) => { if (draft.valid) { this.current = draft; this.notify(draft); } };
  discard = (draft: DraftRecord) => { draft.valid = false; };
  complete = (draft: DraftRecord, sessionId: string) => {
    const visible = this.isCurrent(draft);
    draft.valid = false;
    const next = this.create(); next.sessionId = sessionId;
    this.sessions.set(sessionId, next);
    if (visible) { this.current = next; this.notify(next); }
  };
  beginRestore = () => {
    const draft = this.current;
    if (draft.value.restoring || draft.value.composerText || draft.value.uploadedResources.length || draft.value.uploadingResources.length || draft.value.annotatedContexts.length || draft.value.contextResources.length) return null;
    this.patch(draft, { restoring: true });
    return draft;
  };
  endRestore = (draft: DraftRecord) => this.patch(draft, { restoring: false });
}
