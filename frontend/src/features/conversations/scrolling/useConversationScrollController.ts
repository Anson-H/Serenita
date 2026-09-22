import { ConversationScrollReconciler } from "./conversationScrollReconciler";
import { ConversationReadingAnchor } from "./conversationReadingAnchor";
import { ConversationContentObserver } from "./conversationContentObserver";
import { ConversationInputSession } from "./conversationInputSession";
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type MutableRefObject,
  type RefObject
} from "react";
import { SCROLL_BOUNDARY_EPSILON_PX, geometryFor, normalizedScrollTop, shouldShowTailButton } from "./conversationScrollGeometry";
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

const PROGRAMMATIC_SCROLL_EXPIRY_MS = 250;

type ProgrammaticScroll = {
  expectedTop: number;
  operationId: number;
  origin: string;
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
  const programmaticClearTimerRef = useRef<number | null>(null);
  const reconciliationSuspendedRef = useRef(false);
  const readingAnchor = useRef(new ConversationReadingAnchor()).current;
  const programmaticOriginRef = useRef<ProgrammaticScroll | null>(null);
  const contentObserver = useRef(new ConversationContentObserver()).current;
  const inputSession = useRef<ConversationInputSession | null>(null);
  if (!inputSession.current) inputSession.current = new ConversationInputSession({
    claimByUser: (...args) => claimByUser(...args),
    writeScrollBy: (...args) => writeScrollBy(...args),
    returnToLatest: () => returnToLatest(),
    handleObservedScroll: () => handleObservedScroll(),
    onFocus: event => { if (returnFocusButtonRef.current && event.target !== returnFocusButtonRef.current) returnFocusButtonRef.current = null; },
    onFinish: () => { if (stateRef.current.followIntent === "paused" && stateRef.current.operation === "idle") captureReadingAnchor(); },
  });
  const gestures = inputSession.current;
  const lastObservedScrollTopRef = useRef(0);
  const returnFocusButtonRef = useRef<HTMLButtonElement | null>(null);
  const mutationSequenceRef = useRef(0);
  const geometryInvalidationFrameRef = useRef<number | null>(null);

  const reconcilerRef = useRef<ConversationScrollReconciler | null>(null);
  if (!reconcilerRef.current) reconcilerRef.current = new ConversationScrollReconciler({
    surface: () => conversationSurfaceRef.current,
    stage: () => conversationStageRef.current,
    state: () => stateRef.current,
    commit: event => commit(event),
    anchor: readingAnchor,
    captureAnchor: preferred => captureReadingAnchor(preferred),
    messages: () => messageRefs.current,
    writeScrollTop: (...args) => writeScrollTop(...args),
    setSuspended: value => updateReconciliationSuspended(value),
    observeGeometry: () => observeCurrentGeometry(),
    finishReturnFocus: () => finishReturnFocus(),
  });
  const reconciler = reconcilerRef.current;

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
    if (startsNewOperation) reconciler.start(next);
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

  const supersedeUserGesture = useCallback(() => gestures.supersede(), [gestures]);

  const resumeSuspendedReconciliation = reconciler.resume;

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

  const captureReadingAnchor = useCallback((preferred?: HTMLElement | null) =>
    readingAnchor.capture(conversationSurfaceRef.current, conversationStageRef.current, messageRefs.current, preferred),
    [readingAnchor, conversationSurfaceRef, conversationStageRef, messageRefs]);

  const scheduleReconciliation = reconciler.schedule;

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
      !gestures.active &&
      readingAnchor.current
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

  const scheduleGestureFinish = useCallback(() => gestures.scheduleFinish(), [gestures]);

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
    readingAnchor.clear();
    gestures.claim(inputKind, direction);
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
    const gesture = gestures.active;
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
      gestures.active?.direction === "down" &&
      observed.nearTail &&
      observed.followIntent !== "following"
    ) {
      observed = commit({
        type: "claim-by-user",
        direction: "down",
        geometry: geometryFor(surface),
        inputKind: gestures.active.inputKind
      });
    }
    if (observed.followIntent === "following" && !observed.atTail) {
      scheduleReconciliation();
    }
    onClearAnnotationSelectionRef.current();
    if (gestures.active) {
      scheduleGestureFinish();
    }
  }, [claimByUser, commit, consumeProgrammaticScroll, conversationSurfaceRef, scheduleGestureFinish, scheduleReconciliation]);

  const forceLatest = useCallback((reason: string) => {
    supersedeUserGesture();
    readingAnchor.clear();
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
      if (gestures.active) {
        readingAnchor.clear();
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
    readingAnchor.clear();
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
      readingAnchor.register(messageId, node);
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
    gestures.reset();
    readingAnchor.clear();
    returnFocusButtonRef.current = null;
    clearProgrammaticScroll();
    reconciler.cancel();
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
    const stage = conversationStageRef.current;
    const surface = conversationSurfaceRef.current;
    if (!stage || !surface) return;
    return gestures.install(stage, surface);
  }, [bindingKey, conversationStageRef, conversationSurfaceRef, surfaceBindingRevision, gestures]);

  useLayoutEffect(() => {
    contentObserver.observe(messageListRef.current, conversationSurfaceRef.current, () => invalidateGeometry("content-observer"));
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
    reconciler.cancel();
    if (geometryInvalidationFrameRef.current !== null) {
      window.cancelAnimationFrame(geometryInvalidationFrameRef.current);
      geometryInvalidationFrameRef.current = null;
    }
    clearProgrammaticScroll();
    gestures.dispose();
    contentObserver.disconnect();
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
