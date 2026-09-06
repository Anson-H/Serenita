import assert from "node:assert/strict";
import test from "node:test";
import { loadModule } from "./helpers/load-module.mjs";

const {
  CONVERSATION_CONSUMED_SOURCE_REQUEST_LIMIT, CONVERSATION_TAIL_EXACT_THRESHOLD_PX,
  CONVERSATION_TAIL_SNAP_THRESHOLD_PX, clampConversationScrollTop, createConversationScrollState,
  measureConversationTail, reduceConversationScrollState
} = loadModule("features/conversations/conversationScrollStateMachine.ts");

const geometry = (tailDistance, overrides = {}) => ({
  clientHeight: 500,
  scrollHeight: 1_500,
  scrollTop: 1_000 - tailDistance,
  ...overrides
});

const reduce = (state, ...events) =>
  events.reduce(reduceConversationScrollState, state);

test("state keeps following intent, operation, and exact tail alignment separate", () => {
  const state = createConversationScrollState("session-a");
  assert.equal(state.followIntent, "following");
  assert.equal(state.operation, "idle");
  assert.equal(state.atTail, true);

  const grown = reduceConversationScrollState(state, {
    type: "observe-geometry",
    geometry: geometry(50)
  });
  assert.equal(grown.followIntent, "following");
  assert.equal(grown.atTail, false);
  assert.equal(grown.operation, "reconciling");
});

test("tail measurement uses inclusive 1px exact and 24px snap thresholds", () => {
  assert.equal(CONVERSATION_TAIL_EXACT_THRESHOLD_PX, 1);
  assert.equal(CONVERSATION_TAIL_SNAP_THRESHOLD_PX, 24);

  for (const [distance, atTail, nearTail] of [
    [0, true, true],
    [1, true, true],
    [1.001, false, true],
    [24, false, true],
    [24.001, false, false]
  ]) {
    assert.deepEqual(
      (({ atTail: exact, nearTail: near }) => [exact, near])(
        measureConversationTail(geometry(distance))
      ),
      [atTail, nearTail],
      `tail distance ${distance}`
    );
  }
});

test("Safari bounce and invalid geometry are clamped before classification", () => {
  assert.equal(
    clampConversationScrollTop(geometry(1_000, { scrollTop: -37.5 })),
    0
  );
  assert.equal(
    clampConversationScrollTop(geometry(0, { scrollTop: 1_080.25 })),
    1_000
  );
  assert.equal(
    measureConversationTail(geometry(0, { scrollTop: 1_080.25 })).atTail,
    true
  );
  assert.equal(
    measureConversationTail({
      clientHeight: Number.NaN,
      scrollHeight: Number.POSITIVE_INFINITY,
      scrollTop: Number.NaN
    }).tailDistance,
    0
  );
});

test("geometry-only browser clamps never change paused user intent", () => {
  let state = createConversationScrollState("session-a");
  state = reduceConversationScrollState(state, {
    type: "claim-by-user",
    direction: "up",
    geometry: geometry(12),
    inputKind: "scrollbar"
  });
  assert.equal(state.followIntent, "paused");

  state = reduceConversationScrollState(state, {
    type: "observe-geometry",
    geometry: geometry(0, { scrollTop: 1_100 })
  });
  assert.equal(state.atTail, true);
  assert.equal(state.followIntent, "paused");
  assert.equal(state.operation, "idle");
});

test("operation tokens reject stale completion and require exact tail alignment", () => {
  let state = createConversationScrollState("session-a");
  state = reduceConversationScrollState(state, {
    type: "force-latest",
    reason: "new-turn"
  });
  const staleOperationId = state.operationId;
  state = reduceConversationScrollState(state, { type: "return-to-latest" });
  const returnOperationId = state.operationId;
  assert.ok(returnOperationId > staleOperationId);

  const staleCompletion = reduceConversationScrollState(state, {
    type: "complete-operation",
    operationId: staleOperationId
  });
  assert.strictEqual(staleCompletion, state);

  state = reduceConversationScrollState(state, {
    type: "observe-geometry",
    geometry: geometry(1.01)
  });
  assert.strictEqual(
    reduceConversationScrollState(state, {
      type: "complete-operation",
      operationId: returnOperationId
    }),
    state
  );

  state = reduceConversationScrollState(state, {
    type: "observe-geometry",
    geometry: geometry(1)
  });
  state = reduceConversationScrollState(state, {
    type: "complete-operation",
    operationId: returnOperationId
  });
  assert.equal(state.operation, "idle");
  assert.equal(state.followIntent, "following");
});

