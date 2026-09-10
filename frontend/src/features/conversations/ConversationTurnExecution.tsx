import {
  useMemo
} from "react";
import type {
  ConversationErrorRecord,
  ConversationRecord
} from "../../api/client";
import { isBaseContextAssemblyType } from "../accountPreferences/contextAssemblyDisplay";
import type { ToolExecutionDisplayType } from "../accountPreferences/toolExecutionDisplay";
import {
  isCompactionStatus
} from "./contextCompactionDisplay";
import {
  activeTurnStartedAtMs,
  completedTurnDurationMs,
  terminalModelContentRecordId,
  type ConversationExecutionRecord
} from "./conversationTurns";
import { TurnDurationLabel } from "./ExecutionDuration";
import { CompactionStatusRecord, ContextRecordDetails, ModelContentRecord, ModelRecordDetails, ObservationRecord, OperationRecord, TurnErrorRecord } from "./ExecutionRecordDetails";
import { RootTraceChevron } from "./ExecutionRecordPrimitives";
import { formatThinkingDuration } from "./thinking";
import {
  mergedTextToolRawOutputCallIds,
  modelReadableToolResultContent
} from "./toolTracePresentation";
import { useTurnExecutionDisclosure } from "./useExecutionDisclosure";

function isVisibleExecutionRecord(
  record: ConversationExecutionRecord,
  visibleBaseContextRecordIds: ReadonlySet<string>,
  visibleContextTypes: ReadonlySet<string>,
  visibleToolTypes: ReadonlySet<ToolExecutionDisplayType>,
  mergedRawOutputCallIds: ReadonlySet<string>
) {
  if (record.kind === "model") {
    if (record.purpose === "context_compaction") return false;
    return (
      record.channel !== "input" &&
      record.channel !== "result" &&
      !(record.channel === "raw_output" && mergedRawOutputCallIds.has(record.call_id)) &&
      (record.channel !== "tool_request" || visibleToolTypes.has("model_tool_request"))
    );
  }
  if (record.kind === "context") {
    if (isCompactionStatus(record)) return true;
    return isBaseContextAssemblyType(record.context_type)
      ? visibleBaseContextRecordIds.has(record.record_id)
      : visibleContextTypes.has(record.context_type);
  }
  if (record.kind === "tool") {
    return visibleToolTypes.has("tool_call");
  }
  return true;
}

