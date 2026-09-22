import { ConversationReadingAnchor } from "./conversationReadingAnchor";
import { SCROLL_BOUNDARY_EPSILON_PX, geometryFor, normalizedScrollTop, readableConversationRect } from "./conversationScrollGeometry";
import { clampConversationScrollTop, measureConversationTail, type ConversationScrollEvent, type ConversationScrollState } from "./conversationScrollStateMachine";
const RETURN_RECONCILE_TIMEOUT_MS = 2000;
const ANCHOR_RECONCILE_TIMEOUT_MS = 2000;
const MAX_STALLED_RECONCILE_FRAMES = 2;
const STABLE_GEOMETRY_FRAMES = 2;
type ReconcileProgress = { attemptedFromTop: number; attemptedTargetTop: number; lastError: number; operationId: number; stalledFrames: number };
function initialReconcileProgress(operationId = -1): ReconcileProgress {
  return { attemptedFromTop: Number.NaN, attemptedTargetTop: Number.NaN, lastError: Number.POSITIVE_INFINITY, operationId, stalledFrames: 0 };
}
type Port = {
  surface: () => HTMLDivElement | null;
  stage: () => HTMLDivElement | null;
  state: () => ConversationScrollState;
  commit: (event: ConversationScrollEvent) => ConversationScrollState;
  anchor: ConversationReadingAnchor;
  captureAnchor: (preferred?: HTMLElement | null) => unknown;
  messages: () => Map<string, HTMLElement>;
  writeScrollTop: (surface: HTMLDivElement, top: number, origin: string) => number;
  setSuspended: (value: boolean) => void;
  observeGeometry: () => ConversationScrollState;
  finishReturnFocus: () => void;
};
/** Owns reconciliation progress and its animation frame; it submits events to the controller's reducer. */
export class ConversationScrollReconciler {
  private frame: number | null = null;
  private startedAt = 0;
  private settle = { frames: 0, geometryRevision: -1, operationId: -1 };
  private sourceCenter = { frames: 0, operationId: -1, top: Number.NaN };
  private progress = initialReconcileProgress();
  private suspendedOperation: number | null = null;
  constructor(private readonly port: Port) { }
  start(state: ConversationScrollState) {
    this.port.setSuspended(false);
    this.startedAt = performance.now(); this.suspendedOperation = null;
    this.settle = { frames: 0, geometryRevision: state.geometryRevision, operationId: state.operationId };
    this.sourceCenter = { frames: 0, operationId: state.operationId, top: Number.NaN };
    this.progress = initialReconcileProgress(state.operationId);
  }
  resume = (operationId: number) => {
    if (this.suspendedOperation !== operationId) return;
    this.suspendedOperation = null; this.port.setSuspended(false);
    this.startedAt = performance.now(); this.progress = initialReconcileProgress(operationId);
  };
  schedule = () => { if (this.frame === null) this.frame = window.requestAnimationFrame(this.run); };
  cancel() { if (this.frame !== null) window.cancelAnimationFrame(this.frame); this.frame = null; this.suspendedOperation = null; }
  private run = () => {
    this.frame = null;
    const surface = this.port.surface();
    const current = this.port.state();
    if (!surface || current.operation === "idle") {
      return;
    }

    if (current.operation === "preserving-anchor") return this.preserveAnchor(surface, current);
    if (current.operation === "locating-source") return this.locateSource(surface, current);
    this.reconcileTail(surface, current);
  };

