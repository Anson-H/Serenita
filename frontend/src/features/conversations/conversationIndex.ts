import type { Dispatch, SetStateAction } from "react";
import type { ConversationSummary } from "../../api/client";

/** One owner arbitrates list reads and local event/mutation updates. */
export function createConversationIndex(
  read: () => Promise<{ sessions: ConversationSummary[] }>,
  publish: Dispatch<SetStateAction<ConversationSummary[]>>,
  isCurrent: () => boolean
) {
  let sequence = 0;
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
    pending.promise = read().then(response => {
      if (isCurrent() && pending.sequence === sequence && pending.relevant.some(check => check())) {
        publish(response.sessions);
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
    refresh
  };
}
