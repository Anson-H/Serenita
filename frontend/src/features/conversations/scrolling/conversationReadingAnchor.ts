import { readableConversationRect, SCROLL_BOUNDARY_EPSILON_PX } from "./conversationScrollGeometry";
export type ReadingAnchor = { messageId: string | null; node: HTMLElement; viewportTop: number };
/** Owns the reading position independently of a DOM node being replaced. */
export class ConversationReadingAnchor {
  private anchor: ReadingAnchor | null = null;
  private messageIds = new WeakMap<HTMLElement, string>();
  get current() { return this.anchor; }
  clear() { this.anchor = null; }
  register(id: string, node: HTMLElement) { this.messageIds.set(node, id); }
  acceptPosition(top: number) { if (this.anchor) this.anchor.viewportTop = top; }
  resolve(anchor: ReadingAnchor, messageRefs: Map<string, HTMLElement>) {
    if (anchor.node.isConnected) {
      return anchor.node;
    }
    return anchor.messageId ? messageRefs.get(anchor.messageId) ?? null : null;
  }

  private findRegisteredMessage(node: Element | null, surface: HTMLDivElement) {
    let current = node;
    while (current && current !== surface) {
      if (current instanceof HTMLElement) {
        const messageId = this.messageIds.get(current);
        if (messageId) {
          return { messageId, node: current };
        }
      }
      current = current.parentElement;
    }
    return null;
  }

  capture(surface: HTMLDivElement | null, stage: HTMLDivElement | null, messageRefs: Map<string, HTMLElement>, preferred?: HTMLElement | null) {
    if (!surface) {
      return null;
    }
    if (preferred && surface.contains(preferred)) {
      const registered = this.findRegisteredMessage(preferred, surface);
      const anchor = {
        messageId: registered?.messageId ?? null,
        node: preferred,
        viewportTop: preferred.getBoundingClientRect().top
      };
      this.anchor = anchor;
      return anchor;
    }

    const readableRect = readableConversationRect(
      surface,
      stage
    );
    const surfaceRect = surface.getBoundingClientRect();
    const sampleX = [
      surfaceRect.left + 1,
      surfaceRect.left + surfaceRect.width / 2,
      surfaceRect.right - 1
    ];
    const sampleY = [1, 16, 32, 48]
      .map((offset) => readableRect.top + offset)
      .filter((value) => value < readableRect.bottom);
    let candidate: { messageId: string; node: HTMLElement; rect: DOMRect } | null = null;

    for (const y of sampleY) {
      for (const x of sampleX) {
        const registered = this.findRegisteredMessage(document.elementFromPoint(x, y), surface);
        if (!registered || !registered.node.isConnected) {
          continue;
        }
        const rect = registered.node.getBoundingClientRect();
        if (
          rect.bottom > readableRect.top + SCROLL_BOUNDARY_EPSILON_PX &&
          rect.top < readableRect.bottom - SCROLL_BOUNDARY_EPSILON_PX &&
          (!candidate || rect.top < candidate.rect.top)
        ) {
          candidate = { ...registered, rect };
        }
      }
      if (candidate) {
        break;
      }
    }

    if (!candidate) {
      for (const [messageId, node] of messageRefs) {
        if (!node.isConnected) {
          continue;
        }
        const rect = node.getBoundingClientRect();
        if (
          rect.bottom > readableRect.top + SCROLL_BOUNDARY_EPSILON_PX &&
          rect.top < readableRect.bottom - SCROLL_BOUNDARY_EPSILON_PX &&
          (!candidate || rect.top < candidate.rect.top)
        ) {
          candidate = { messageId, node, rect };
        }
      }
    }
    if (!candidate) {
      this.anchor = null;
      return null;
    }
    const anchor = {
      messageId: candidate.messageId,
      node: candidate.node,
      viewportTop: candidate.rect.top
    };
    this.anchor = anchor;
    return anchor;
  }

}
