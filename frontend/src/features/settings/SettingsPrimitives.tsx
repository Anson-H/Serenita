import { NavigationTitle } from "../../components/NavigationTitle";
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ComponentProps,
  type ReactNode
} from "react";

import { ChevronRightIcon } from "../../components/icons";

function useSettledLayoutMeasurement(measure: () => void) {
  const firstFrameRef = useRef<number | null>(null);
  const secondFrameRef = useRef<number | null>(null);
  const cancelScheduledMeasurement = useCallback(() => {
    if (firstFrameRef.current !== null) {
      window.cancelAnimationFrame(firstFrameRef.current);
      firstFrameRef.current = null;
    }
    if (secondFrameRef.current !== null) {
      window.cancelAnimationFrame(secondFrameRef.current);
      secondFrameRef.current = null;
    }
  }, []);
  const scheduleMeasurement = useCallback(() => {
    cancelScheduledMeasurement();
    measure();
    firstFrameRef.current = window.requestAnimationFrame(() => {
      firstFrameRef.current = null;
      measure();
      secondFrameRef.current = window.requestAnimationFrame(() => {
        secondFrameRef.current = null;
        measure();
      });
    });
  }, [cancelScheduledMeasurement, measure]);

  useEffect(() => cancelScheduledMeasurement, [cancelScheduledMeasurement]);

  return scheduleMeasurement;
}

function observeElementWidths(elements: Array<Element | null>, onWidthChange: () => void) {
  if (typeof ResizeObserver === "undefined") return () => undefined;
  const observedWidths = new Map<Element, number>();
  const observer = new ResizeObserver((entries) => {
    let widthChanged = false;
    entries.forEach((entry) => {
      const previousWidth = observedWidths.get(entry.target);
      const nextWidth = entry.contentRect.width;
      observedWidths.set(entry.target, nextWidth);
      if (previousWidth !== undefined && Math.abs(previousWidth - nextWidth) > 0.5) {
        widthChanged = true;
      }
    });
    if (widthChanged) onWidthChange();
  });
  elements.filter((element): element is Element => Boolean(element)).forEach((element) => {
    observedWidths.set(element, element.getBoundingClientRect().width);
    observer.observe(element);
  });
  return () => observer.disconnect();
}

export function SettingsListForwardIcon({ className = "" }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={["navigation-forward-icon", className].filter(Boolean).join(" ")}
    >
      <ChevronRightIcon />
    </span>
  );
}

export function SettingsTrailingSummary({
  children,
  className = "",
  title
}: {
  children: ReactNode;
  className?: string;
  title?: string;
}) {
  const summaryRef = useRef<HTMLElement | null>(null);
  const [wrapped, setWrapped] = useState(false);
  const measureWrapping = useCallback(() => {
    const summary = summaryRef.current;
    if (!summary) return;
    const lineHeight = Number.parseFloat(window.getComputedStyle(summary).lineHeight);
    const nextWrapped = Number.isFinite(lineHeight)
      && summary.getBoundingClientRect().height > lineHeight + 0.5;
    setWrapped((current) => current === nextWrapped ? current : nextWrapped);
  }, []);
  const scheduleMeasurement = useSettledLayoutMeasurement(measureWrapping);

  useLayoutEffect(() => {
    scheduleMeasurement();
  }, [children, scheduleMeasurement]);

  useEffect(() => {
    const summary = summaryRef.current;
    if (!summary) return;
    return observeElementWidths(
      [summary, summary.parentElement, summary.parentElement?.parentElement ?? null],
      scheduleMeasurement
    );
  }, [scheduleMeasurement]);

  return (
    <small
      className={["grouped-list-trailing-summary", className].filter(Boolean).join(" ")}
      data-wrapped={wrapped ? "true" : undefined}
      ref={summaryRef}
      title={title}
    >
      {children}
    </small>
  );
}

export function SettingsListPanel({
  bodyClassName = "",
  children,
  className = "",
  footer,
  title,
  titleId
}: {
  bodyClassName?: string;
  children: ReactNode;
  className?: string;
  footer?: ReactNode;
  title: string;
  titleId: string;
}) {
  return (
    <aside
      aria-labelledby={titleId}
      className={["settings-list-column", className].filter(Boolean).join(" ")}
    >
      <header className="settings-list-header">
        <NavigationTitle id={titleId} title={title} />
      </header>
      <div className={["settings-list-body", "scroll-content", "content-column", bodyClassName].filter(Boolean).join(" ")}>
        {children}
      </div>
      {footer}
    </aside>
  );
}

type SettingsAutoGrowingTextareaProps = Omit<
  ComponentProps<"textarea">,
  "ref" | "rows"
>;

function resizeSettingsTextarea(textarea: HTMLTextAreaElement) {
  textarea.style.height = "auto";
  const computedStyle = window.getComputedStyle(textarea);
  const rawScrollHeight = textarea.scrollHeight;
  const lineHeight = Number.parseFloat(computedStyle.lineHeight);
  const paddingTop = Number.parseFloat(computedStyle.paddingTop);
  const paddingBottom = Number.parseFloat(computedStyle.paddingBottom);
  const hasStableLineMetrics = [lineHeight, paddingTop, paddingBottom].every(Number.isFinite);
  const renderedLineCount = hasStableLineMetrics
    ? Math.max(
      1,
      Math.round((rawScrollHeight - paddingTop - paddingBottom) / lineHeight)
    )
    : 1;
  const naturalHeight = hasStableLineMetrics
    ? renderedLineCount * lineHeight + paddingTop + paddingBottom
    : rawScrollHeight;
  const computedMaxHeight = Number.parseFloat(computedStyle.maxHeight);
  const maxHeight = Number.isFinite(computedMaxHeight)
    ? computedMaxHeight
    : naturalHeight;
  const nextHeight = Math.min(naturalHeight, maxHeight);
  textarea.style.height = `${nextHeight}px`;
  textarea.style.overflowY = naturalHeight > nextHeight ? "auto" : "hidden";
  return hasStableLineMetrics && renderedLineCount > 1;
}

function SettingsAutoGrowingTextarea({
  className = "",
  value,
  ...props
}: SettingsAutoGrowingTextareaProps) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const [multiline, setMultiline] = useState(false);
  const resize = useCallback(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    const nextMultiline = resizeSettingsTextarea(textarea);
    setMultiline((current) => current === nextMultiline ? current : nextMultiline);
  }, []);
  const scheduleResize = useSettledLayoutMeasurement(resize);

  useLayoutEffect(() => {
    scheduleResize();
  }, [scheduleResize, value]);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    return observeElementWidths(
      [textarea, textarea.parentElement, textarea.parentElement?.parentElement ?? null],
      scheduleResize
    );
  }, [scheduleResize]);

  return (
    <textarea
      {...props}
      className={["auto-growing-text-control", className].filter(Boolean).join(" ")}
      data-multiline={multiline ? "true" : undefined}
      ref={textareaRef}
      rows={1}
      value={value}
    />
  );
}

export function SettingsLongTextField({
  label,
  ...props
}: SettingsAutoGrowingTextareaProps & { label: string }) {
  return (
    <label className="field-row long-text-field-row">
      <span className="field-label">{label}</span>
      <SettingsAutoGrowingTextarea {...props} />
    </label>
  );
}

export function SettingsControlRow({
  control,
  label,
  layout = "row"
}: {
  control: ReactNode;
  label: string;
  layout?: "field" | "row";
}) {
  return (
    <div className={`settings-control-row field-row ${layout === "field" ? "settings-control-field" : ""}`.trim()}>
      <span className="field-control-label">{label}</span>
      {control}
    </div>
  );
}