test("an upward user gesture always pauses and invalidates programmatic work", () => {
  let state = reduceConversationScrollState(
    createConversationScrollState("session-a"),
    { type: "return-to-latest" }
  );
  const programmaticOperationId = state.operationId;
  state = reduceConversationScrollState(state, {
    type: "claim-by-user",
    direction: "up",
    geometry: geometry(0.5),
    inputKind: "wheel"
  });
  assert.equal(state.followIntent, "paused");
  assert.equal(state.atTail, true);
  assert.equal(state.operation, "idle");
  assert.equal(state.gestureId, 1);
  assert.ok(state.operationId > programmaticOperationId);
});

test("a downward gesture resumes only inside the snap range and reconciles exactly", () => {
  let state = reduceConversationScrollState(
    createConversationScrollState("session-a"),
    {
      type: "claim-by-user",
      direction: "up",
      geometry: geometry(100),
      inputKind: "touch"
    }
  );
  state = reduceConversationScrollState(state, {
    type: "claim-by-user",
    direction: "down",
    geometry: geometry(24.001),
    inputKind: "touch"
  });
  assert.equal(state.followIntent, "paused");
  assert.equal(state.operation, "idle");

  state = reduceConversationScrollState(state, {
    type: "claim-by-user",
    direction: "down",
    geometry: geometry(24),
    inputKind: "touch"
  });
  assert.equal(state.followIntent, "following");
  assert.equal(state.operation, "reconciling");
  assert.equal(state.atTail, false);
});

test("source requests are session scoped, token guarded, and consumed once", () => {
  let state = createConversationScrollState("session-a");
  const wrongSession = reduceConversationScrollState(state, {
    type: "locate-source",
    messageId: "message-1",
    requestId: "request-1",
    sessionId: "session-b"
  });
  assert.strictEqual(wrongSession, state);

  state = reduceConversationScrollState(state, {
    type: "locate-source",
    messageId: "message-1",
    requestId: "request-1",
    sessionId: "session-a"
  });
  const sourceOperationId = state.operationId;
  assert.equal(state.followIntent, "paused");
  assert.equal(state.operation, "locating-source");
  assert.equal(state.sourceRequestId, "request-1");
  assert.strictEqual(
    reduceConversationScrollState(state, {
      type: "locate-source",
      messageId: "message-1",
      requestId: "request-1",
      sessionId: "session-a"
    }),
    state
  );
  assert.strictEqual(
    reduceConversationScrollState(state, {
      type: "consume-source",
      operationId: sourceOperationId - 1,
      requestId: "request-1"
    }),
    state
  );

  state = reduceConversationScrollState(state, {
    type: "consume-source",
    operationId: sourceOperationId,
    requestId: "request-1"
  });
  assert.equal(state.operation, "idle");
  assert.deepEqual(state.consumedSourceRequestIds, ["request-1"]);
  const replay = reduceConversationScrollState(state, {
    type: "locate-source",
    messageId: "message-1",
    requestId: "request-1",
    sessionId: "session-a"
  });
  assert.strictEqual(replay, state);
});

test("cancelling source location clears its target and rejects a late consumer", () => {
  let state = createConversationScrollState("session-a");
  state = reduceConversationScrollState(state, {
    type: "locate-source",
    messageId: "message-1",
    requestId: "request-1",
    sessionId: "session-a"
  });
  const sourceOperationId = state.operationId;
  const gestureId = state.gestureId;
  const geometryRevision = state.geometryRevision;

  state = reduceConversationScrollState(state, { type: "cancel-source" });
  assert.equal(state.sourceRequestId, null);
  assert.equal(state.sourceMessageId, null);
  assert.equal(state.sourceSessionId, null);
  assert.equal(state.operation, "idle");
  assert.equal(state.followIntent, "paused");
  assert.equal(state.operationId, sourceOperationId);
  assert.equal(state.gestureId, gestureId);
  assert.equal(state.geometryRevision, geometryRevision);

  const lateConsumer = reduceConversationScrollState(state, {
    type: "consume-source",
    operationId: sourceOperationId,
    requestId: "request-1"
  });
  assert.strictEqual(lateConsumer, state);
  assert.deepEqual(lateConsumer.consumedSourceRequestIds, []);
});

