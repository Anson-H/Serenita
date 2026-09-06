export const CONVERSATION_TAIL_EXACT_THRESHOLD_PX = 1;
export const CONVERSATION_TAIL_SNAP_THRESHOLD_PX = 24;
export const CONVERSATION_CONSUMED_SOURCE_REQUEST_LIMIT = 64;

export type ConversationFollowIntent = "following" | "paused";
export type ConversationScrollOperation =
  | "idle"
  | "reconciling"
  | "returning"
  | "locating-source"
  | "preserving-anchor";
export type ConversationScrollDirection = "up" | "down";
export type ConversationScrollInputKind =
  | "keyboard"
  | "scrollbar"
  | "touch"
  | "wheel";

export type ConversationScrollGeometry = {
  clientHeight: number;
  scrollHeight: number;
  scrollTop: number;
};

export type ConversationTailMetrics = {
  atTail: boolean;
  maxScrollTop: number;
  nearTail: boolean;
  scrollTop: number;
  tailDistance: number;
};

export type ConversationScrollState = {
  atTail: boolean;
  consumedSourceRequestIds: readonly string[];
  followIntent: ConversationFollowIntent;
  geometryRevision: number;
  gestureId: number;
  lastForceReason: string | null;
  lastMutationKey: string | null;
  lastTailDistance: number;
  lastUserInputKind: ConversationScrollInputKind | null;
  nearTail: boolean;
  operation: ConversationScrollOperation;
  operationId: number;
  sessionId: string | null;
  sourceMessageId: string | null;
  sourceRequestId: string | null;
  sourceSessionId: string | null;
};

export type ConversationScrollEvent =
  | {
    type: "reset-session";
    sessionId: string | null;
  }
  | {
    type: "force-latest";
    reason: string;
  }
  | {
    type: "prepare-mutation";
    key: string;
    policy: "inherit-current";
  }
  | {
    type: "return-to-latest";
  }
  | {
    type: "locate-source";
    messageId: string;
    requestId: string;
    sessionId: string;
  }
  | {
    type: "consume-source";
    operationId: number;
    requestId: string;
  }
  | {
    type: "cancel-source";
  }
  | {
    type: "claim-by-user";
    direction: ConversationScrollDirection;
    geometry: ConversationScrollGeometry;
    inputKind: ConversationScrollInputKind;
  }
  | {
    type: "observe-geometry";
    geometry: ConversationScrollGeometry;
  }
  | {
    type: "complete-operation";
    operationId: number;
  };

function finiteNonNegative(value: number) {
  return Number.isFinite(value) ? Math.max(0, value) : 0;
}

/**
 * Safari can report a negative scrollTop while bouncing at the start and a
 * value larger than the scroll range while bouncing at the end. Consumers
 * must compare geometry using this clamped value without writing it back to
 * the DOM, otherwise a browser-only layout movement can be mistaken for user
 * intent.
 */
export function clampConversationScrollTop({
  clientHeight,
  scrollHeight,
  scrollTop
}: ConversationScrollGeometry) {
  const maxScrollTop = Math.max(
    0,
    finiteNonNegative(scrollHeight) - finiteNonNegative(clientHeight)
  );
  const finiteScrollTop = Number.isFinite(scrollTop) ? scrollTop : 0;
  return Math.min(maxScrollTop, Math.max(0, finiteScrollTop));
}

export function measureConversationTail(
  geometry: ConversationScrollGeometry
): ConversationTailMetrics {
  const clientHeight = finiteNonNegative(geometry.clientHeight);
  const scrollHeight = finiteNonNegative(geometry.scrollHeight);
  const maxScrollTop = Math.max(0, scrollHeight - clientHeight);
  const scrollTop = clampConversationScrollTop(geometry);
  const tailDistance = Math.max(0, maxScrollTop - scrollTop);
  return {
    atTail: tailDistance <= CONVERSATION_TAIL_EXACT_THRESHOLD_PX,
    maxScrollTop,
    nearTail: tailDistance <= CONVERSATION_TAIL_SNAP_THRESHOLD_PX,
    scrollTop,
    tailDistance
  };
}

export function createConversationScrollState(
  sessionId: string | null = null
): ConversationScrollState {
  return {
    atTail: true,
    consumedSourceRequestIds: [],
    followIntent: "following",
    geometryRevision: 0,
    gestureId: 0,
    lastForceReason: null,
    lastMutationKey: null,
    lastTailDistance: 0,
    lastUserInputKind: null,
    nearTail: true,
    operation: "idle",
    operationId: 0,
    sessionId,
    sourceMessageId: null,
    sourceRequestId: null,
    sourceSessionId: null
  };
}

function clearSourceRequest() {
  return {
    sourceMessageId: null,
    sourceRequestId: null,
    sourceSessionId: null
  } satisfies Pick<
    ConversationScrollState,
    "sourceMessageId" | "sourceRequestId" | "sourceSessionId"
  >;
}

