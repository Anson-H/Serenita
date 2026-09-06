import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type MutableRefObject,
  type RefObject
} from "react";
import { installConversationInputListeners } from "./conversationInputListeners";
import { SCROLL_BOUNDARY_EPSILON_PX, findConsumableVerticalScroller, geometryFor, hasNestedVerticalScroller, isEditableOrInteractiveTarget, normalizedScrollTop, normalizedWheelDelta, readableConversationRect, shouldShowTailButton } from "./conversationScrollGeometry";
import {
  clampConversationScrollTop,
  createConversationScrollState,
  measureConversationTail,
  reduceConversationScrollState,
  type ConversationScrollDirection,
  type ConversationScrollEvent,
  type ConversationScrollGeometry,
  type ConversationScrollInputKind,
  type ConversationScrollState
} from "./conversationScrollStateMachine";

const GESTURE_IDLE_MS = 120;

const RETURN_RECONCILE_TIMEOUT_MS = 2000;

const ANCHOR_RECONCILE_TIMEOUT_MS = 2000;

const PROGRAMMATIC_SCROLL_EXPIRY_MS = 250;

const OVERLAY_SCROLLBAR_HIT_WIDTH_PX = 16;

const MAX_STALLED_RECONCILE_FRAMES = 2;

const STABLE_GEOMETRY_FRAMES = 2;

type ReadingAnchor = {
  messageId: string | null;
  node: HTMLElement;
  viewportTop: number;
};

type ActiveGesture = {
  direction: ConversationScrollDirection | null;
  inputKind: ConversationScrollInputKind;
  stale: boolean;
};

type TouchGesture = {
  lastY: number;
  stale: boolean;
  target: EventTarget | null;
};

type ProgrammaticScroll = {
  expectedTop: number;
  operationId: number;
  origin: string;
  surface: HTMLDivElement;
};

type ReconcileProgress = {
  attemptedFromTop: number;
  attemptedTargetTop: number;
  lastError: number;
  operationId: number;
  stalledFrames: number;
};

type ContentObserverNodes = {
  flow: HTMLElement;
  messageList: HTMLDivElement;
  sentinel: HTMLElement | null;
  surface: HTMLDivElement;
};

type UseConversationScrollControllerOptions = {
  bindingKey: string;
  conversationSessionId: string | null;
  conversationStageRef: RefObject<HTMLDivElement | null>;
  conversationSurfaceRef: RefObject<HTMLDivElement | null>;
  highlightedMessageId: string | null;
  highlightedMessageRequestId: number;
  messageListRef: RefObject<HTMLDivElement | null>;
  messageRefs: MutableRefObject<Map<string, HTMLElement>>;
  onClearAnnotationSelection: () => void;
};

function initialReconcileProgress(operationId = -1): ReconcileProgress {
  return {
    attemptedFromTop: Number.NaN,
    attemptedTargetTop: Number.NaN,
    lastError: Number.POSITIVE_INFINITY,
    operationId,
    stalledFrames: 0
  };
}

