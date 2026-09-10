import { useLayoutEffect } from "react";

/** Keep each content inset tied to its own scrollbar's actual layout width. */
export function useScrollbarMetrics() {
  useLayoutEffect(() => {
    const selector = ".scroll-content, .scroll-balanced, .conversation-surface";
    const property = "--scrollbar-layout-width";
    const elements = new Set<HTMLElement>();

    const root = document.documentElement;
    const previousRootLayout = root.getAttribute("data-scrollbar-layout");
    const previousRootWidth = root.style.getPropertyValue(property);
    const probe = document.createElement("div");
    probe.style.cssText =
      "position:absolute;visibility:hidden;overflow:scroll;width:100px;height:100px;inset:-9999px auto auto -9999px;";
    document.body.append(probe);
    const defaultLayoutWidth = probe.offsetWidth - probe.clientWidth;
    probe.remove();
    root.dataset.scrollbarLayout = defaultLayoutWidth > 0 ? "classic" : "overlay";
    root.style.setProperty(property, `${defaultLayoutWidth}px`);

    const scheduledFrames = new Map<HTMLElement, number>();
    const measure = (element: HTMLElement) => {
      const style = getComputedStyle(element);
      const borders = parseFloat(style.borderLeftWidth) + parseFloat(style.borderRightWidth);
      const width = Math.max(0, element.offsetWidth - element.clientWidth - borders);
      // Zero is authoritative too: overlay and non-overflowing surfaces must
      // never inherit a parent's occupied scrollbar width.
      const value = `${width}px`;
      if (element.style.getPropertyValue(property) !== value) {
        element.style.setProperty(property, value);
      }
      element.dataset.scrollbarLayout = width > 0 ? "classic" : "overlay";
    };
    const scheduleRemeasure = (element: HTMLElement) => {
      const previousFrame = scheduledFrames.get(element);
      if (previousFrame !== undefined) window.cancelAnimationFrame(previousFrame);
      scheduledFrames.set(element, window.requestAnimationFrame(() => {
        scheduledFrames.delete(element);
        if (element.isConnected) measure(element);
      }));
    };
    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) measure(entry.target as HTMLElement);
    });
    const observe = (element: HTMLElement) => {
      if (elements.has(element)) return;
      elements.add(element);
      measure(element);
      scheduleRemeasure(element);
      resizeObserver.observe(element);
    };
    const observeTree = (node: Node) => {
      if (!(node instanceof Element)) return;
      if (node instanceof HTMLElement && node.matches(selector)) observe(node);
      node.querySelectorAll<HTMLElement>(selector).forEach(observe);
    };
    observeTree(document.body);

    // Overflow can change without a ResizeObserver notification in WebKit.
    // Remeasure affected ancestors when their content or visibility changes.
    const mutationObserver = new MutationObserver((records) => {
      for (const record of records) {
        record.addedNodes.forEach(observeTree);
        if (record.attributeName === "class") observeTree(record.target);
        let ancestor = record.target instanceof Element ? record.target : record.target.parentElement;
        while (ancestor) {
          if (ancestor instanceof HTMLElement && elements.has(ancestor)) scheduleRemeasure(ancestor);
          ancestor = ancestor.parentElement;
        }
      }
      for (const element of elements) {
        if (element.isConnected) continue;
        resizeObserver.unobserve(element);
        const frame = scheduledFrames.get(element);
        if (frame !== undefined) window.cancelAnimationFrame(frame);
        scheduledFrames.delete(element);
        element.style.removeProperty(property);
        element.removeAttribute("data-scrollbar-layout");
        elements.delete(element);
      }
    });
    mutationObserver.observe(document.body, {
      childList: true, characterData: true, subtree: true,
      attributes: true, attributeFilter: ["class", "style", "hidden"]
    });

    return () => {
      mutationObserver.disconnect();
      resizeObserver.disconnect();
      for (const frame of scheduledFrames.values()) window.cancelAnimationFrame(frame);
      scheduledFrames.clear();
      for (const element of elements) {
        element.style.removeProperty(property);
        element.removeAttribute("data-scrollbar-layout");
      }
      if (previousRootLayout === null) root.removeAttribute("data-scrollbar-layout");
      else root.setAttribute("data-scrollbar-layout", previousRootLayout);
      if (previousRootWidth) root.style.setProperty(property, previousRootWidth);
      else root.style.removeProperty(property);
    };
  }, []);
}
