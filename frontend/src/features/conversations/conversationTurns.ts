import type {
  ConversationAssistantRecord,
  ConversationContextRecord,
  ConversationErrorRecord,
  ConversationModelRecord,
  ConversationObservationRecord,
  ConversationRecord,
  ConversationToolRecord,
  ConversationUserRecord
} from "../../api/client";

export type ConversationExecutionRecord =
  | ConversationContextRecord
  | ConversationErrorRecord
  | ConversationModelRecord
  | ConversationObservationRecord
  | ConversationToolRecord;

export type ConversationTurnGroup = {
  key: string;
  records: ConversationRecord[];
  userRecords: ConversationUserRecord[];
  executionRecords: ConversationExecutionRecord[];
  assistantRecords: ConversationAssistantRecord[];
  turnIds: string[];
};

type MutableConversationTurnGroup = ConversationTurnGroup & {
  turnIdSet: Set<string>;
};

function newTurnGroup(record: ConversationRecord): MutableConversationTurnGroup {
  return {
    key: record.kind === "user" ? record.message_id : `turn-${record.turn_id}-${record.record_id}`,
    records: [],
    userRecords: [],
    executionRecords: [],
    assistantRecords: [],
    turnIds: [],
    turnIdSet: new Set()
  };
}

function appendRecord(group: MutableConversationTurnGroup, record: ConversationRecord) {
  group.records.push(record);
  if (!group.turnIdSet.has(record.turn_id)) {
    group.turnIdSet.add(record.turn_id);
    group.turnIds.push(record.turn_id);
  }
  if (record.kind === "user") {
    group.userRecords.push(record);
  } else if (record.kind === "assistant") {
    group.assistantRecords.push(record);
  } else {
    group.executionRecords.push(record);
  }
}

/**
 * Active-path records are already in conversational order. A user record opens
 * one visible turn. This intentionally groups regenerated assistant records
 * with the original question even though regeneration receives a fresh turn_id.
 */
export function groupConversationRecordsByTurn(records: ConversationRecord[]) {
  const groups: MutableConversationTurnGroup[] = [];
  let current: MutableConversationTurnGroup | null = null;

  for (const record of records) {
    if (record.kind === "user") {
      current = newTurnGroup(record);
      groups.push(current);
    } else if (!current) {
      current = newTurnGroup(record);
      groups.push(current);
    }
    appendRecord(current, record);
  }

  return groups.map(({ turnIdSet: _turnIdSet, ...group }) => group);
}

export function terminalModelContentRecordId(
  records: readonly ConversationExecutionRecord[]
): string | null {
  const completedModelCallIds = new Set(
    records
      .filter(
        (record): record is ConversationModelRecord =>
          record.kind === "model" &&
          record.channel === "result" &&
          record.status === "completed" &&
          !record.error
      )
      .map((record) => record.call_id)
  );
  const modelToolRequestCallIds = new Set(
    records
      .filter(
        (record): record is ConversationModelRecord =>
          record.kind === "model" && record.channel === "tool_request"
      )
      .map((record) => record.call_id)
  );

  for (let index = records.length - 1;index >= 0;index -= 1) {
    const record = records[index];
    if (
      record.kind === "model" &&
      record.channel === "content" &&
      record.purpose !== "context_compaction" &&
      completedModelCallIds.has(record.call_id) &&
      !modelToolRequestCallIds.has(record.call_id)
    ) {
      return record.record_id;
    }
  }
  return null;
}

export function completedTurnDurationMs(records: ConversationRecord[]) {
  const projectedDurations = records
    .map((record) => record.turn_duration_ms)
    .filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  if (projectedDurations.length) {
    return Math.max(...projectedDurations, 0);
  }

  const executionTimes = records
    .filter((record) => record.kind !== "user")
    .map((record) => record.time)
    .filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  if (executionTimes.length > 1) {
    return Math.max(...executionTimes) - Math.min(...executionTimes);
  }

  return Math.max(
    0,
    ...records.map((record) => Number(record.duration_ms) || 0)
  );
}

export function recordStartedAtMs(record: ConversationRecord) {
  if (typeof record.time === "number" && Number.isFinite(record.time)) {
    return record.time;
  }
  if (typeof record.created_at === "string" && record.created_at.trim()) {
    const parsed = Date.parse(record.created_at);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return null;
}

export function activeTurnStartedAtMs(
  records: ConversationRecord[],
  activeTurnId: string | null
) {
  if (!activeTurnId) {
    return null;
  }
  return records
    .filter((record) => record.turn_id === activeTurnId && record.kind !== "user")
    .map(recordStartedAtMs)
    .filter((value): value is number => value !== null)
    .reduce<number | null>(
      (earliest, value) => earliest === null ? value : Math.min(earliest, value),
      null
    );
}