function startOperation(
  state: ConversationScrollState,
  operation: ConversationScrollOperation
) {
  return {
    operation,
    operationId: state.operationId + 1
  } satisfies Pick<ConversationScrollState, "operation" | "operationId">;
}

export function reduceConversationScrollState(
  state: ConversationScrollState,
  event: ConversationScrollEvent
): ConversationScrollState {
  switch (event.type) {
    case "reset-session": {
      const preserveConsumedRequests = state.sessionId === event.sessionId;
      const preservePendingSource = preserveConsumedRequests && Boolean(
        state.sourceRequestId && state.sourceMessageId && state.sourceSessionId
      );
      return {
        ...createConversationScrollState(event.sessionId),
        atTail: false,
        consumedSourceRequestIds: preserveConsumedRequests
          ? state.consumedSourceRequestIds
          : [],
        followIntent: preservePendingSource ? "paused" : "following",
        geometryRevision: state.geometryRevision,
        gestureId: state.gestureId + 1,
        nearTail: false,
        operation: preservePendingSource ? "locating-source" : "reconciling",
        operationId: state.operationId + 1,
        sourceMessageId: preservePendingSource ? state.sourceMessageId : null,
        sourceRequestId: preservePendingSource ? state.sourceRequestId : null,
        sourceSessionId: preservePendingSource ? state.sourceSessionId : null
      };
    }

    case "force-latest":
      return {
        ...state,
        ...clearSourceRequest(),
        ...startOperation(state, "reconciling"),
        followIntent: "following",
        lastForceReason: event.reason,
        lastMutationKey: null
      };

    case "prepare-mutation": {
      if (state.lastMutationKey === event.key) {
        return state;
      }
      if (
        (state.operation === "locating-source" && state.sourceRequestId) ||
        (state.operation === "preserving-anchor" && state.followIntent === "paused")
      ) {
        return {
          ...state,
          lastMutationKey: event.key
        };
      }
      return {
        ...state,
        ...startOperation(
          state,
          state.followIntent === "following"
            ? "reconciling"
            : "preserving-anchor"
        ),
        lastMutationKey: event.key
      };
    }

    case "return-to-latest":
      return {
        ...state,
        ...clearSourceRequest(),
        ...startOperation(state, "returning"),
        followIntent: "following",
        lastMutationKey: null
      };

    case "locate-source": {
      if (
        event.sessionId !== state.sessionId ||
        state.consumedSourceRequestIds.includes(event.requestId) ||
        state.sourceRequestId === event.requestId
      ) {
        return state;
      }
      return {
        ...state,
        ...startOperation(state, "locating-source"),
        followIntent: "paused",
        lastMutationKey: null,
        sourceMessageId: event.messageId,
        sourceRequestId: event.requestId,
        sourceSessionId: event.sessionId
      };
    }

    case "consume-source": {
      if (
        event.operationId !== state.operationId ||
        event.requestId !== state.sourceRequestId ||
        state.operation !== "locating-source"
      ) {
        return state;
      }
      return {
        ...state,
        ...clearSourceRequest(),
        consumedSourceRequestIds: [
          ...state.consumedSourceRequestIds,
          event.requestId
        ].slice(-CONVERSATION_CONSUMED_SOURCE_REQUEST_LIMIT),
        followIntent: "paused",
        operation: "idle"
      };
    }

    case "cancel-source":
      return {
        ...state,
        ...clearSourceRequest(),
        operation:
          state.operation === "locating-source" ? "idle" : state.operation
      };

    case "claim-by-user": {
      const metrics = measureConversationTail(event.geometry);
      const shouldSnapToTail = event.direction === "down" && metrics.nearTail;
      return {
        ...state,
        ...clearSourceRequest(),
        ...startOperation(
          state,
          shouldSnapToTail && !metrics.atTail ? "reconciling" : "idle"
        ),
        atTail: metrics.atTail,
        followIntent:
          event.direction === "up"
            ? "paused"
            : shouldSnapToTail
              ? "following"
              : state.followIntent,
        gestureId: state.gestureId + 1,
        lastTailDistance: metrics.tailDistance,
        lastUserInputKind: event.inputKind,
        nearTail: metrics.nearTail
      };
    }

    case "observe-geometry": {
      const metrics = measureConversationTail(event.geometry);
      const shouldBeginReconciliation =
        state.followIntent === "following" &&
        !metrics.atTail &&
        state.operation === "idle";
      return {
        ...state,
        ...(shouldBeginReconciliation
          ? startOperation(state, "reconciling")
          : null),
        atTail: metrics.atTail,
        geometryRevision: state.geometryRevision + 1,
        lastTailDistance: metrics.tailDistance,
        nearTail: metrics.nearTail
      };
    }

    case "complete-operation":
      if (
        event.operationId !== state.operationId ||
        state.operation === "idle" ||
        state.operation === "locating-source" ||
        ((state.operation === "reconciling" ||
          state.operation === "returning") &&
          !state.atTail)
      ) {
        return state;
      }
      return {
        ...state,
        operation: "idle"
      };
  }
}