export function ConversationTurnExecution({
  active,
  activeTurnId,
  highlightedMessageId,
  onRegisterMessageElement,
  records,
  turnRecords,
  showModelIdentity,
  visibleBaseContextRecordIds,
  visibleContextTypes,
  visibleToolTypes
}: {
  active: boolean;
  activeTurnId: string | null;
  highlightedMessageId: string | null;
  onRegisterMessageElement: (messageId: string, node: HTMLElement | null) => void;
  records: ConversationExecutionRecord[];
  turnRecords: ConversationRecord[];
  showModelIdentity: boolean;
  visibleBaseContextRecordIds: ReadonlySet<string>;
  visibleContextTypes: ReadonlySet<string>;
  visibleToolTypes: ReadonlySet<ToolExecutionDisplayType>;
}) {
  const activeTurnRecords = useMemo(
    () => activeTurnId
      ? turnRecords.filter((record) => record.turn_id === activeTurnId)
      : turnRecords,
    [activeTurnId, turnRecords]
  );
  const persistedDurationMs = useMemo(
    () => completedTurnDurationMs(activeTurnRecords),
    [activeTurnRecords]
  );
  const persistedStartedAtMs = useMemo(
    () => activeTurnStartedAtMs(turnRecords, activeTurnId),
    [activeTurnId, turnRecords]
  );
  const mergedRawOutputCallIds = useMemo(
    () => mergedTextToolRawOutputCallIds(records),
    [records]
  );
  const visibleRecords = useMemo(
    () => records.filter((record) =>
      record.record_id === highlightedMessageId ||
      isVisibleExecutionRecord(
        record,
        visibleBaseContextRecordIds,
        visibleContextTypes,
        visibleToolTypes,
        mergedRawOutputCallIds
      )
    ),
    [
      highlightedMessageId,
      mergedRawOutputCallIds,
      records,
      visibleBaseContextRecordIds,
      visibleContextTypes,
      visibleToolTypes
    ]
  );
  const failureRecords = useMemo(
    () => visibleRecords.filter(
      (record): record is ConversationErrorRecord => record.kind === "error"
    ),
    [visibleRecords]
  );
  const finalAssistantModelRecordId = useMemo(
    () => terminalModelContentRecordId(records),
    [records]
  );
  const traceRecords = useMemo(
    () => visibleRecords.filter(
      (record) => record.kind !== "error" && record.record_id !== finalAssistantModelRecordId
    ),
    [finalAssistantModelRecordId, visibleRecords]
  );
  const highlightedTraceRequested = useMemo(
    () => Boolean(
      highlightedMessageId &&
      traceRecords.some((record) => record.record_id === highlightedMessageId)
    ),
    [highlightedMessageId, traceRecords]
  );
  const { bodyMounted, onToggle, open } = useTurnExecutionDisclosure(
    active,
    highlightedTraceRequested
  );
  const summaryAriaLabel = active
    ? "本轮执行过程，当前仍在执行"
    : `本轮执行过程，用时 ${formatThinkingDuration(persistedDurationMs)}`;
  return (
    <>
      {active || traceRecords.length ? (
        <details
          className="turn-execution"
          data-active={active ? "true" : undefined}
          onToggle={onToggle}
          open={open}
        >
          <summary
            aria-label={summaryAriaLabel}
          >
            <TurnDurationLabel
              active={active}
              activeTurnId={activeTurnId}
              persistedDurationMs={persistedDurationMs}
              persistedStartedAtMs={persistedStartedAtMs}
            />
            <RootTraceChevron />
          </summary>
          {bodyMounted ? <div className="turn-execution-body" aria-label="本轮执行过程">
            {traceRecords.map((record) => {
              if (record.kind === "model") {
                if (record.purpose === "context_compaction") return null;
                if (record.channel === "content") {
                  return (
                    <ModelContentRecord
                      showModelIdentity={showModelIdentity}
                      highlighted={highlightedMessageId === record.record_id}
                      key={record.record_id}
                      onRegister={onRegisterMessageElement}
                      record={record}
                    />
                  );
                }
                return (
                  <ModelRecordDetails
                      showModelIdentity={showModelIdentity}
                    highlighted={highlightedMessageId === record.record_id}
                    key={record.record_id}
                    onRegister={onRegisterMessageElement}
                    record={record}
                  />
                );
              }
              if (record.kind === "context") {
                if (isCompactionStatus(record)) {
                  return <CompactionStatusRecord
                    highlighted={highlightedMessageId === record.record_id}
                    key={record.record_id}
                    onRegister={onRegisterMessageElement}
                    record={record}
                    records={records}
                  />;
                }
                return (
                  <ContextRecordDetails
                    highlighted={highlightedMessageId === record.record_id}
                    key={record.record_id}
                    onRegister={onRegisterMessageElement}
                    record={record}
                  />
                );
              }
              if (record.kind === "observation") {
                return (
                  <ObservationRecord
                    highlighted={highlightedMessageId === record.record_id}
                    key={record.record_id}
                    onRegister={onRegisterMessageElement}
                    record={record}
                  />
                );
              }
              if (record.kind === "error") {
                return null;
              }
              return (
                <OperationRecord
                  highlighted={highlightedMessageId === record.record_id}
                  key={record.record_id}
                  modelReadableContent={modelReadableToolResultContent(record, records)}
                  onRegister={onRegisterMessageElement}
                  record={record}
                />
              );
            })}
          </div> : null}
        </details>
      ) : null}
      {failureRecords.map((record) => (
        <TurnErrorRecord
          highlighted={highlightedMessageId === record.record_id}
          key={record.record_id}
          onRegister={onRegisterMessageElement}
          record={record}
        />
      ))}
    </>
  );
}
