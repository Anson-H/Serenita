type Nodes = { flow: HTMLElement; messageList: HTMLDivElement; sentinel: HTMLElement | null; surface: HTMLDivElement };
/** Owns observers for one current content binding and ignores callbacks after disposal. */
export class ConversationContentObserver {
  private nodes: Nodes | null = null;
  private cleanup: (() => void) | null = null;
  disconnect() { this.cleanup?.(); this.cleanup = null; this.nodes = null; }
  observe(messageList: HTMLDivElement | null, surface: HTMLDivElement | null, invalidateGeometry: () => void) {
    const flow = messageList?.querySelector<HTMLElement>(".conversation-message-flow") ?? null;
    const sentinel = messageList?.querySelector<HTMLElement>(".conversation-tail-sentinel") ?? null;
    if (!messageList || !surface || !flow) {
      this.cleanup?.();
      this.cleanup = null;
      this.nodes = null;
      return;
    }
    const observed = this.nodes;
    if (
      observed?.flow === flow &&
      observed.messageList === messageList &&
      observed.sentinel === sentinel &&
      observed.surface === surface
    ) {
      return;
    }
    this.cleanup?.();
    let disposed = false;
    const nodes = { flow, messageList, sentinel, surface };
    this.nodes = nodes;
    const notify = () => {
      if (!disposed && this.nodes === nodes) {
        invalidateGeometry();
      }
    };
    const resizeObserver = typeof ResizeObserver === "undefined"
      ? null
      : new ResizeObserver(notify);
    resizeObserver?.observe(flow);
    resizeObserver?.observe(surface);
    resizeObserver?.observe(messageList);
    const mutationObserver = typeof MutationObserver === "undefined"
      ? null
      : new MutationObserver(notify);
    mutationObserver?.observe(flow, {
      attributes: true,
      attributeFilter: ["open", "src", "style"],
      characterData: true,
      childList: true,
      subtree: true
    });
    const intersectionObserver = sentinel && typeof IntersectionObserver !== "undefined"
      ? new IntersectionObserver(notify, { root: surface, threshold: 1 })
      : null;
    if (sentinel) {
      intersectionObserver?.observe(sentinel);
    }
    const handleMediaSettled = () => notify();
    messageList.addEventListener("load", handleMediaSettled, true);
    messageList.addEventListener("error", handleMediaSettled, true);
    const fonts = document.fonts;
    const handleFontsSettled = () => notify();
    fonts?.addEventListener?.("loadingdone", handleFontsSettled);
    void fonts?.ready?.then(handleFontsSettled).catch(() => undefined);
    notify();
    this.cleanup = () => {
      disposed = true;
      resizeObserver?.disconnect();
      mutationObserver?.disconnect();
      intersectionObserver?.disconnect();
      messageList.removeEventListener("load", handleMediaSettled, true);
      messageList.removeEventListener("error", handleMediaSettled, true);
      fonts?.removeEventListener?.("loadingdone", handleFontsSettled);
    };
  }
}
