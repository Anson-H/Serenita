import { isImeComposing } from "./inputMethod";

export type FocusModality = "keyboard" | "pointer";

type FocusTracking = {
  setModality: (modality: FocusModality) => void;
  returnTarget: () => HTMLElement | null;
  dispose: () => void;
};
const tracking = new WeakMap<Document, FocusTracking>();

function textControl(element: Element | null) {
  return Boolean(element?.matches('input:not([type="checkbox"], [type="radio"], [type="file"], [type="range"], [type="color"], [type="button"], [type="submit"], [type="reset"]), textarea, [contenteditable="true"]'));
}

function focusSurface(element: HTMLElement) {
  const interactionOwner = element.dataset.interactionOwner;
  if (interactionOwner === "self") return element;
  if (interactionOwner === "row") {
    return element.closest<HTMLElement>(".field-row")
      ?? element.closest<HTMLElement>("[data-row-surface]")
      ?? element.closest<HTMLElement>(".grouped-object-list > *")
      ?? element;
  }
  // Editable text belongs to its input surface; unmarked actions own themselves.
  if (textControl(element)) {
    return element.closest<HTMLElement>(".field-row")
      ?? element.closest<HTMLElement>("[data-input-surface]")
      ?? element;
  }
  if (element.matches('input[type="file"]')) return element.closest("label") ?? element;
  if (element.matches('input[type="checkbox"], input[type="radio"]')) {
    return element.parentElement?.querySelector<HTMLElement>(".selection-check-control") ?? element;
  }
  return element;
}

/** One input-modality tracker for the application and memory-only browser fixtures. */
export function installInteractionFocus(doc: Document = document) {
  tracking.get(doc)?.dispose();
  let modality: FocusModality = "pointer";
  let marked: HTMLElement | null = null;
  let keyboardTransfer = false;
  let pointerTarget: HTMLElement | null = null;

  function clear() {
    marked?.removeAttribute("data-keyboard-focus");
    marked = null;
  }

  function render() {
    clear();
    const active = doc.activeElement;
    if (modality !== "keyboard" || !(active instanceof HTMLElement) || active === doc.body) return;
    marked = focusSurface(active);
    const inset = marked.matches(".grouped-object-list > *, .field-row, [data-row-surface], .root-disclosure-toggle");
    marked.setAttribute("data-keyboard-focus", inset ? "inset" : "outset");
  }

  function setModality(next: FocusModality) {
    modality = next;
    render();
  }

  function pointerDown(event: PointerEvent) {
    keyboardTransfer = false;
    pointerTarget = event.target instanceof Element
      ? event.target.closest<HTMLElement>('button:enabled, a[href], input:enabled, textarea:enabled, select:enabled, [role="button"], [tabindex]')
      : null;
    setModality("pointer");
  }

  function keyDown(event: KeyboardEvent) {
    if (isImeComposing(event) || event.metaKey || event.ctrlKey || (event.altKey && event.key !== "Tab")) return;
    const editing = textControl(doc.activeElement);
    const navigation = event.key === "Tab" || event.key === "Escape"
      || (!editing && ["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Home", "End", "PageUp", "PageDown", "Enter", " ", "ContextMenu", "F10"].includes(event.key));
    // Enter may commit a text field and transfer focus; entering a newline does not switch modality.
    keyboardTransfer = navigation || (editing && event.key === "Enter");
    if (navigation) setModality("keyboard");
  }

  function keyUp() { keyboardTransfer = false; }
  function focusIn() {
    if (keyboardTransfer) modality = "keyboard";
    render();
  }

  doc.addEventListener("pointerdown", pointerDown, true);
  doc.addEventListener("keydown", keyDown, true);
  doc.addEventListener("keyup", keyUp, true);
  doc.addEventListener("focusin", focusIn, true);
  doc.addEventListener("focusout", clear, true);
  function dispose() {
    clear();
    doc.removeEventListener("pointerdown", pointerDown, true);
    doc.removeEventListener("keydown", keyDown, true);
    doc.removeEventListener("keyup", keyUp, true);
    doc.removeEventListener("focusin", focusIn, true);
    doc.removeEventListener("focusout", clear, true);
    tracking.delete(doc);
  }
  tracking.set(doc, {
    setModality,
    // Safari may activate a pointer-clicked button without moving DOM focus to it.
    returnTarget: () => modality === "pointer" && pointerTarget?.isConnected ? pointerTarget : null,
    dispose
  });
  return dispose;
}

export function interactionReturnTarget(doc: Document = document) {
  return tracking.get(doc)?.returnTarget()
    ?? (doc.activeElement instanceof HTMLElement ? doc.activeElement : null);
}

/** Programmatic menu focus follows the action that opened or closed it. */
export function focusWithModality(element: HTMLElement | null, modality: FocusModality) {
  if (!element) return;
  tracking.get(element.ownerDocument)?.setModality(modality);
  element.focus({ preventScroll: true });
}