  private preserveAnchor(surface: HTMLDivElement, current: ConversationScrollState) {
    const anchor = this.port.anchor.current;
    if (!anchor) {
      this.port.captureAnchor();
      this.port.commit({ type: "complete-operation", operationId: current.operationId });
      return;
    }
    const node = this.port.anchor.resolve(anchor, this.port.messages());
    if (!node || !surface.contains(node)) {
      this.port.anchor.clear();
      this.port.captureAnchor();
      this.port.commit({ type: "complete-operation", operationId: current.operationId });
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
      const progress = this.progress;
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
        performance.now() - this.startedAt >=
        ANCHOR_RECONCILE_TIMEOUT_MS
      ) {
        this.port.anchor.acceptPosition(nodeRect.top);
        this.progress = initialReconcileProgress(current.operationId);
        this.port.commit({ type: "complete-operation", operationId: current.operationId });
        return;
      }
      this.progress = {
        attemptedFromTop: scrollTop,
        attemptedTargetTop: targetTop,
        lastError: Math.abs(offset),
        operationId: current.operationId,
        stalledFrames
      };
      this.port.writeScrollTop(surface, targetTop, "reading-anchor");
      this.schedule();
      return;
    }
    this.progress = initialReconcileProgress(current.operationId);
    this.port.commit({ type: "complete-operation", operationId: current.operationId });
    return;
  }

  private locateSource(surface: HTMLDivElement, current: ConversationScrollState) {
    const target = current.sourceMessageId
      ? this.port.messages().get(current.sourceMessageId) ?? null
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
      this.port.stage()
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
    const sourceSettle = this.sourceCenter;
    if (Math.abs(scrollTop - desiredTop) > SCROLL_BOUNDARY_EPSILON_PX) {
      const progress = this.progress;
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
          performance.now() - this.startedAt >=
          ANCHOR_RECONCILE_TIMEOUT_MS)
      ) {
        this.progress = {
          ...progress,
          stalledFrames
        };
        this.suspendedOperation = current.operationId;
        this.port.setSuspended(true);
        return;
      }
      this.progress = {
        attemptedFromTop: scrollTop,
        attemptedTargetTop: desiredTop,
        lastError: Math.abs(scrollTop - desiredTop),
        operationId: current.operationId,
        stalledFrames
      };
      this.sourceCenter = {
        frames: 0,
        operationId: current.operationId,
        top: desiredTop
      };
      this.port.writeScrollTop(surface, desiredTop, "source-navigation");
      this.schedule();
      return;
    }
    this.suspendedOperation = null;
    this.progress = initialReconcileProgress(current.operationId);
    const sameTarget =
      sourceSettle.operationId === current.operationId &&
      Math.abs(sourceSettle.top - desiredTop) <= SCROLL_BOUNDARY_EPSILON_PX;
    this.sourceCenter = {
      frames: sameTarget ? sourceSettle.frames + 1 : 1,
      operationId: current.operationId,
      top: desiredTop
    };
    if (this.sourceCenter.frames < STABLE_GEOMETRY_FRAMES) {
      this.schedule();
      return;
    }
    if (current.sourceRequestId) {
      this.port.commit({
        type: "consume-source",
        operationId: current.operationId,
        requestId: current.sourceRequestId
      });
    }
    this.port.captureAnchor(target);
    return;
  }

  private reconcileTail(surface: HTMLDivElement, current: ConversationScrollState) {
    const metrics = measureConversationTail(geometryFor(surface));
    if (!metrics.atTail) {
      if (
        current.operation === "returning" &&
        performance.now() - this.startedAt >= RETURN_RECONCILE_TIMEOUT_MS
      ) {
        this.suspendedOperation = current.operationId;
        this.port.setSuspended(true);
        return;
      }
      const progress = this.progress;
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
        performance.now() - this.startedAt >= RETURN_RECONCILE_TIMEOUT_MS
      ) {
        this.progress = {
          ...progress,
          stalledFrames
        };
        this.suspendedOperation = current.operationId;
        this.port.setSuspended(true);
        return;
      }
      this.progress = {
        attemptedFromTop: metrics.scrollTop,
        attemptedTargetTop: metrics.maxScrollTop,
        lastError: metrics.tailDistance,
        operationId: current.operationId,
        stalledFrames
      };
      this.port.writeScrollTop(surface, metrics.maxScrollTop, "tail-reconciliation");
      this.schedule();
      return;
    }
    let observed = current;
    if (!current.atTail) {
      observed = this.port.observeGeometry();
    }
    this.progress = initialReconcileProgress(observed.operationId);
    this.suspendedOperation = null;
    this.port.setSuspended(false);
    const settle = this.settle;
    const sameGeometry =
      settle.operationId === observed.operationId &&
      settle.geometryRevision === observed.geometryRevision;
    this.settle = {
      frames: sameGeometry ? settle.frames + 1 : 1,
      geometryRevision: observed.geometryRevision,
      operationId: observed.operationId
    };
    if (this.settle.frames < STABLE_GEOMETRY_FRAMES) {
      this.schedule();
      return;
    }
    const completedOperation = observed.operation;
    if (completedOperation === "returning") {
      this.port.finishReturnFocus();
    }
    this.port.commit({
      type: "complete-operation",
      operationId: observed.operationId
    });
  }
}