export function useConversationScrollController({
  bindingKey,
  conversationSessionId,
  conversationStageRef,
  conversationSurfaceRef,
  highlightedMessageId,
  highlightedMessageRequestId,
  messageListRef,
  messageRefs,
  onClearAnnotationSelection
}: UseConversationScrollControllerOptions) {
  const [state, setState] = useState<ConversationScrollState>(() =>
    createConversationScrollState(conversationSessionId)
  );
  const [reconciliationSuspended, setReconciliationSuspended] = useState(false);
  const [surfaceBindingRevision, setSurfaceBindingRevision] = useState(0);
  const stateRef = useRef(state);
  const onClearAnnotationSelectionRef = useRef(onClearAnnotationSelection);
  const observedSurfaceRef = useRef<HTMLDivElement | null>(null);
  const observedSessionRef = useRef<string | null>(conversationSessionId);
  const reconcileFrameRef = useRef<number | null>(null);
  const programmaticClearTimerRef = useRef<number | null>(null);
  const operationStartedAtRef = useRef(0);
  const settleRef = useRef({
    frames: 0,
    geometryRevision: -1,
    operationId: -1
  });
  const sourceCenterRef = useRef({ frames: 0, operationId: -1, top: Number.NaN });
  const reconcileProgressRef = useRef<ReconcileProgress>(initialReconcileProgress());
  const suspendedReconciliationRef = useRef<number | null>(null);
  const reconciliationSuspendedRef = useRef(false);
  const readingAnchorRef = useRef<ReadingAnchor | null>(null);
  const messageIdByElementRef = useRef(new WeakMap<HTMLElement, string>());
  const programmaticOriginRef = useRef<ProgrammaticScroll | null>(null);
  const contentObserverNodesRef = useRef<ContentObserverNodes | null>(null);
  const contentObserverCleanupRef = useRef<(() => void) | null>(null);
  const activeGestureRef = useRef<ActiveGesture | null>(null);
  const wheelGestureRef = useRef<ActiveGesture | null>(null);
  const wheelIdleTimerRef = useRef<number | null>(null);
  const scrollIdleTimerRef = useRef<number | null>(null);
  const touchGestureRef = useRef<TouchGesture | null>(null);
  const lastObservedScrollTopRef = useRef(0);
  const returnFocusButtonRef = useRef<HTMLButtonElement | null>(null);
  const mutationSequenceRef = useRef(0);
  const geometryInvalidationFrameRef = useRef<number | null>(null);

  onClearAnnotationSelectionRef.current = onClearAnnotationSelection;

  const updateReconciliationSuspended = useCallback((value: boolean) => {
    if (reconciliationSuspendedRef.current === value) {
      return;
    }
    const current = stateRef.current;
    if (
      shouldShowTailButton(current, reconciliationSuspendedRef.current) &&
      !shouldShowTailButton(current, value)
    ) {
      const tailButton = conversationStageRef.current?.querySelector<HTMLElement>(
        ".conversation-tail-button"
      );
      if (tailButton && tailButton === document.activeElement) {
        conversationSurfaceRef.current?.focus({ preventScroll: true });
      }
    }
    reconciliationSuspendedRef.current = value;
    setReconciliationSuspended(value);
  }, [conversationStageRef, conversationSurfaceRef]);

  const commit = useCallback((event: ConversationScrollEvent) => {
    const current = stateRef.current;
    const next = reduceConversationScrollState(current, event);
    if (next === current) {
      return current;
    }
    const startsNewOperation = next.operationId !== current.operationId;
    const currentButtonVisible = shouldShowTailButton(
      current,
      reconciliationSuspendedRef.current
    );
    const nextButtonVisible = shouldShowTailButton(
      next,
      startsNewOperation ? false : reconciliationSuspendedRef.current
    );
    if (currentButtonVisible && !nextButtonVisible) {
      const tailButton = conversationStageRef.current?.querySelector<HTMLElement>(
        ".conversation-tail-button"
      );
      if (tailButton && tailButton === document.activeElement) {
        conversationSurfaceRef.current?.focus({ preventScroll: true });
      }
    }
    if (startsNewOperation) {
      updateReconciliationSuspended(false);
      operationStartedAtRef.current = performance.now();
      suspendedReconciliationRef.current = null;
      settleRef.current = {
        frames: 0,
        geometryRevision: next.geometryRevision,
        operationId: next.operationId
      };
      sourceCenterRef.current = {
        frames: 0,
        operationId: next.operationId,
        top: Number.NaN
      };
      reconcileProgressRef.current = initialReconcileProgress(next.operationId);
    }
    stateRef.current = next;
    setState(next);
    return next;
  }, [conversationStageRef, conversationSurfaceRef, updateReconciliationSuspended]);

  const clearProgrammaticScroll = useCallback(() => {
    programmaticOriginRef.current = null;
    if (programmaticClearTimerRef.current !== null) {
      window.clearTimeout(programmaticClearTimerRef.current);
      programmaticClearTimerRef.current = null;
    }
  }, []);

  const supersedeUserGesture = useCallback(() => {
    if (wheelGestureRef.current) {
      wheelGestureRef.current.stale = true;
    }
    if (touchGestureRef.current) {
      touchGestureRef.current.stale = true;
    }
    activeGestureRef.current = null;
  }, []);

  const resumeSuspendedReconciliation = useCallback((operationId: number) => {
    if (suspendedReconciliationRef.current !== operationId) {
      return;
    }
    suspendedReconciliationRef.current = null;
    updateReconciliationSuspended(false);
    operationStartedAtRef.current = performance.now();
    reconcileProgressRef.current = initialReconcileProgress(operationId);
  }, [updateReconciliationSuspended]);

  const markProgrammaticScroll = useCallback((
    surface: HTMLDivElement,
    expectedTop: number,
    origin: string
  ) => {
    programmaticOriginRef.current = {
      expectedTop,
      operationId: stateRef.current.operationId,
      origin,
      surface
    };
    if (programmaticClearTimerRef.current !== null) {
      window.clearTimeout(programmaticClearTimerRef.current);
    }
    programmaticClearTimerRef.current = window.setTimeout(
      clearProgrammaticScroll,
      PROGRAMMATIC_SCROLL_EXPIRY_MS
    );
  }, [clearProgrammaticScroll]);

  const consumeProgrammaticScroll = useCallback((
    surface: HTMLDivElement,
    scrollTop: number
  ) => {
    const pending = programmaticOriginRef.current;
    if (!pending) {
      return false;
    }
    const matches =
      pending.surface === surface &&
      pending.operationId === stateRef.current.operationId &&
      Math.abs(pending.expectedTop - scrollTop) <= SCROLL_BOUNDARY_EPSILON_PX;
    if (matches || pending.surface !== surface || pending.operationId !== stateRef.current.operationId) {
      clearProgrammaticScroll();
    }
    return matches;
  }, [clearProgrammaticScroll]);

  const writeScrollTop = useCallback((
    surface: HTMLDivElement,
    top: number,
    origin: string
  ) => {
    const targetTop = clampConversationScrollTop({
      ...geometryFor(surface),
      scrollTop: top
    });
    markProgrammaticScroll(surface, targetTop, origin);
    surface.scrollTo({ top: targetTop, behavior: "auto" });
    lastObservedScrollTopRef.current = normalizedScrollTop(surface);
    return targetTop;
  }, [markProgrammaticScroll]);

  const writeScrollBy = useCallback((
    surface: HTMLDivElement,
    delta: number,
    origin: string
  ) => {
    writeScrollTop(
      surface,
      normalizedScrollTop(surface) + delta,
      origin
    );
  }, [writeScrollTop]);

  const resolveReadingAnchorNode = useCallback((anchor: ReadingAnchor) => {
    if (anchor.node.isConnected) {
      return anchor.node;
    }
    return anchor.messageId ? messageRefs.current.get(anchor.messageId) ?? null : null;
  }, [messageRefs]);

  const findRegisteredMessage = useCallback((node: Element | null) => {
    const surface = conversationSurfaceRef.current;
    let current = node;
    while (current && current !== surface) {
      if (current instanceof HTMLElement) {
        const messageId = messageIdByElementRef.current.get(current);
        if (messageId) {
          return { messageId, node: current };
        }
      }
      current = current.parentElement;
    }
    return null;
  }, [conversationSurfaceRef]);

  const captureReadingAnchor = useCallback((preferred?: HTMLElement | null) => {
    const surface = conversationSurfaceRef.current;
    if (!surface) {
      return null;
    }
    if (preferred && surface.contains(preferred)) {
      const registered = findRegisteredMessage(preferred);
      const anchor = {
        messageId: registered?.messageId ?? null,
        node: preferred,
        viewportTop: preferred.getBoundingClientRect().top
      };
      readingAnchorRef.current = anchor;
      return anchor;
    }

    const readableRect = readableConversationRect(
      surface,
      conversationStageRef.current
    );
    const surfaceRect = surface.getBoundingClientRect();
    const sampleX = [
      surfaceRect.left + 1,
      surfaceRect.left + surfaceRect.width / 2,
      surfaceRect.right - 1
    ];
    const sampleY = [1, 16, 32, 48]
      .map((offset) => readableRect.top + offset)
      .filter((value) => value < readableRect.bottom);
    let candidate: { messageId: string; node: HTMLElement; rect: DOMRect } | null = null;

    for (const y of sampleY) {
      for (const x of sampleX) {
        const registered = findRegisteredMessage(document.elementFromPoint(x, y));
        if (!registered || !registered.node.isConnected) {
          continue;
        }
        const rect = registered.node.getBoundingClientRect();
        if (
          rect.bottom > readableRect.top + SCROLL_BOUNDARY_EPSILON_PX &&
          rect.top < readableRect.bottom - SCROLL_BOUNDARY_EPSILON_PX &&
          (!candidate || rect.top < candidate.rect.top)
        ) {
          candidate = { ...registered, rect };
        }
      }
      if (candidate) {
        break;
      }
    }

    if (!candidate) {
      for (const [messageId, node] of messageRefs.current) {
        if (!node.isConnected) {
          continue;
        }
        const rect = node.getBoundingClientRect();
        if (
          rect.bottom > readableRect.top + SCROLL_BOUNDARY_EPSILON_PX &&
          rect.top < readableRect.bottom - SCROLL_BOUNDARY_EPSILON_PX &&
          (!candidate || rect.top < candidate.rect.top)
        ) {
          candidate = { messageId, node, rect };
        }
      }
    }
    if (!candidate) {
      readingAnchorRef.current = null;
      return null;
    }
    const anchor = {
      messageId: candidate.messageId,
      node: candidate.node,
      viewportTop: candidate.rect.top
    };
    readingAnchorRef.current = anchor;
    return anchor;
  }, [conversationStageRef, conversationSurfaceRef, findRegisteredMessage, messageRefs]);

  const scheduleReconciliation = useCallback(() => {
    if (reconcileFrameRef.current !== null) {
      return;
    }
    reconcileFrameRef.current = window.requestAnimationFrame(runReconciliation);
  }, []);

  const observeCurrentGeometry = useCallback(() => {
    const surface = conversationSurfaceRef.current;
    if (!surface) {
      return stateRef.current;
    }
    return commit({ type: "observe-geometry", geometry: geometryFor(surface) });
  }, [commit, conversationSurfaceRef]);

  const finishReturnFocus = useCallback(() => {
    const button = returnFocusButtonRef.current;
    returnFocusButtonRef.current = null;
    if (!button || document.activeElement !== button) {
      return;
    }
    conversationSurfaceRef.current?.focus({ preventScroll: true });
  }, [conversationSurfaceRef]);

  function runReconciliation() {
    reconcileFrameRef.current = null;
    const surface = conversationSurfaceRef.current;
    const current = stateRef.current;
    if (!surface || current.operation === "idle") {
      return;
    }

    if (current.operation === "preserving-anchor") {
      const anchor = readingAnchorRef.current;
      if (!anchor) {
        captureReadingAnchor();
        commit({ type: "complete-operation", operationId: current.operationId });
        return;
      }
      const node = resolveReadingAnchorNode(anchor);
      if (!node || !surface.contains(node)) {
        readingAnchorRef.current = null;
        captureReadingAnchor();
        commit({ type: "complete-operation", operationId: current.operationId });
        return;
      }
      const nodeRect = node.getBoundingClientRect();
      const offset = nodeRect.top - anchor.viewportTop;
      if (Math.abs(offset) > SCROLL_BOUNDARY_EPSILON_PX) {
        const scrollTop = normalizedScrollTop(surface);
        const targetTop = clampConversationScrollTop({
          ...geometryFor(surface),
          scrollTop: scrollTop + offset
        });
        const progress = reconcileProgressRef.current;
        const sameAttempt =
          progress.operationId === current.operationId &&
          Math.abs(progress.attemptedTargetTop - targetTop) <=
          SCROLL_BOUNDARY_EPSILON_PX;
        const previousAttemptMoved = sameAttempt &&
          Math.abs(progress.attemptedTargetTop - progress.attemptedFromTop) >
          SCROLL_BOUNDARY_EPSILON_PX;
        const previousScrollMoved = sameAttempt &&
          Math.abs(scrollTop - progress.attemptedFromTop) > SCROLL_BOUNDARY_EPSILON_PX;
        const errorImproved = Math.abs(offset) <
          progress.lastError - SCROLL_BOUNDARY_EPSILON_PX;
        const stalled = previousAttemptMoved &&
          (!previousScrollMoved || !errorImproved);
        const stalledFrames = stalled ? progress.stalledFrames + 1 : 0;
        if (
          Math.abs(targetTop - scrollTop) <= SCROLL_BOUNDARY_EPSILON_PX ||
          stalledFrames >= MAX_STALLED_RECONCILE_FRAMES ||
          performance.now() - operationStartedAtRef.current >=
          ANCHOR_RECONCILE_TIMEOUT_MS
        ) {
          anchor.viewportTop = nodeRect.top;
          reconcileProgressRef.current = initialReconcileProgress(current.operationId);
          commit({ type: "complete-operation", operationId: current.operationId });
          return;
        }
        reconcileProgressRef.current = {
          attemptedFromTop: scrollTop,
          attemptedTargetTop: targetTop,
          lastError: Math.abs(offset),
          operationId: current.operationId,
          stalledFrames
        };
        writeScrollTop(surface, targetTop, "reading-anchor");
        scheduleReconciliation();
        return;
      }
      reconcileProgressRef.current = initialReconcileProgress(current.operationId);
      commit({ type: "complete-operation", operationId: current.operationId });
      return;
    }

    if (current.operation === "locating-source") {
      const target = current.sourceMessageId
        ? messageRefs.current.get(current.sourceMessageId) ?? null
        : null;
      if (!target || !target.isConnected || !surface.contains(target)) {
        return;
      }
      const targetRect = target.getBoundingClientRect();
      if (!targetRect.height && !targetRect.width) {
        return;
      }
      const readableRect = readableConversationRect(
        surface,
        conversationStageRef.current
      );
      if (readableRect.height <= SCROLL_BOUNDARY_EPSILON_PX) {
        return;
      }
      const scrollTop = normalizedScrollTop(surface);
      const desiredTop = clampConversationScrollTop({
        ...geometryFor(surface),
        scrollTop:
          scrollTop +
          targetRect.top -
          readableRect.top -
          (readableRect.height - targetRect.height) / 2
      });
      const sourceSettle = sourceCenterRef.current;
      if (Math.abs(scrollTop - desiredTop) > SCROLL_BOUNDARY_EPSILON_PX) {
        const progress = reconcileProgressRef.current;
        const sameAttempt =
          progress.operationId === current.operationId &&
          Math.abs(progress.attemptedTargetTop - desiredTop) <=
          SCROLL_BOUNDARY_EPSILON_PX;
        const previousAttemptMoved = sameAttempt &&
          Math.abs(progress.attemptedTargetTop - progress.attemptedFromTop) >
          SCROLL_BOUNDARY_EPSILON_PX;
        const previousScrollMoved = sameAttempt &&
          Math.abs(scrollTop - progress.attemptedFromTop) >
          SCROLL_BOUNDARY_EPSILON_PX;
        const stalledFrames = previousAttemptMoved && !previousScrollMoved
          ? progress.stalledFrames + 1
          : 0;
        if (
          stalledFrames >= MAX_STALLED_RECONCILE_FRAMES ||
          (sameAttempt &&
            performance.now() - operationStartedAtRef.current >=
            ANCHOR_RECONCILE_TIMEOUT_MS)
        ) {
          reconcileProgressRef.current = {
            ...progress,
            stalledFrames
          };
          suspendedReconciliationRef.current = current.operationId;
          updateReconciliationSuspended(true);
          return;
        }
        reconcileProgressRef.current = {
          attemptedFromTop: scrollTop,
          attemptedTargetTop: desiredTop,
          lastError: Math.abs(scrollTop - desiredTop),
          operationId: current.operationId,
          stalledFrames
        };
        sourceCenterRef.current = {
          frames: 0,
          operationId: current.operationId,
          top: desiredTop
        };
        writeScrollTop(surface, desiredTop, "source-navigation");
        scheduleReconciliation();
        return;
      }
      suspendedReconciliationRef.current = null;
      reconcileProgressRef.current = initialReconcileProgress(current.operationId);
      const sameTarget =
        sourceSettle.operationId === current.operationId &&
        Math.abs(sourceSettle.top - desiredTop) <= SCROLL_BOUNDARY_EPSILON_PX;
      sourceCenterRef.current = {
        frames: sameTarget ? sourceSettle.frames + 1 : 1,
        operationId: current.operationId,
        top: desiredTop
      };
      if (sourceCenterRef.current.frames < STABLE_GEOMETRY_FRAMES) {
        scheduleReconciliation();
        return;
      }
      if (current.sourceRequestId) {
        commit({
          type: "consume-source",
          operationId: current.operationId,
          requestId: current.sourceRequestId
        });
      }
      captureReadingAnchor(target);
      return;
    }

    const metrics = measureConversationTail(geometryFor(surface));
    if (!metrics.atTail) {
      if (
        current.operation === "returning" &&
        performance.now() - operationStartedAtRef.current >= RETURN_RECONCILE_TIMEOUT_MS
      ) {
        suspendedReconciliationRef.current = current.operationId;
        updateReconciliationSuspended(true);
        return;
      }
      const progress = reconcileProgressRef.current;
      const sameAttempt =
        progress.operationId === current.operationId &&
        Math.abs(progress.attemptedTargetTop - metrics.maxScrollTop) <=
        SCROLL_BOUNDARY_EPSILON_PX;
      const previousAttemptMoved = sameAttempt &&
        Math.abs(progress.attemptedTargetTop - progress.attemptedFromTop) >
        SCROLL_BOUNDARY_EPSILON_PX;
      const previousScrollMoved = sameAttempt &&
        Math.abs(metrics.scrollTop - progress.attemptedFromTop) >
        SCROLL_BOUNDARY_EPSILON_PX;
      const stalledFrames = previousAttemptMoved && !previousScrollMoved
        ? progress.stalledFrames + 1
        : 0;
      if (
        stalledFrames >= MAX_STALLED_RECONCILE_FRAMES &&
        performance.now() - operationStartedAtRef.current >= RETURN_RECONCILE_TIMEOUT_MS
      ) {
        reconcileProgressRef.current = {
          ...progress,
          stalledFrames
        };
        suspendedReconciliationRef.current = current.operationId;
        updateReconciliationSuspended(true);
        return;
      }
      reconcileProgressRef.current = {
        attemptedFromTop: metrics.scrollTop,
        attemptedTargetTop: metrics.maxScrollTop,
        lastError: metrics.tailDistance,
        operationId: current.operationId,
        stalledFrames
      };
      writeScrollTop(surface, metrics.maxScrollTop, "tail-reconciliation");
      scheduleReconciliation();
      return;
    }
    let observed = current;
    if (!current.atTail) {
      observed = observeCurrentGeometry();
    }
    reconcileProgressRef.current = initialReconcileProgress(observed.operationId);
    suspendedReconciliationRef.current = null;
    updateReconciliationSuspended(false);
    const settle = settleRef.current;
    const sameGeometry =
      settle.operationId === observed.operationId &&
      settle.geometryRevision === observed.geometryRevision;
    settleRef.current = {
      frames: sameGeometry ? settle.frames + 1 : 1,
      geometryRevision: observed.geometryRevision,
      operationId: observed.operationId
    };
    if (settleRef.current.frames < STABLE_GEOMETRY_FRAMES) {
      scheduleReconciliation();
      return;
    }
    const completedOperation = observed.operation;
    if (completedOperation === "returning") {
      finishReturnFocus();
    }
    commit({
      type: "complete-operation",
      operationId: observed.operationId
    });
  }

  const flushGeometryInvalidation = useCallback(() => {
    geometryInvalidationFrameRef.current = null;
    const surface = conversationSurfaceRef.current;
    if (!surface) {
      return;
    }
    const current = stateRef.current;
    resumeSuspendedReconciliation(current.operationId);
    if (
      current.followIntent === "paused" &&
      current.operation === "idle" &&
      !activeGestureRef.current &&
      readingAnchorRef.current
    ) {
      mutationSequenceRef.current += 1;
      commit({
        type: "prepare-mutation",
        key: `geometry:${mutationSequenceRef.current}`,
        policy: "inherit-current"
      });
    }
    const observed = commit({
      type: "observe-geometry",
      geometry: geometryFor(surface)
    });
    if (observed.operation !== "idle" || observed.followIntent === "following") {
      scheduleReconciliation();
    }
  }, [commit, conversationSurfaceRef, resumeSuspendedReconciliation, scheduleReconciliation]);

  const invalidateGeometry = useCallback((_reason: string) => {
    if (geometryInvalidationFrameRef.current !== null) {
      return;
    }
    geometryInvalidationFrameRef.current = window.requestAnimationFrame(
      flushGeometryInvalidation
    );
  }, [flushGeometryInvalidation]);

  const finishUserGesture = useCallback(() => {
    activeGestureRef.current = null;
    if (
      stateRef.current.followIntent === "paused" &&
      stateRef.current.operation === "idle"
    ) {
      captureReadingAnchor();
    }
  }, [captureReadingAnchor]);

  const scheduleGestureFinish = useCallback(() => {
    if (scrollIdleTimerRef.current !== null) {
      window.clearTimeout(scrollIdleTimerRef.current);
    }
    scrollIdleTimerRef.current = window.setTimeout(() => {
      scrollIdleTimerRef.current = null;
      finishUserGesture();
    }, GESTURE_IDLE_MS);
  }, [finishUserGesture]);

  const claimByUser = useCallback((
    inputKind: ConversationScrollInputKind,
    direction: ConversationScrollDirection,
    projectedGeometry?: ConversationScrollGeometry
  ) => {
    const surface = conversationSurfaceRef.current;
    if (!surface) {
      return;
    }
    clearProgrammaticScroll();
    readingAnchorRef.current = null;
    activeGestureRef.current = { direction, inputKind, stale: false };
    const next = commit({
      type: "claim-by-user",
      direction,
      geometry: projectedGeometry ?? geometryFor(surface),
      inputKind
    });
    if (next.operation === "reconciling") {
      scheduleReconciliation();
    }
  }, [clearProgrammaticScroll, commit, conversationSurfaceRef, scheduleReconciliation]);

  const handleObservedScroll = useCallback(() => {
    const surface = conversationSurfaceRef.current;
    if (!surface) {
      return;
    }
    const clampedTop = clampConversationScrollTop(geometryFor(surface));
    const programmatic = consumeProgrammaticScroll(surface, clampedTop);
    const gesture = activeGestureRef.current;
    if (!programmatic && gesture?.inputKind === "scrollbar") {
      const delta = clampedTop - lastObservedScrollTopRef.current;
      if (Math.abs(delta) > SCROLL_BOUNDARY_EPSILON_PX) {
        claimByUser("scrollbar", delta < 0 ? "up" : "down");
      }
    }
    lastObservedScrollTopRef.current = clampedTop;
    let observed = commit({
      type: "observe-geometry",
      geometry: geometryFor(surface)
    });
    if (
      !programmatic &&
      activeGestureRef.current?.direction === "down" &&
      observed.nearTail &&
      observed.followIntent !== "following"
    ) {
      observed = commit({
        type: "claim-by-user",
        direction: "down",
        geometry: geometryFor(surface),
        inputKind: activeGestureRef.current.inputKind
      });
    }
    if (observed.followIntent === "following" && !observed.atTail) {
      scheduleReconciliation();
    }
    onClearAnnotationSelectionRef.current();
    if (activeGestureRef.current) {
      scheduleGestureFinish();
    }
  }, [claimByUser, commit, consumeProgrammaticScroll, conversationSurfaceRef, scheduleGestureFinish, scheduleReconciliation]);

  const forceLatest = useCallback((reason: string) => {
    supersedeUserGesture();
    readingAnchorRef.current = null;
    returnFocusButtonRef.current = null;
    const next = commit({ type: "force-latest", reason });
    const surface = conversationSurfaceRef.current;
    if (surface) {
      writeScrollTop(surface, measureConversationTail(geometryFor(surface)).maxScrollTop, reason);
    }
    if (next.operation !== "idle") {
      scheduleReconciliation();
    }
  }, [commit, conversationSurfaceRef, scheduleReconciliation, supersedeUserGesture, writeScrollTop]);

  const prepareMutation = useCallback((key: string) => {
    if (stateRef.current.followIntent === "paused") {
      if (activeGestureRef.current) {
        readingAnchorRef.current = null;
      } else if (stateRef.current.operation === "idle") {
        captureReadingAnchor();
      }
    }
    const next = commit({ type: "prepare-mutation", key, policy: "inherit-current" });
    if (next.operation !== "idle") {
      scheduleReconciliation();
    }
  }, [captureReadingAnchor, commit, scheduleReconciliation]);

  const returnToLatest = useCallback(() => {
    supersedeUserGesture();
    readingAnchorRef.current = null;
    const stage = conversationStageRef.current;
    const focusedTailButton = stage?.querySelector<HTMLButtonElement>(
      ".conversation-tail-button"
    ) ?? null;
    returnFocusButtonRef.current = focusedTailButton === document.activeElement
      ? focusedTailButton
      : null;
    commit({ type: "return-to-latest" });
    const surface = conversationSurfaceRef.current;
    if (surface) {
      writeScrollTop(
        surface,
        measureConversationTail(geometryFor(surface)).maxScrollTop,
        "return-to-latest"
      );
    }
    scheduleReconciliation();
  }, [commit, conversationStageRef, conversationSurfaceRef, scheduleReconciliation, supersedeUserGesture, writeScrollTop]);

  const preserveConversationAnchor = useCallback((anchor: HTMLElement) => {
    const surface = conversationSurfaceRef.current;
    if (!surface || !surface.contains(anchor)) {
      return;
    }
    commit({
      type: "claim-by-user",
      direction: "up",
      geometry: geometryFor(surface),
      inputKind: "keyboard"
    });
    captureReadingAnchor(anchor);
    mutationSequenceRef.current += 1;
    commit({
      type: "prepare-mutation",
      key: `anchor:${mutationSequenceRef.current}`,
      policy: "inherit-current"
    });
    scheduleReconciliation();
  }, [captureReadingAnchor, commit, conversationSurfaceRef, scheduleReconciliation]);

  const registerMessageElement = useCallback((
    messageId: string,
    node: HTMLElement | null
  ) => {
    if (node) {
      messageRefs.current.set(messageId, node);
      messageIdByElementRef.current.set(node, messageId);
    } else {
      messageRefs.current.delete(messageId);
    }
    if (stateRef.current.sourceMessageId === messageId) {
      resumeSuspendedReconciliation(stateRef.current.operationId);
      scheduleReconciliation();
    }
  }, [messageRefs, resumeSuspendedReconciliation, scheduleReconciliation]);

  useLayoutEffect(() => {
    const surface = conversationSurfaceRef.current;
    if (
      surface === observedSurfaceRef.current &&
      conversationSessionId === observedSessionRef.current
    ) {
      return;
    }
    observedSurfaceRef.current = surface;
    observedSessionRef.current = conversationSessionId;
    setSurfaceBindingRevision((current) => current + 1);
    const staleWheelGesture = wheelGestureRef.current;
    if (staleWheelGesture) {
      staleWheelGesture.stale = true;
    }
    readingAnchorRef.current = null;
    activeGestureRef.current = null;
    touchGestureRef.current = null;
    returnFocusButtonRef.current = null;
    if (wheelIdleTimerRef.current !== null) {
      window.clearTimeout(wheelIdleTimerRef.current);
      wheelIdleTimerRef.current = null;
    }
    wheelGestureRef.current = staleWheelGesture;
    if (staleWheelGesture) {
      wheelIdleTimerRef.current = window.setTimeout(() => {
        if (wheelGestureRef.current === staleWheelGesture) {
          wheelGestureRef.current = null;
        }
        wheelIdleTimerRef.current = null;
      }, GESTURE_IDLE_MS);
    }
    if (scrollIdleTimerRef.current !== null) {
      window.clearTimeout(scrollIdleTimerRef.current);
      scrollIdleTimerRef.current = null;
    }
    clearProgrammaticScroll();
    suspendedReconciliationRef.current = null;
    if (reconcileFrameRef.current !== null) {
      window.cancelAnimationFrame(reconcileFrameRef.current);
      reconcileFrameRef.current = null;
    }
    if (geometryInvalidationFrameRef.current !== null) {
      window.cancelAnimationFrame(geometryInvalidationFrameRef.current);
      geometryInvalidationFrameRef.current = null;
    }
    commit({ type: "reset-session", sessionId: conversationSessionId });
    if (surface) {
      lastObservedScrollTopRef.current = clampConversationScrollTop(geometryFor(surface));
      scheduleReconciliation();
    }
  });

  useLayoutEffect(() => {
    if (!highlightedMessageId || !conversationSessionId) {
      commit({ type: "cancel-source" });
      return;
    }
    supersedeUserGesture();
    returnFocusButtonRef.current = null;
    const requestId = `${conversationSessionId}:${highlightedMessageRequestId}:${highlightedMessageId}`;
    const next = commit({
      type: "locate-source",
      sessionId: conversationSessionId,
      messageId: highlightedMessageId,
      requestId
    });
    if (next.operation === "locating-source") {
      scheduleReconciliation();
    }
  }, [
    commit,
    conversationSessionId,
    highlightedMessageId,
    highlightedMessageRequestId,
    scheduleReconciliation,
    supersedeUserGesture
  ]);

  useEffect(() => {
    const currentStage = conversationStageRef.current;
    const currentSurface = conversationSurfaceRef.current;
    if (!currentStage || !currentSurface) {
      return;
    }
    const stage: HTMLDivElement = currentStage;
    const surface: HTMLDivElement = currentSurface;

    function resetWheelIdleTimer() {
      if (wheelIdleTimerRef.current !== null) {
        window.clearTimeout(wheelIdleTimerRef.current);
      }
      wheelIdleTimerRef.current = window.setTimeout(() => {
        wheelIdleTimerRef.current = null;
        wheelGestureRef.current = null;
        finishUserGesture();
      }, GESTURE_IDLE_MS);
    }

    function handleWheel(event: WheelEvent) {
      if (
        event.ctrlKey ||
        event.shiftKey ||
        !event.deltaY ||
        Math.abs(event.deltaY) <= Math.abs(event.deltaX)
      ) {
        return;
      }
      if (wheelGestureRef.current?.stale) {
        event.preventDefault();
        resetWheelIdleTimer();
        return;
      }
      const deltaY = normalizedWheelDelta(event, surface);
      const direction: ConversationScrollDirection = deltaY < 0 ? "up" : "down";
      const targetInsideSurface = event.target instanceof Node && surface.contains(event.target);
      const boundary = targetInsideSurface ? surface : stage;
      if (findConsumableVerticalScroller(event.target, boundary, direction)) {
        return;
      }
      const nestedAtBoundary = hasNestedVerticalScroller(event.target, boundary);
      const gesture = wheelGestureRef.current ?? {
        direction,
        inputKind: "wheel" as const,
        stale: false
      };
      gesture.direction = direction;
      wheelGestureRef.current = gesture;
      activeGestureRef.current = gesture;
      const geometry = geometryFor(surface);
      claimByUser("wheel", direction, {
        ...geometry,
        scrollTop: normalizedScrollTop(surface) + deltaY
      });
      resetWheelIdleTimer();
      if (!targetInsideSurface || nestedAtBoundary) {
        event.preventDefault();
        writeScrollBy(surface, deltaY, "user-wheel-handoff");
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.defaultPrevented || isEditableOrInteractiveTarget(event.target)) {
        return;
      }
      if (event.key === "End") {
        event.preventDefault();
        returnToLatest();
        return;
      }
      const direction = ["ArrowUp", "PageUp", "Home"].includes(event.key) ||
        (event.key === " " && event.shiftKey)
        ? "up"
        : ["ArrowDown", "PageDown"].includes(event.key) ||
          (event.key === " " && !event.shiftKey)
          ? "down"
          : null;
      if (direction) {
        claimByUser("keyboard", direction);
        scheduleGestureFinish();
      }
    }

    function handlePointerDown(event: PointerEvent) {
      if (event.pointerType !== "mouse" || event.button !== 0) {
        return;
      }
      const rect = surface.getBoundingClientRect();
      const surfaceStyle = window.getComputedStyle(surface);
      const borderWidth = [surfaceStyle.borderLeftWidth, surfaceStyle.borderRightWidth]
        .map((value) => Number.parseFloat(value))
        .reduce((sum, value) => sum + (Number.isFinite(value) ? value : 0), 0);
      const scrollbarWidth = Math.max(
        0,
        surface.offsetWidth - surface.clientWidth - borderWidth
      );
      const usesOverlayFallback =
        scrollbarWidth <= SCROLL_BOUNDARY_EPSILON_PX;
      const hitWidth = !usesOverlayFallback
        ? scrollbarWidth + 2
        : OVERLAY_SCROLLBAR_HIT_WIDTH_PX;
      if (
        event.clientX < rect.right - hitWidth ||
        (!usesOverlayFallback && event.target !== surface) ||
        (usesOverlayFallback && isEditableOrInteractiveTarget(event.target))
      ) {
        return;
      }
      activeGestureRef.current = {
        direction: null,
        inputKind: "scrollbar",
        stale: false
      };
    }

    function handlePointerEnd() {
      if (activeGestureRef.current?.inputKind === "scrollbar") {
        finishUserGesture();
      }
    }

    function handleTouchStart(event: TouchEvent) {
      if (event.touches.length !== 1 || isEditableOrInteractiveTarget(event.target)) {
        touchGestureRef.current = null;
        return;
      }
      touchGestureRef.current = {
        lastY: event.touches[0].clientY,
        stale: false,
        target: event.target
      };
    }

    function handleTouchMove(event: TouchEvent) {
      const touchGesture = touchGestureRef.current;
      if (!touchGesture || event.touches.length !== 1) {
        return;
      }
      if (touchGesture.stale) {
        event.preventDefault();
        return;
      }
      const nextY = event.touches[0].clientY;
      const deltaY = touchGesture.lastY - nextY;
      touchGesture.lastY = nextY;
      if (Math.abs(deltaY) <= SCROLL_BOUNDARY_EPSILON_PX) {
        return;
      }
      const direction: ConversationScrollDirection = deltaY < 0 ? "up" : "down";
      const targetInsideSurface = touchGesture.target instanceof Node &&
        surface.contains(touchGesture.target);
      const boundary = targetInsideSurface ? surface : stage;
      if (findConsumableVerticalScroller(touchGesture.target, boundary, direction)) {
        return;
      }
      const nestedAtBoundary = hasNestedVerticalScroller(touchGesture.target, boundary);
      const geometry = geometryFor(surface);
      claimByUser("touch", direction, {
        ...geometry,
        scrollTop: normalizedScrollTop(surface) + deltaY
      });
      if (!targetInsideSurface || nestedAtBoundary) {
        event.preventDefault();
        writeScrollBy(surface, deltaY, "user-touch-handoff");
      }
    }

    function handleTouchEnd() {
      touchGestureRef.current = null;
      finishUserGesture();
    }

    function handleFocusIn(event: FocusEvent) {
      const pendingButton = returnFocusButtonRef.current;
      if (pendingButton && event.target !== pendingButton) {
        returnFocusButtonRef.current = null;
      }
    }

    function handleScrollEnd() {
      if (activeGestureRef.current) {
        finishUserGesture();
      }
    }

    return installConversationInputListeners(stage, surface, {
      handleWheel,
      handleTouchStart,
      handleTouchMove,
      handleTouchEnd,
      handleObservedScroll,
      handleKeyDown,
      handlePointerDown,
      handlePointerEnd,
      handleFocusIn,
      handleScrollEnd
    });
  }, [
    bindingKey,
    claimByUser,
    conversationStageRef,
    conversationSurfaceRef,
    finishUserGesture,
    handleObservedScroll,
    returnToLatest,
    scheduleGestureFinish,
    surfaceBindingRevision,
    writeScrollBy
  ]);

  useLayoutEffect(() => {
    const messageList = messageListRef.current;
    const surface = conversationSurfaceRef.current;
    const flow = messageList?.querySelector<HTMLElement>(".conversation-message-flow") ?? null;
    const sentinel = messageList?.querySelector<HTMLElement>(".conversation-tail-sentinel") ?? null;
    if (!messageList || !surface || !flow) {
      contentObserverCleanupRef.current?.();
      contentObserverCleanupRef.current = null;
      contentObserverNodesRef.current = null;
      return;
    }
    const observed = contentObserverNodesRef.current;
    if (
      observed?.flow === flow &&
      observed.messageList === messageList &&
      observed.sentinel === sentinel &&
      observed.surface === surface
    ) {
      return;
    }
    contentObserverCleanupRef.current?.();
    let disposed = false;
    const nodes = { flow, messageList, sentinel, surface };
    contentObserverNodesRef.current = nodes;
    const notify = () => {
      if (!disposed && contentObserverNodesRef.current === nodes) {
        invalidateGeometry("content-observer");
      }
    };
    const resizeObserver = typeof ResizeObserver === "undefined"
      ? null
      : new ResizeObserver(notify);
    resizeObserver?.observe(flow);
    resizeObserver?.observe(surface);
    resizeObserver?.observe(messageList);
    const mutationObserver = typeof MutationObserver === "undefined"
      ? null
      : new MutationObserver(notify);
    mutationObserver?.observe(flow, {
      attributes: true,
      attributeFilter: ["open", "src", "style"],
      characterData: true,
      childList: true,
      subtree: true
    });
    const intersectionObserver = sentinel && typeof IntersectionObserver !== "undefined"
      ? new IntersectionObserver(notify, { root: surface, threshold: 1 })
      : null;
    if (sentinel) {
      intersectionObserver?.observe(sentinel);
    }
    const handleMediaSettled = () => notify();
    messageList.addEventListener("load", handleMediaSettled, true);
    messageList.addEventListener("error", handleMediaSettled, true);
    const fonts = document.fonts;
    const handleFontsSettled = () => notify();
    fonts?.addEventListener?.("loadingdone", handleFontsSettled);
    void fonts?.ready?.then(handleFontsSettled).catch(() => undefined);
    notify();
    contentObserverCleanupRef.current = () => {
      disposed = true;
      resizeObserver?.disconnect();
      mutationObserver?.disconnect();
      intersectionObserver?.disconnect();
      messageList.removeEventListener("load", handleMediaSettled, true);
      messageList.removeEventListener("error", handleMediaSettled, true);
      fonts?.removeEventListener?.("loadingdone", handleFontsSettled);
    };
  });

  useEffect(() => {
    const handleViewportChange = () => invalidateGeometry("viewport");
    window.addEventListener("resize", handleViewportChange);
    window.visualViewport?.addEventListener("resize", handleViewportChange);
    window.visualViewport?.addEventListener("scroll", handleViewportChange);
    return () => {
      window.removeEventListener("resize", handleViewportChange);
      window.visualViewport?.removeEventListener("resize", handleViewportChange);
      window.visualViewport?.removeEventListener("scroll", handleViewportChange);
    };
  }, [invalidateGeometry]);

  useEffect(() => () => {
    if (reconcileFrameRef.current !== null) {
      window.cancelAnimationFrame(reconcileFrameRef.current);
      reconcileFrameRef.current = null;
    }
    if (geometryInvalidationFrameRef.current !== null) {
      window.cancelAnimationFrame(geometryInvalidationFrameRef.current);
      geometryInvalidationFrameRef.current = null;
    }
    clearProgrammaticScroll();
    if (wheelIdleTimerRef.current !== null) {
      window.clearTimeout(wheelIdleTimerRef.current);
    }
    if (scrollIdleTimerRef.current !== null) {
      window.clearTimeout(scrollIdleTimerRef.current);
    }
    contentObserverCleanupRef.current?.();
    contentObserverCleanupRef.current = null;
    contentObserverNodesRef.current = null;
    suspendedReconciliationRef.current = null;
    returnFocusButtonRef.current = null;
  }, [clearProgrammaticScroll]);

  return {
    atTail: state.atTail,
    conversationTailButtonVisible: shouldShowTailButton(
      state,
      reconciliationSuspended
    ),
    followIntent: state.followIntent,
    forceLatest,
    invalidateGeometry,
    operation: state.operation,
    prepareMutation,
    preserveConversationAnchor,
    registerMessageElement,
    returnToLatest
  };
}
