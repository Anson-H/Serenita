type ConversationInputHandlers = {
  handleWheel: (event: WheelEvent) => void;
  handleTouchStart: (event: TouchEvent) => void;
  handleTouchMove: (event: TouchEvent) => void;
  handleTouchEnd: (event: TouchEvent) => void;
  handleObservedScroll: (event: Event) => void;
  handleKeyDown: (event: KeyboardEvent) => void;
  handlePointerDown: (event: PointerEvent) => void;
  handlePointerEnd: (event: PointerEvent) => void;
  handleFocusIn: (event: FocusEvent) => void;
  handleScrollEnd: (event: Event) => void;
};

export function installConversationInputListeners(stage: HTMLElement, surface: HTMLDivElement, {
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
}: ConversationInputHandlers) {
  stage.addEventListener("wheel", handleWheel, { passive: false });
  stage.addEventListener("touchstart", handleTouchStart, { passive: true });
  stage.addEventListener("touchmove", handleTouchMove, { passive: false });
  stage.addEventListener("touchend", handleTouchEnd);
  stage.addEventListener("touchcancel", handleTouchEnd);
  surface.addEventListener("scroll", handleObservedScroll, { passive: true });
  surface.addEventListener("keydown", handleKeyDown);
  surface.addEventListener("pointerdown", handlePointerDown);
  window.addEventListener("pointerup", handlePointerEnd);
  window.addEventListener("pointercancel", handlePointerEnd);
  document.addEventListener("focusin", handleFocusIn);
  if ("onscrollend" in surface) {
    surface.addEventListener("scrollend", handleScrollEnd);
  }
  return () => {
    stage.removeEventListener("wheel", handleWheel);
    stage.removeEventListener("touchstart", handleTouchStart);
    stage.removeEventListener("touchmove", handleTouchMove);
    stage.removeEventListener("touchend", handleTouchEnd);
    stage.removeEventListener("touchcancel", handleTouchEnd);
    surface.removeEventListener("scroll", handleObservedScroll);
    surface.removeEventListener("keydown", handleKeyDown);
    surface.removeEventListener("pointerdown", handlePointerDown);
    window.removeEventListener("pointerup", handlePointerEnd);
    window.removeEventListener("pointercancel", handlePointerEnd);
    document.removeEventListener("focusin", handleFocusIn);
    if ("onscrollend" in surface) {
      surface.removeEventListener("scrollend", handleScrollEnd);
    }
  };
}
