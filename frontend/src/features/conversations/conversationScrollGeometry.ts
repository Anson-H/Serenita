import {
  clampConversationScrollTop,
  type ConversationScrollDirection,
  type ConversationScrollGeometry,
  type ConversationScrollState
} from "./conversationScrollStateMachine";

const WHEEL_LINE_HEIGHT_PX = 16;

const WHEEL_DELTA_MODE_LINE = 1;

const WHEEL_DELTA_MODE_PAGE = 2;

export const SCROLL_BOUNDARY_EPSILON_PX = 1;

export function geometryFor(surface: HTMLElement): ConversationScrollGeometry {
  return {
    clientHeight: surface.clientHeight,
    scrollHeight: surface.scrollHeight,
    scrollTop: surface.scrollTop
  };
}

export function normalizedScrollTop(surface: HTMLElement) {
  return clampConversationScrollTop(geometryFor(surface));
}

function isVerticalScroller(element: HTMLElement) {
  const { overflowY } = window.getComputedStyle(element);
  return (
    ["auto", "scroll", "overlay"].includes(overflowY) &&
    element.scrollHeight - element.clientHeight > SCROLL_BOUNDARY_EPSILON_PX
  );
}

function canConsumeVerticalScroll(
  element: HTMLElement,
  direction: ConversationScrollDirection
) {
  const maxScrollTop = Math.max(0, element.scrollHeight - element.clientHeight);
  const scrollTop = Math.min(maxScrollTop, Math.max(0, element.scrollTop));
  return direction === "up"
    ? scrollTop > SCROLL_BOUNDARY_EPSILON_PX
    : maxScrollTop - scrollTop > SCROLL_BOUNDARY_EPSILON_PX;
}

export function findConsumableVerticalScroller(
  target: EventTarget | null,
  boundary: HTMLElement,
  direction: ConversationScrollDirection
) {
  let element = target instanceof Element ? target : null;
  while (element && element !== boundary) {
    if (
      element instanceof HTMLElement &&
      isVerticalScroller(element) &&
      canConsumeVerticalScroll(element, direction)
    ) {
      return element;
    }
    element = element.parentElement;
  }
  return null;
}

export function hasNestedVerticalScroller(
  target: EventTarget | null,
  boundary: HTMLElement
) {
  let element = target instanceof Element ? target : null;
  while (element && element !== boundary) {
    if (element instanceof HTMLElement && isVerticalScroller(element)) {
      return true;
    }
    element = element.parentElement;
  }
  return false;
}

export function normalizedWheelDelta(event: WheelEvent, surface: HTMLElement) {
  if (event.deltaMode === WHEEL_DELTA_MODE_LINE) {
    return event.deltaY * WHEEL_LINE_HEIGHT_PX;
  }
  if (event.deltaMode === WHEEL_DELTA_MODE_PAGE) {
    return event.deltaY * surface.clientHeight;
  }
  return event.deltaY;
}

export function isEditableOrInteractiveTarget(target: EventTarget | null) {
  if (!(target instanceof Element)) {
    return false;
  }
  return Boolean(target.closest(
    "input, textarea, select, button, summary, label, a, [contenteditable='true'], [role='menu'], [role='dialog'], [data-interaction-owner='self'], .queued-input-drag-handle"
  ));
}

export function readableConversationRect(
  surface: HTMLDivElement,
  stage: HTMLDivElement | null
) {
  const surfaceRect = surface.getBoundingClientRect();
  const stageRect = stage?.getBoundingClientRect() ?? surfaceRect;
  const viewport = window.visualViewport;
  const viewportTop = viewport?.offsetTop ?? 0;
  const viewportBottom = viewport
    ? viewport.offsetTop + viewport.height
    : window.innerHeight;
  let top = Math.max(surfaceRect.top, stageRect.top, viewportTop);
  let bottom = Math.min(surfaceRect.bottom, stageRect.bottom, viewportBottom);

  if (stage) {
    const overlayHeight = Number.parseFloat(
      window.getComputedStyle(stage).getPropertyValue("--composer-overlay-height")
    );
    if (Number.isFinite(overlayHeight) && overlayHeight > 0) {
      bottom = Math.min(bottom, stageRect.bottom - overlayHeight);
    }
    const composer = stage.querySelector<HTMLElement>(".conversation-composer");
    if (composer) {
      bottom = Math.min(bottom, composer.getBoundingClientRect().top);
    }
    const tailButton = stage.querySelector<HTMLElement>(".conversation-tail-button");
    if (tailButton) {
      bottom = Math.min(bottom, tailButton.getBoundingClientRect().top);
    }
  }

  if (bottom < top) {
    top = bottom;
  }
  return {
    bottom,
    height: Math.max(0, bottom - top),
    top
  };
}

export function shouldShowTailButton(
  state: ConversationScrollState,
  reconciliationSuspended: boolean
) {
  return (
    state.followIntent === "paused" ||
    state.operation === "returning" ||
    (reconciliationSuspended && !state.atTail)
  );
}
