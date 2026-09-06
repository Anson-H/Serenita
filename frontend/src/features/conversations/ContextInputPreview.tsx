import {
  useId,
  type ReactNode
} from "react";
import { useContextInputPreview } from "./useContextInputPreview";

export function displayModelInputText(value: string) {
  const markerEnd = value.indexOf("\n");
  if (markerEnd < 0) {
    return value;
  }
  const marker = value.slice(0, markerEnd);
  const payloadText = value.slice(markerEnd + 1);
  if (marker === "ATTACHED EXISTING CONTENT") {
    return payloadText;
  }
  try {
    const payload = JSON.parse(payloadText) as Record<string, unknown>;
    if (marker === "ATTACHED ANNOTATION") {
      return typeof payload.annotation_text === "string" ? payload.annotation_text : value;
    }
  } catch {
    return value;
  }
  return value;
}

export function ContextInputPreview({
  ariaLabel,
  className,
  emptyMessage,
  icon,
  label,
  modelInputText,
  previewContent,
  align = "start",
  previewInteractive = false,
  trailing
}: {
  ariaLabel: string;
  className: string;
  emptyMessage: string;
  icon: ReactNode;
  label: string;
  modelInputText?: string;
  previewContent?: ReactNode;
  align?: "start" | "end";
  previewInteractive?: boolean;
  trailing?: ReactNode;
}) {
  const previewId = useId();
  const { previewRootRef, triggerRef, previewRef, previewPinned, setPreviewPinned } = useContextInputPreview(align);

  return (
    <div
      className={`context-resource-preview ${className}`}
      data-preview-align={align}
      data-preview-pinned={previewPinned ? "true" : undefined}
      ref={previewRootRef}
    >
      <div className="compact-control-bar context-reference-trigger" data-row-surface ref={triggerRef}>
        <button
          className="control control--inline-compact control--ghost"
          data-interaction-owner="row"
          data-popup-trigger
          aria-controls={previewId}
          aria-describedby={previewId}
          aria-expanded={previewPinned}
          aria-label={ariaLabel}
          onClick={(event) => {
            const nextPinned = !previewPinned;
            setPreviewPinned(nextPinned);
            if (!nextPinned) event.currentTarget.blur();
          }}
          type="button"
        >
          {icon}
          <span className="context-resource-label">{label}</span>
        </button>
        {trailing}
      </div>
      <div
        className="context-input-preview"
        id={previewId}
        ref={previewRef}
        role={previewInteractive ? "dialog" : "tooltip"}
      >
        <div className="context-input-preview-content">
          {previewContent}
          {!previewContent && modelInputText ? (
            <pre>{displayModelInputText(modelInputText)}</pre>
          ) : null}
          {!previewContent && !modelInputText ? (
            <span className="context-input-status">{emptyMessage}</span>
          ) : null}
        </div>
      </div>
    </div>
  );
}
