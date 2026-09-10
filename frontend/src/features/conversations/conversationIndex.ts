import type { Dispatch, SetStateAction } from "react";
import type { ConversationSummary } from "../../api/client";

/** One owner arbitrates list reads and local event/mutation updates. */
export function createConversationIndex(
  read: (cursor?: string) => Promise<{ sessions: ConversationSummary[]; next_cursor?: string | null }>,
  publish: Dispatch<SetStateAction<ConversationSummary[]>>,
  isCurrent: () => boolean,
  publishPage: (hasMore: boolean) => void = () => {}
) {
  let sequence = 0;
  let pages = 1;
  let nextCursor: string | null = null;
  let loadingMore: Promise<void> | null = null;

  async function readVisiblePages() {
    let cursor: string | undefined;
    const sessions: ConversationSummary[] = [];
    const seen = new Set<string>();
    for (let page = 0; page < pages; page++) {
      const result = await read(cursor);
      if (!isCurrent()) return { sessions: [], next_cursor: null };
      for (const session of result.sessions) {
        if (!seen.has(session.session_id)) { seen.add(session.session_id); sessions.push(session); }
      }
      cursor = result.next_cursor ?? undefined;
      if (!cursor) break;
    }
    return { sessions, next_cursor: cursor ?? null };
  }
  let inFlight: { sequence: number; relevant: Array<() => boolean>; promise: Promise<void> } | null = null;
  async function refresh(isRelevant: () => boolean = () => true): Promise<void> {
    if (!isCurrent() || !isRelevant()) return;
    if (inFlight) {
      const pending = inFlight;
      if (pending.sequence === sequence) {
        pending.relevant.push(isRelevant);
        return pending.promise;
      }
      // A mutation requires a newer snapshot, after the existing read ends.
      await pending.promise.catch(() => undefined);
      return refresh(isRelevant);
    }
    const pending = { sequence, relevant: [isRelevant], promise: Promise.resolve() };
    inFlight = pending;
    pending.promise = readVisiblePages().then(response => {
      if (isCurrent() && pending.sequence === sequence && pending.relevant.some(check => check())) {
        nextCursor = response.next_cursor;
        publish(response.sessions);
        publishPage(Boolean(nextCursor));
      }
    }).finally(() => { if (inFlight === pending) inFlight = null; });
    return pending.promise;
  }
  return {
    update(next: SetStateAction<ConversationSummary[]>) {
      if (!isCurrent()) return;
      sequence += 1;
      publish(next);
    },
    async loadMore() {
      if (loadingMore) return loadingMore;
      if (inFlight) await inFlight.promise;
      if (!isCurrent() || !nextCursor) return;
      const captured = sequence;
      loadingMore = read(nextCursor).then(response => {
        if (!isCurrent() || captured !== sequence) return;
        pages += 1;
        sequence += 1;
        nextCursor = response.next_cursor ?? null;
        publish(current => {
          const existing = new Set(current.map(session => session.session_id));
          return [...current, ...response.sessions.filter(session => !existing.has(session.session_id))];
        });
        publishPage(Boolean(nextCursor));
      }).finally(() => { loadingMore = null; });
      return loadingMore;
    },
    refresh
  };
}
