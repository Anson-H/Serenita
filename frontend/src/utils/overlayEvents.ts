/** Only scrolling an anchor's ancestors can move it away from its overlay. */
export function scrollAffectsAnchor(event: Event, anchor: HTMLElement | null): boolean {
  if (!anchor) return false;
  const target = event.target;
  if (target === anchor.ownerDocument || target === anchor.ownerDocument.defaultView) {
    return true;
  }
  return target instanceof Element && target !== anchor && target.contains(anchor);
}