test("inherited mutations reconcile followers and preserve paused anchors", () => {
  let following = createConversationScrollState("session-a");
  following = reduceConversationScrollState(following, {
    type: "prepare-mutation",
    key: "queue:promoted:1",
    policy: "inherit-current"
  });
  assert.equal(following.followIntent, "following");
  assert.equal(following.operation, "reconciling");
  assert.strictEqual(
    reduceConversationScrollState(following, {
      type: "prepare-mutation",
      key: "queue:promoted:1",
      policy: "inherit-current"
    }),
    following
  );

  let paused = reduceConversationScrollState(
    createConversationScrollState("session-a"),
    {
      type: "claim-by-user",
      direction: "up",
      geometry: geometry(100),
      inputKind: "keyboard"
    }
  );
  paused = reduceConversationScrollState(paused, {
    type: "prepare-mutation",
    key: "stream:terminal:1",
    policy: "inherit-current"
  });
  assert.equal(paused.followIntent, "paused");
  assert.equal(paused.operation, "preserving-anchor");
  const preservingOperationId = paused.operationId;
  paused = reduceConversationScrollState(paused, {
    type: "prepare-mutation",
    key: "stream:terminal:2",
    policy: "inherit-current"
  });
  assert.equal(paused.operation, "preserving-anchor");
  assert.equal(paused.operationId, preservingOperationId);
  assert.equal(paused.lastMutationKey, "stream:terminal:2");
});

test("same-session remount keeps an unconsumed source with a fresh operation token", () => {
  let state = createConversationScrollState("session-a");
  state = reduceConversationScrollState(state, {
    type: "locate-source",
    messageId: "message-1",
    requestId: "request-1",
    sessionId: "session-a"
  });
  const staleOperationId = state.operationId;
  state = reduceConversationScrollState(state, {
    type: "reset-session",
    sessionId: "session-a"
  });
  assert.equal(state.followIntent, "paused");
  assert.equal(state.operation, "locating-source");
  assert.equal(state.sourceMessageId, "message-1");
  assert.equal(state.sourceRequestId, "request-1");
  assert.ok(state.operationId > staleOperationId);

  const lateConsumer = reduceConversationScrollState(state, {
    type: "consume-source",
    operationId: staleOperationId,
    requestId: "request-1"
  });
  assert.strictEqual(lateConsumer, state);

  state = reduceConversationScrollState(state, {
    type: "consume-source",
    operationId: state.operationId,
    requestId: "request-1"
  });
  assert.equal(state.operation, "idle");
  assert.deepEqual(state.consumedSourceRequestIds, ["request-1"]);
});

test("session reset invalidates work and keeps consumed requests only for remounts", () => {
  let state = createConversationScrollState("session-a");
  state = reduce(state, {
    type: "locate-source",
    messageId: "message-1",
    requestId: "request-1",
    sessionId: "session-a"
  });
  state = reduceConversationScrollState(state, {
    type: "consume-source",
    operationId: state.operationId,
    requestId: "request-1"
  });
  const oldOperationId = state.operationId;

  const remounted = reduceConversationScrollState(state, {
    type: "reset-session",
    sessionId: "session-a"
  });
  assert.deepEqual(remounted.consumedSourceRequestIds, ["request-1"]);
  assert.equal(remounted.operation, "reconciling");
  assert.ok(remounted.operationId > oldOperationId);

  const switched = reduceConversationScrollState(remounted, {
    type: "reset-session",
    sessionId: "session-b"
  });
  assert.deepEqual(switched.consumedSourceRequestIds, []);
  assert.equal(switched.sessionId, "session-b");
});

test("consumed source request history stays bounded within the active session", () => {
  let state = createConversationScrollState("session-a");
  for (let index = 0; index <= CONVERSATION_CONSUMED_SOURCE_REQUEST_LIMIT; index += 1) {
    const requestId = `request-${index}`;
    state = reduceConversationScrollState(state, {
      type: "locate-source",
      messageId: `message-${index}`,
      requestId,
      sessionId: "session-a"
    });
    state = reduceConversationScrollState(state, {
      type: "consume-source",
      operationId: state.operationId,
      requestId
    });
  }
  assert.equal(
    state.consumedSourceRequestIds.length,
    CONVERSATION_CONSUMED_SOURCE_REQUEST_LIMIT
  );
  assert.equal(state.consumedSourceRequestIds[0], "request-1");
  assert.equal(
    state.consumedSourceRequestIds.at(-1),
    `request-${CONVERSATION_CONSUMED_SOURCE_REQUEST_LIMIT}`
  );
});
