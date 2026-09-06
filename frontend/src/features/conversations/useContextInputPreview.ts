import { useEffect, useLayoutEffect, useRef, useState } from "react";

export function useContextInputPreview(align: "start" | "end") {
  const previewRootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLDivElement>(null);
  const previewRef = useRef<HTMLDivElement>(null);
  const [previewPinned, setPreviewPinned] = useState(false);

  useLayoutEffect(() => {
    const root = previewRootRef.current, preview = previewRef.current, trigger = triggerRef.current;
    if (!root || !preview || !trigger) return;
    const boundary = root.closest(".conversation-composer, .message-entry") ?? root.parentElement;
    if (!boundary) return;
    const updatePosition = () => {
      const view = window.visualViewport;
      const rootBounds = root.getBoundingClientRect();
      const anchor = align === "end" ? trigger.getBoundingClientRect() : rootBounds;
      const content = boundary.getBoundingClientRect();
      const style = getComputedStyle(root);
      const edgeInset = parseFloat(style.getPropertyValue("--space-content"));
      const gap = parseFloat(style.getPropertyValue("--space-related"));
      const viewLeft = view?.offsetLeft ?? 0, viewTop = view?.offsetTop ?? 0;
      const viewWidth = view?.width ?? window.innerWidth, viewHeight = view?.height ?? window.innerHeight;
      const left = Math.max(content.left, viewLeft + edgeInset);
      const right = Math.min(content.right, viewLeft + viewWidth - edgeInset);
      const maxWidth = Math.max(0, align === "end" ? anchor.right - left : right - anchor.left);
      const heightLimit = Math.min(360, viewHeight * 0.48);
      const above = Math.max(0, anchor.top - viewTop - edgeInset - gap);
      const below = Math.max(0, viewTop + viewHeight - edgeInset - anchor.bottom - gap);
      let side = align === "start" ? "above" : "below";
      const preferred = side === "above" ? above : below;
      const opposite = side === "above" ? below : above;
      if (preferred < Math.min(160, heightLimit) && opposite > preferred) {
        side = side === "above" ? "below" : "above";
      }
      preview.dataset.side = side;
      preview.style.setProperty("--context-preview-right", `${rootBounds.right - anchor.right}px`);
      preview.style.setProperty("--context-preview-max-width", `${maxWidth}px`);
      preview.style.setProperty("--context-preview-max-height", `${Math.min(heightLimit, side === "above" ? above : below)}px`);
    };
    updatePosition();
    const observer = new ResizeObserver(updatePosition);
    observer.observe(root);
    observer.observe(trigger);
    observer.observe(boundary);
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    window.visualViewport?.addEventListener("resize", updatePosition);
    window.visualViewport?.addEventListener("scroll", updatePosition);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
      window.visualViewport?.removeEventListener("resize", updatePosition);
      window.visualViewport?.removeEventListener("scroll", updatePosition);
    };
  }, [align]);

  useEffect(() => {
    if (!previewPinned) {
      return;
    }

    const closeFromOutside = (event: MouseEvent) => {
      if (
        previewRootRef.current
        && !event.composedPath().includes(previewRootRef.current)
      ) {
        setPreviewPinned(false);
        const activeElement = document.activeElement;
        if (
          activeElement instanceof HTMLElement
          && previewRootRef.current.contains(activeElement)
        ) {
          activeElement.blur();
        }
      }
    };
    const closeFromEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setPreviewPinned(false);
        const activeElement = document.activeElement;
        if (
          activeElement instanceof HTMLElement
          && previewRootRef.current?.contains(activeElement)
        ) {
          activeElement.blur();
        }
      }
    };

    document.addEventListener("click", closeFromOutside, true);
    document.addEventListener("keydown", closeFromEscape);
    return () => {
      document.removeEventListener("click", closeFromOutside, true);
      document.removeEventListener("keydown", closeFromEscape);
    };
  }, [previewPinned]);

  return { previewRootRef, triggerRef, previewRef, previewPinned, setPreviewPinned };
}
