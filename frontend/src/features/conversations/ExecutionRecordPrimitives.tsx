import {
  useEffect,
  useMemo,
  useRef
} from "react";
import type {
  ConversationContextRecord
} from "../../api/client";
import {
  ChevronRightIcon
} from "../../components/icons";

export function TraceChevron() {
  return <ChevronRightIcon className="turn-trace-chevron" />;
}

export function RootTraceChevron() {
  return <ChevronRightIcon className="turn-trace-chevron" />;
}

export function TraceItemSeparator() {
  return <span aria-hidden="true" className="turn-trace-item-separator">·</span>;
}

export function firstVisibleLine(text: string) {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .find(Boolean) ?? "";
}

function latestVisibleLine(text: string) {
  const lines = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  return lines.at(-1) ?? "";
}

export function LiveDisclosurePreview({
  fallback,
  followLatest = false,
  streaming,
  text
}: {
  fallback: string;
  followLatest?: boolean;
  streaming: boolean;
  text: string;
}) {
  const previewRef = useRef<HTMLSpanElement>(null);
  const followsEnd = streaming || followLatest;
  const preview = (followsEnd ? latestVisibleLine(text) : firstVisibleLine(text)) || fallback;

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      const element = previewRef.current;
      if (!element) {
        return;
      }
      element.scrollLeft = followsEnd ? element.scrollWidth - element.clientWidth : 0;
    });
    return () => window.cancelAnimationFrame(frame);
  }, [followsEnd, preview]);

  return (
    <>
      <TraceItemSeparator />
      <span
        className="turn-trace-item-preview"
        data-follow-end={followsEnd ? "true" : undefined}
        ref={previewRef}
      >
        {preview}
      </span>
    </>
  );
}

function formatRecordValue(value: unknown) {
  if (typeof value === "string") {
    return value;
  }
  if (value === undefined) {
    return "—";
  }
  const serialized = JSON.stringify(value, null, 2);
  return serialized ?? String(value);
}

export function conversationTurnFailureMessage(error: unknown) {
  if (typeof error === "string") {
    return error;
  }
  if (error && typeof error === "object") {
    const message = (error as Record<string, unknown>).message;
    if (typeof message === "string") {
      return message;
    }
  }
  return formatRecordValue(error);
}

export function FormattedRecordValue({ value }: { value: unknown }) {
  const formatted = useMemo(() => formatRecordValue(value), [value]);
  return <pre>{formatted}</pre>;
}

export function previewRecordValue(value: unknown) {
  if (typeof value === "string") {
    return value;
  }
  if (value === null || value === undefined) {
    return "";
  }
  return JSON.stringify(value) ?? String(value);
}

export function providerSourceLabel(record: ConversationContextRecord) {
  const source = record.provider_source;
  if (!source) {
    return null;
  }
  const range = source.start !== undefined && source.end !== undefined
    ? ` [${source.start}, ${source.end})`
    : "";
  return `provider_payload${source.path}${range}`;
}
