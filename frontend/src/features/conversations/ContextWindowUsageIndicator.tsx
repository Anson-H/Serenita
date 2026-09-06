import { useEffect, useId, useRef, useState } from "react";

import {
  contextWindowUsageCopy,
  type ContextWindowUsage
} from "./modelTokenUsage";

export function ContextWindowUsageIndicator({
  usage
}: {
  usage: ContextWindowUsage;
}) {
  const copy = contextWindowUsageCopy(usage);
  const [pinned, setPinned] = useState(false);
  const controlRef = useRef<HTMLButtonElement>(null);
  const tooltipId = useId();

  useEffect(() => {
    if (!pinned) return;

    const isOutside = (target: EventTarget | null) =>
      target instanceof Node && !controlRef.current?.contains(target);
    const handleOutsidePointer = (event: PointerEvent) => {
      if (isOutside(event.target)) {
        setPinned(false);
        controlRef.current?.blur();
      }
    };
    const handleOutsideFocus = (event: FocusEvent) => {
      if (isOutside(event.target)) setPinned(false);
    };

    document.addEventListener("pointerdown", handleOutsidePointer, true);
    document.addEventListener("focusin", handleOutsideFocus, true);
    return () => {
      document.removeEventListener("pointerdown", handleOutsidePointer, true);
      document.removeEventListener("focusin", handleOutsideFocus, true);
    };
  }, [pinned]);

  return (
    <button
      aria-controls={tooltipId}
      aria-expanded={pinned}
      data-popup-trigger
      aria-label={copy.ariaLabel}
      className="control control--inline control--icon control--ghost context-window-usage"
      onClick={() => setPinned((current) => !current)}
      ref={controlRef}
      type="button"
    >
      <svg aria-hidden="true" className="context-window-usage-outline" viewBox="0 0 50 50">
        <rect className="context-window-usage-track" x="7.5" y="7.5" width="35" height="35" rx="7.5" />
        <rect
          className="context-window-usage-progress"
          x="7.5"
          y="7.5"
          width="35"
          height="35"
          rx="7.5"
          pathLength="100"
          style={{ strokeDashoffset: 100 - usage.percent }}
        />
      </svg>
      <span className="context-window-usage-tooltip" id={tooltipId} role="tooltip">
        <span>背景信息窗口：</span>
        <span>{copy.usageLabel}</span>
        <span>{copy.tokenLabel}</span>
      </span>
    </button>
  );
}
