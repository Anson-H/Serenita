import type {
  CompositionEvent,
  MouseEvent
} from "react";

type TextControl = HTMLInputElement | HTMLTextAreaElement;
export type ScrollPositionSnapshot = {
  element: HTMLElement;
  left: number;
  top: number;
};
type CompositionAwareKeyboardEvent = {
  isComposing?: boolean;
  keyCode?: number;
  nativeEvent?: { isComposing?: boolean };
};

export function isImeComposing(event: CompositionAwareKeyboardEvent) {
  return Boolean(event.isComposing || event.nativeEvent?.isComposing || event.keyCode === 229);
}

export function keepTextControlFocused(event: MouseEvent<HTMLButtonElement>) {
  event.preventDefault();
}

export function focusWithoutScroll<T extends HTMLElement>(element: T | null) {
  element?.focus({ preventScroll: true });
}

export function captureScrollPosition(element: HTMLElement | null): ScrollPositionSnapshot | null {
  return element
    ? { element, left: element.scrollLeft, top: element.scrollTop }
    : null;
}

export function restoreScrollPosition(snapshot: ScrollPositionSnapshot | null) {
  if (!snapshot) return;
  const restore = () => {
    snapshot.element.scrollTo({
      behavior: "auto",
      left: snapshot.left,
      top: snapshot.top
    });
  };
  restore();
  if (typeof window !== "undefined") {
    window.requestAnimationFrame(restore);
  }
}

export function syncCommittedText<T extends TextControl>(
  event: CompositionEvent<T>,
  onValueChange: (value: string) => void
) {
  onValueChange(event.currentTarget.value);
}

export function formTextValue(
  form: HTMLFormElement,
  controlName: string,
  fallback: string
) {
  const control = form.elements.namedItem(controlName);
  return control instanceof HTMLInputElement || control instanceof HTMLTextAreaElement
    ? control.value
    : fallback;
}

export function formTextValues<T extends Record<string, string>>(
  form: HTMLFormElement,
  fallbackValues: T
) {
  return Object.fromEntries(
    Object.entries(fallbackValues).map(([key, fallback]) => [
      key,
      formTextValue(form, key, fallback)
    ])
  ) as T;
}
