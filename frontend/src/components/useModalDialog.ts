import { useEffect, useRef, type RefObject } from "react";

import { focusWithoutScroll, isImeComposing } from "../utils/inputMethod";
import { interactionReturnTarget } from "../utils/interactionFocus";

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "iframe",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])"
].join(",");

function isFocusable(element: HTMLElement) {
  return !element.hidden
    && element.getAttribute("aria-hidden") !== "true"
    && element.getClientRects().length > 0;
}

function focusableElements(dialog: HTMLElement) {
  const modalScopes = Array.from(
    document.querySelectorAll<HTMLElement>('[data-modal-focus-scope="true"]')
  );
  return [dialog, ...modalScopes]
    .flatMap((scope) => Array.from(scope.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)))
    .filter(isFocusable);
}

function openModalFocusScope() {
  return document.querySelector<HTMLElement>('[data-modal-focus-scope="true"]');
}

export function useModalDialog({
  active,
  dialogRef,
  escapeDisabled = false,
  focusKey,
  initialFocusRef,
  onEscape,
  restoreFocusRef
}: {
  active: boolean;
  dialogRef: RefObject<HTMLElement | null>;
  escapeDisabled?: boolean;
  focusKey?: unknown;
  initialFocusRef?: RefObject<HTMLElement | null>;
  onEscape: () => void;
  restoreFocusRef?: RefObject<HTMLElement | null>;
}) {
  const onEscapeRef = useRef(onEscape);
  const escapeDisabledRef = useRef(escapeDisabled);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  onEscapeRef.current = onEscape;
  escapeDisabledRef.current = escapeDisabled;

  useEffect(() => {
    if (!active) return;
    previousFocusRef.current = interactionReturnTarget();
    const appRoot = document.getElementById("root");
    const shouldInertApp = Boolean(appRoot && !appRoot.contains(dialogRef.current));
    const previouslyInert = appRoot?.inert ?? false;
    if (shouldInertApp && appRoot) appRoot.inert = true;
    const underlyingDialogs = Array.from(document.querySelectorAll<HTMLElement>('[role="dialog"][aria-modal="true"]'))
      .filter(element => element !== dialogRef.current && !dialogRef.current?.contains(element))
      .map(element => ({element, inert: element.inert}));
    for (const {element} of underlyingDialogs) element.inert = true;

    return () => {
      for (const {element, inert} of underlyingDialogs) if (element.isConnected) element.inert = inert;
      if (shouldInertApp && appRoot) appRoot.inert = previouslyInert;
      window.requestAnimationFrame(() => {
        const explicitReturnTarget = restoreFocusRef?.current;
        const returnTarget = explicitReturnTarget?.isConnected
          ? explicitReturnTarget
          : previousFocusRef.current?.isConnected
            ? previousFocusRef.current
            : null;
        focusWithoutScroll(returnTarget);
      });
    };
  }, [active, dialogRef, restoreFocusRef]);

  useEffect(() => {
    if (!active) return;
    const focusFrame = window.requestAnimationFrame(() => {
      const dialog = dialogRef.current;
      if (!dialog || dialog.inert) return;
      if (dialog.contains(document.activeElement)) return;
      const target = initialFocusRef?.current
        ?? dialog.querySelector<HTMLElement>("[data-modal-initial-focus]")
        ?? focusableElements(dialog)[0]
        ?? dialog;
      focusWithoutScroll(target);
    });
    return () => window.cancelAnimationFrame(focusFrame);
  }, [active, dialogRef, focusKey, initialFocusRef]);

  useEffect(() => {
    if (!active) return;

    function handleKeyDown(event: globalThis.KeyboardEvent) {
      const dialog = dialogRef.current;
      if (!dialog || dialog.inert) return;
      if (event.key === "Escape") {
        if (isImeComposing(event) || escapeDisabledRef.current) return;
        const expandedControl = document.activeElement instanceof HTMLElement
          ? document.activeElement.closest<HTMLElement>('[aria-expanded="true"]')
          : null;
        if (openModalFocusScope() || expandedControl) return;
        event.preventDefault();
        onEscapeRef.current();
        return;
      }
      if (event.key !== "Tab") return;
      const focusables = focusableElements(dialog);
      if (!focusables.length) {
        event.preventDefault();
        focusWithoutScroll(dialog);
        return;
      }
      const currentIndex = focusables.indexOf(document.activeElement as HTMLElement);
      const nextIndex = event.shiftKey
        ? currentIndex <= 0 ? focusables.length - 1 : currentIndex - 1
        : currentIndex < 0 || currentIndex === focusables.length - 1 ? 0 : currentIndex + 1;
      if (currentIndex < 0 || event.shiftKey && currentIndex === 0 || !event.shiftKey && currentIndex === focusables.length - 1) {
        event.preventDefault();
        focusWithoutScroll(focusables[nextIndex]);
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [active, dialogRef]);
}
