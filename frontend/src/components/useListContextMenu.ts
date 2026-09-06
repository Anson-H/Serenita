import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type MouseEvent,
  type PointerEvent as ReactPointerEvent
} from "react";

import { scrollAffectsAnchor } from "../utils/overlayEvents";

const MENU_POINTER_GAP = 8;
const MENU_VIEWPORT_GAP = 15;

type ListContextMenu = {
  id: string;
  anchor: HTMLButtonElement;
  x: number;
  y: number;
  triggerX: number;
  triggerY: number;
};
type LongPress = {
  id: string;
  anchor: HTMLButtonElement;
  pointerId: number;
  x: number;
  y: number;
  timer: number;
};

function menuCoordinate(trigger: number, size: number, viewportSize: number) {
  const after = trigger + MENU_POINTER_GAP;
  const before = trigger - size - MENU_POINTER_GAP;
  const max = viewportSize - size - MENU_VIEWPORT_GAP;
  return Math.max(MENU_VIEWPORT_GAP, Math.min(after <= max ? after : before, max));
}

/** Shared row gestures, keyboard navigation, positioning, and overlay lifetime. */
export function useListContextMenu({ enabled, scope }: { enabled: boolean; scope: string }) {
  const [contextMenu, setContextMenu] = useState<ListContextMenu | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const gestureRef = useRef<LongPress | null>(null);
  const suppressedClickRef = useRef<string | null>(null);
  const releaseTimerRef = useRef<number | null>(null);

  const cancelLongPress = useCallback(() => {
    if (gestureRef.current) window.clearTimeout(gestureRef.current.timer);
    gestureRef.current = null;
  }, []);

  const clearSuppressedClick = useCallback(() => {
    if (releaseTimerRef.current !== null) window.clearTimeout(releaseTimerRef.current);
    releaseTimerRef.current = null;
    suppressedClickRef.current = null;
  }, []);

  const closeContextMenu = useCallback((restoreFocus = true) => {
    setContextMenu((current) => {
      if (restoreFocus && current?.anchor.isConnected) {
        window.requestAnimationFrame(() => current.anchor.focus({ preventScroll: true }));
      }
      return null;
    });
  }, []);

  useEffect(() => {
    closeContextMenu(false);
    cancelLongPress();
    clearSuppressedClick();
  }, [scope, closeContextMenu, cancelLongPress, clearSuppressedClick]);

  useEffect(() => {
    if (!enabled) {
      closeContextMenu(false);
      cancelLongPress();
    }
  }, [enabled, closeContextMenu, cancelLongPress]);

  useEffect(() => {
    const onScroll = (event: Event) => {
      if (scrollAffectsAnchor(event, gestureRef.current?.anchor ?? null)) cancelLongPress();
    };
    window.addEventListener("scroll", onScroll, true);
    return () => {
      window.removeEventListener("scroll", onScroll, true);
      cancelLongPress();
      clearSuppressedClick();
    };
  }, [cancelLongPress, clearSuppressedClick]);

  useEffect(() => {
    if (!contextMenu) return;
    const frame = window.requestAnimationFrame(() => {
      menuRef.current?.querySelector<HTMLButtonElement>('[role="menuitem"]:not(:disabled)')
        ?.focus({ preventScroll: true });
    });
    const onOutsidePointer = (event: PointerEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) closeContextMenu(false);
    };
    const onResize = () => closeContextMenu(false);
    const onScroll = (event: Event) => {
      if (scrollAffectsAnchor(event, contextMenu.anchor)) closeContextMenu(false);
    };
    document.addEventListener("pointerdown", onOutsidePointer, true);
    window.addEventListener("resize", onResize);
    window.addEventListener("scroll", onScroll, true);
    return () => {
      window.cancelAnimationFrame(frame);
      document.removeEventListener("pointerdown", onOutsidePointer, true);
      window.removeEventListener("resize", onResize);
      window.removeEventListener("scroll", onScroll, true);
    };
  }, [contextMenu, closeContextMenu]);

  useLayoutEffect(() => {
    if (!contextMenu || !menuRef.current) return;
    const bounds = menuRef.current.getBoundingClientRect();
    const x = menuCoordinate(contextMenu.triggerX, bounds.width, window.innerWidth);
    const y = menuCoordinate(contextMenu.triggerY, bounds.height, window.innerHeight);
    if (x !== contextMenu.x || y !== contextMenu.y) setContextMenu({ ...contextMenu, x, y });
  }, [contextMenu]);

  function open(id: string, anchor: HTMLButtonElement, x: number, y: number) {
    cancelLongPress();
    if (enabled) setContextMenu({
      id, anchor, triggerX: x, triggerY: y,
      x: x + MENU_POINTER_GAP, y: y + MENU_POINTER_GAP
    });
  }

  function finishPointer() {
    cancelLongPress();
    // Keep the click suppressed for the whole hold, then consume the release click.
    if (suppressedClickRef.current) {
      releaseTimerRef.current = window.setTimeout(clearSuppressedClick, 700);
    }
  }

  function rowProps<E extends HTMLElement = HTMLButtonElement>(id: string, anchorSelector?: string) {
    const anchorFor = (element: E) => anchorSelector
      ? element.querySelector<HTMLButtonElement>(anchorSelector)
      : element as unknown as HTMLButtonElement;
    return {
      "data-context-menu-trigger": "",
      "data-context-menu-open": contextMenu?.id === id ? "true" : undefined,
      onContextMenu(event: MouseEvent<E>) {
        event.preventDefault();
        const anchor = anchorFor(event.currentTarget);
        if (anchor) open(id, anchor, event.clientX, event.clientY);
      },
      onKeyDown(event: KeyboardEvent<E>) {
        if ((event.shiftKey && event.key === "F10") || event.key === "ContextMenu") {
          event.preventDefault();
          const anchor = anchorFor(event.currentTarget);
          if (!anchor) return;
          const bounds = anchor.getBoundingClientRect();
          open(id, anchor, bounds.left + Math.min(bounds.width / 2, 88), bounds.top + bounds.height / 2);
        }
      },
      onPointerDown(event: ReactPointerEvent<E>) {
        cancelLongPress();
        clearSuppressedClick();
        if (!enabled || event.pointerType === "mouse" || !event.isPrimary || event.button !== 0) return;
        const anchor = anchorFor(event.currentTarget);
        if (!anchor) return;
        const gesture: LongPress = {
          id, anchor, pointerId: event.pointerId,
          x: event.clientX, y: event.clientY, timer: 0
        };
        gesture.timer = window.setTimeout(() => {
          if (gestureRef.current !== gesture) return;
          suppressedClickRef.current = id;
          open(id, gesture.anchor, gesture.x, gesture.y);
        }, 500);
        gestureRef.current = gesture;
      },
      onPointerMove(event: ReactPointerEvent<E>) {
        const gesture = gestureRef.current;
        if (gesture && event.pointerId === gesture.pointerId
          && Math.hypot(event.clientX - gesture.x, event.clientY - gesture.y) > 8) cancelLongPress();
      },
      onPointerUp: finishPointer,
      onPointerCancel: finishPointer,
      onClickCapture(event: MouseEvent<E>) {
        if (suppressedClickRef.current !== id) return;
        event.preventDefault();
        event.stopPropagation();
        clearSuppressedClick();
      }
    };
  }

  function onMenuKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape" || event.key === "Tab") {
      if (event.key === "Escape") event.preventDefault();
      closeContextMenu(event.key === "Escape");
      return;
    }
    const items = [...event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="menuitem"]:not(:disabled)')];
    if (!items.length) return;
    const index = items.indexOf(document.activeElement as HTMLButtonElement);
    let next: number;
    if (event.key === "ArrowDown") next = (index + 1) % items.length;
    else if (event.key === "ArrowUp") next = (index <= 0 ? items.length : index) - 1;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = items.length - 1;
    else return;
    event.preventDefault();
    items[next].focus({ preventScroll: true });
  }

  return { contextMenu, menuRef, closeContextMenu, rowProps, onMenuKeyDown };
}
