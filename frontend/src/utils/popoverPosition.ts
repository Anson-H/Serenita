export type SelectMenuLayout = {
  menuWidth: "trigger" | "content";
  menuAlign: "start" | "end";
};

export type PopoverPosition = {
  left: number;
  top: number;
  width: number;
  maxWidth: number;
  maxHeight: number;
  placement: "above" | "below";
};

export function calculatePopoverPosition({ anchor, viewport, edgeInset, gap, contentWidth, maxHeight, menuWidth, menuAlign }: SelectMenuLayout & {
  anchor: { left: number; top: number; bottom: number; width: number };
  viewport: { left: number; top: number; width: number; height: number };
  edgeInset: number;
  gap: number;
  contentWidth: number;
  maxHeight: number;
}): PopoverPosition {
  const right = viewport.left + viewport.width;
  const bottom = viewport.top + viewport.height;
  const maxWidth = Math.max(0, viewport.width - edgeInset * 2);
  const width = Math.min(menuWidth === "trigger" ? anchor.width : contentWidth, maxWidth);
  const below = Math.max(0, bottom - edgeInset - anchor.bottom - gap);
  const above = Math.max(0, anchor.top - gap - viewport.top - edgeInset);
  const placement = below < Math.min(160, maxHeight) && above > below ? "above" : "below";
  const top = Math.max(viewport.top + edgeInset,
    Math.min(placement === "above" ? anchor.top - gap : anchor.bottom + gap, bottom - edgeInset));
  return {
    left: Math.max(viewport.left + edgeInset, Math.min(menuAlign === "end" ? anchor.left + anchor.width - width : anchor.left, right - edgeInset - width)),
    top,
    width,
    maxWidth,
    maxHeight: Math.max(0, Math.min(maxHeight, placement === "above"
      ? top - viewport.top - edgeInset : bottom - edgeInset - top)),
    placement
  };
}

export function samePopoverPosition(current: PopoverPosition | null, next: PopoverPosition) {
  return Boolean(current && current.left === next.left && current.top === next.top
    && current.width === next.width && current.maxWidth === next.maxWidth && current.maxHeight === next.maxHeight
    && current.placement === next.placement);
}
