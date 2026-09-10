import type { ConversationDetail } from "../../../api/types";

type UpdateDetail = (update: (detail: ConversationDetail | null) => ConversationDetail | null) => void;

/** A refresh batches outstanding invalidations and only applies to its original view. */
export class ReportStateRefresher {
  private sequence = 0;
  private scope = "";
  private pending = new Set<string>();

  constructor(private read: (sessionId: string) => Promise<ConversationDetail>) { }

  invalidate() {
    this.sequence += 1;
    this.pending.clear();
    this.scope = "";
  }

  async refresh(options: {
    sessionId: string; memberId: string; reportIds: string[];
    isCurrent: () => boolean; update: UpdateDetail; onError: () => void;
  }) {
    if (!options.isCurrent() || !options.reportIds.length) return;
    const scope = JSON.stringify([options.sessionId, options.memberId]);
    if (scope !== this.scope) { this.invalidate(); this.scope = scope; }
    options.reportIds.forEach(id => this.pending.add(id));
    const ids = new Set(this.pending);
    const sequence = ++this.sequence;
    const current = () => sequence === this.sequence && options.isCurrent();
    const matches = (state: ConversationDetail["resource_states"][number]) =>
      state.member_id === options.memberId && ids.has(state.resource_id);
    options.update(detail => current() && detail?.session_id === options.sessionId
      ? { ...detail, resource_states: detail.resource_states.filter(state => !matches(state)) } : detail);
    try {
      const fresh = await this.read(options.sessionId);
      if (!current()) return;
      if (fresh.session_id !== options.sessionId) throw new Error("会话响应不匹配。");
      options.update(detail => current() && detail?.session_id === options.sessionId
        ? {
          ...detail, resource_states: [
            ...detail.resource_states.filter(state => !matches(state)),
            ...fresh.resource_states.filter(matches)
          ]
        } : detail);
      this.pending.clear();
    } catch {
      if (current()) options.onError();
    }
  }
}
