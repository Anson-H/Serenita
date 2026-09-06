import {
  memo,
  useEffect,
  useRef,
  useState
} from "react";
import type {
  ConversationModelRecord
} from "../../api/client";
import {
  recordStartedAtMs
} from "./conversationTurns";
import { formatThinkingDuration, liveModelRecordDurationMs } from "./thinking";

const LIVE_DURATION_REFRESH_MS = 50;

export const ModelRecordDurationLabel = memo(function ModelRecordDurationLabel({
  record
}: {
  record: ConversationModelRecord;
}) {
  const persistedDurationMs = Math.max(0, Number(record.duration_ms) || 0);
  const startedAtMs = recordStartedAtMs(record);
  const streaming = record.status === "streaming" || record.status === "running";
  const fallbackStartedAtRef = useRef(Date.now() - persistedDurationMs);
  const recordIdRef = useRef(record.record_id);
  const [durationLabel, setDurationLabel] = useState(() => formatThinkingDuration(
    streaming
      ? liveModelRecordDurationMs(
        Date.now(),
        persistedDurationMs,
        startedAtMs,
        fallbackStartedAtRef.current
      )
      : persistedDurationMs
  ));

  useEffect(() => {
    if (recordIdRef.current !== record.record_id) {
      recordIdRef.current = record.record_id;
      fallbackStartedAtRef.current = Date.now() - persistedDurationMs;
    }
    const update = () => {
      const durationMs = streaming
        ? liveModelRecordDurationMs(
          Date.now(),
          persistedDurationMs,
          startedAtMs,
          fallbackStartedAtRef.current
        )
        : persistedDurationMs;
      const nextLabel = formatThinkingDuration(durationMs);
      setDurationLabel((currentLabel) => currentLabel === nextLabel ? currentLabel : nextLabel);
    };
    update();
    if (!streaming) {
      return;
    }
    const timer = window.setInterval(update, LIVE_DURATION_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [persistedDurationMs, record.record_id, startedAtMs, streaming]);

  return (
    <span
      aria-label={`用时 ${durationLabel}`}
      className="turn-trace-item-meta model-record-duration"
      data-live={streaming ? "true" : undefined}
    >
      用时 {durationLabel}
    </span>
  );
});

function liveTurnDurationMs(
  nowMs: number,
  persistedDurationMs: number,
  persistedStartedAtMs: number | null,
  fallbackStartedAtMs: number
) {
  const liveDurationMs = persistedStartedAtMs === null
    ? nowMs - fallbackStartedAtMs
    : nowMs - persistedStartedAtMs;
  return Math.max(100, persistedDurationMs, liveDurationMs);
}

function ActiveTurnDurationLabel({
  activeTurnId,
  persistedDurationMs,
  persistedStartedAtMs
}: {
  activeTurnId: string | null;
  persistedDurationMs: number;
  persistedStartedAtMs: number | null;
}) {
  const fallbackStartedAtRef = useRef(Date.now() - persistedDurationMs);
  const fallbackTurnIdRef = useRef(activeTurnId);
  const [durationLabel, setDurationLabel] = useState(() => formatThinkingDuration(
    liveTurnDurationMs(
      Date.now(),
      persistedDurationMs,
      persistedStartedAtMs,
      fallbackStartedAtRef.current
    )
  ));

  useEffect(() => {
    if (fallbackTurnIdRef.current !== activeTurnId) {
      fallbackTurnIdRef.current = activeTurnId;
      fallbackStartedAtRef.current = Date.now() - persistedDurationMs;
    }
    const update = () => {
      const nextLabel = formatThinkingDuration(liveTurnDurationMs(
        Date.now(),
        persistedDurationMs,
        persistedStartedAtMs,
        fallbackStartedAtRef.current
      ));
      setDurationLabel((currentLabel) => currentLabel === nextLabel ? currentLabel : nextLabel);
    };
    update();
    const timer = window.setInterval(update, LIVE_DURATION_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [activeTurnId, persistedDurationMs, persistedStartedAtMs]);

  return <span className="turn-execution-title">用时 {durationLabel}</span>;
}

export const TurnDurationLabel = memo(function TurnDurationLabel({
  active,
  activeTurnId,
  persistedDurationMs,
  persistedStartedAtMs
}: {
  active: boolean;
  activeTurnId: string | null;
  persistedDurationMs: number;
  persistedStartedAtMs: number | null;
}) {
  if (!active) {
    return (
      <span className="turn-execution-title">
        用时 {formatThinkingDuration(persistedDurationMs)}
      </span>
    );
  }
  return (
    <ActiveTurnDurationLabel
      activeTurnId={activeTurnId}
      persistedDurationMs={persistedDurationMs}
      persistedStartedAtMs={persistedStartedAtMs}
    />
  );
});
