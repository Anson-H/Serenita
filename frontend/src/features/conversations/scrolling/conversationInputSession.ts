import { installConversationInputListeners } from "./conversationInputListeners";
import { SCROLL_BOUNDARY_EPSILON_PX, findConsumableVerticalScroller, geometryFor, hasNestedVerticalScroller, isEditableOrInteractiveTarget, normalizedScrollTop, normalizedWheelDelta } from "./conversationScrollGeometry";
import type { ConversationScrollDirection, ConversationScrollGeometry, ConversationScrollInputKind } from "./conversationScrollStateMachine";
const GESTURE_IDLE_MS = 120;
const OVERLAY_SCROLLBAR_HIT_WIDTH_PX = 16;
type Gesture = { direction: ConversationScrollDirection | null; inputKind: ConversationScrollInputKind; stale: boolean };
type TouchGesture = { lastY: number; stale: boolean; target: EventTarget | null };
type Commands = {
  claimByUser: (kind: ConversationScrollInputKind, direction: ConversationScrollDirection, geometry?: ConversationScrollGeometry) => void;
  writeScrollBy: (surface: HTMLDivElement, delta: number, origin: string) => void;
  returnToLatest: () => void;
  handleObservedScroll: () => void;
  onFocus: (event: FocusEvent) => void;
  onFinish: () => void;
};
/** Owns native gestures and their timers; only the controller changes operation IDs. */
export class ConversationInputSession {
  private activeGesture: Gesture | null = null;
  private wheelGesture: Gesture | null = null;
  private touchGesture: TouchGesture | null = null;
  private wheelIdleTimer: number | null = null;
  private scrollIdleTimer: number | null = null;
  constructor(private readonly commands: Commands) { }
  get active(): Readonly<Gesture> | null { return this.activeGesture; }
  claim(inputKind: ConversationScrollInputKind, direction: ConversationScrollDirection) { this.activeGesture = { inputKind, direction, stale: false }; }
  supersede() { if (this.wheelGesture) this.wheelGesture.stale = true; if (this.touchGesture) this.touchGesture.stale = true; this.activeGesture = null; }
  finish() { this.activeGesture = null; this.commands.onFinish(); }
  scheduleFinish() {
    if (this.scrollIdleTimer !== null) window.clearTimeout(this.scrollIdleTimer);
    this.scrollIdleTimer = window.setTimeout(() => { this.scrollIdleTimer = null; this.finish(); }, GESTURE_IDLE_MS);
  }
  reset() {
    const stale = this.wheelGesture;
    this.supersede(); this.touchGesture = null;
    this.disposeTimers();
    if (stale) this.wheelIdleTimer = window.setTimeout(() => {
      if (this.wheelGesture === stale) this.wheelGesture = null;
      this.wheelIdleTimer = null;
    }, GESTURE_IDLE_MS);
  }
  private disposeTimers() {
    if (this.wheelIdleTimer !== null) window.clearTimeout(this.wheelIdleTimer);
    if (this.scrollIdleTimer !== null) window.clearTimeout(this.scrollIdleTimer);
    this.wheelIdleTimer = this.scrollIdleTimer = null;
  }
  dispose() { this.disposeTimers(); this.activeGesture = this.wheelGesture = this.touchGesture = null; }
  install(stage: HTMLDivElement, surface: HTMLDivElement) {
    const commands = this.commands;
    const resetWheelIdleTimer = () => {
      if (this.wheelIdleTimer !== null) {
        window.clearTimeout(this.wheelIdleTimer);
      }
      this.wheelIdleTimer = window.setTimeout(() => {
        this.wheelIdleTimer = null;
        this.wheelGesture = null;
        this.finish();
      }, GESTURE_IDLE_MS);
    }

    const handleWheel = (event: WheelEvent) => {
      if (
        event.ctrlKey ||
        event.shiftKey ||
        !event.deltaY ||
        Math.abs(event.deltaY) <= Math.abs(event.deltaX)
      ) {
        return;
      }
      if (this.wheelGesture?.stale) {
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
      const gesture = this.wheelGesture ?? {
        direction,
        inputKind: "wheel" as const,
        stale: false
      };
      gesture.direction = direction;
      this.wheelGesture = gesture;
      this.activeGesture = gesture;
      const geometry = geometryFor(surface);
      commands.claimByUser("wheel", direction, {
        ...geometry,
        scrollTop: normalizedScrollTop(surface) + deltaY
      });
      resetWheelIdleTimer();
      if (!targetInsideSurface || nestedAtBoundary) {
        event.preventDefault();
        commands.writeScrollBy(surface, deltaY, "user-wheel-handoff");
      }
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented || isEditableOrInteractiveTarget(event.target)) {
        return;
      }
      if (event.key === "End") {
        event.preventDefault();
        commands.returnToLatest();
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
        commands.claimByUser("keyboard", direction);
        this.scheduleFinish();
      }
    }

    const handlePointerDown = (event: PointerEvent) => {
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
      this.activeGesture = {
        direction: null,
        inputKind: "scrollbar",
        stale: false
      };
    }

    const handlePointerEnd = () => {
      if (this.activeGesture?.inputKind === "scrollbar") {
        this.finish();
      }
    }

    const handleTouchStart = (event: TouchEvent) => {
      if (event.touches.length !== 1 || isEditableOrInteractiveTarget(event.target)) {
        this.touchGesture = null;
        return;
      }
      this.touchGesture = {
        lastY: event.touches[0].clientY,
        stale: false,
        target: event.target
      };
    }

    const handleTouchMove = (event: TouchEvent) => {
      const touchGesture = this.touchGesture;
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
      commands.claimByUser("touch", direction, {
        ...geometry,
        scrollTop: normalizedScrollTop(surface) + deltaY
      });
      if (!targetInsideSurface || nestedAtBoundary) {
        event.preventDefault();
        commands.writeScrollBy(surface, deltaY, "user-touch-handoff");
      }
    }

    const handleTouchEnd = () => {
      this.touchGesture = null;
      this.finish();
    }

    const handleFocusIn = (event: FocusEvent) => commands.onFocus(event);

    const handleScrollEnd = () => {
      if (this.activeGesture) {
        this.finish();
      }
    }

    return installConversationInputListeners(stage, surface, {
      handleWheel,
      handleTouchStart,
      handleTouchMove,
      handleTouchEnd,
      handleObservedScroll: commands.handleObservedScroll,
      handleKeyDown,
      handlePointerDown,
      handlePointerEnd,
      handleFocusIn,
      handleScrollEnd
    });
  }
}
