import type {
  ConversationDetail,
  ConversationMessage,
  ConversationRecord,
  ConversationStreamEvent,
  StartedMessageResponse
} from "../../api/client";
import { isConversationMessage } from "../../api/client";

type MessageUpdater = (message: ConversationMessage) => ConversationMessage;

type StreamingTurnDetailOptions = {
  response: StartedMessageResponse;
  currentDetail: ConversationDetail | null;
  rawText: string;
  contextResources: Array<Record<string, unknown>>;
  thinkingMode: string;
  untitledTitle: string;
  initialTitle: string;
};

function streamingAssistantMessage(
  response: StartedMessageResponse
): ConversationMessage {
  return {
    record_id: response.final_assistant_message_id,
    kind: "assistant",
    message_id: response.final_assistant_message_id,
    turn_id: response.turn_id,
    parent_message_id: response.assistant_parent_message_id ?? response.user_message_id,
    role: "assistant",
    model_id: response.model_id,
    content: "",
    status: "streaming",
    created_at: response.created_at
  };
}

function mergeStreamedMessages(
  currentDetail: ConversationDetail | null,
  baseMessages: ConversationMessage[],
  streamedMessages: ConversationMessage[],
) {
  const streamedIds = new Set(streamedMessages.map((message) => message.message_id));
  const baseMessageIds = new Set(baseMessages.map((message) => message.message_id));
  const baseTurnIds = new Set(baseMessages.map((message) => message.turn_id));
  const baseRecords = (currentDetail?.records ?? []).filter((record) =>
    isConversationMessage(record)
      ? baseMessageIds.has(record.message_id)
      : baseTurnIds.has(record.turn_id)
  );

  return {
    records: [
      ...baseRecords.filter(
        (record) => !isConversationMessage(record) || !streamedIds.has(record.message_id)
      ),
      ...streamedMessages
    ]
  };
}

function updateDetailMessages(
  detail: ConversationDetail | null,
  updateMessage: MessageUpdater
): ConversationDetail | null {
  if (!detail) {
    return detail;
  }

  return {
    ...detail,
    records: detail.records.map((record) =>
      isConversationMessage(record) ? updateMessage(record) : record
    )
  };
}

function completeStreamingTurnMessage(
  message: ConversationMessage,
  finalAssistantMessageId: string
): ConversationMessage {
  return message.message_id === finalAssistantMessageId
    ? {
      ...message,
      status: "completed"
    }
    : message;
}

function cancelStreamingTurnMessage(message: ConversationMessage, turnId: string): ConversationMessage {
  return message.turn_id === turnId && message.role === "assistant"
    ? {
      ...message,
      status: "cancelled"
    }
    : message;
}

export function buildStreamingTurnDetail({
  response,
  currentDetail,
  rawText,
  contextResources,
  thinkingMode,
  untitledTitle,
  initialTitle
}: StreamingTurnDetailOptions): ConversationDetail {
  const currentMessages = (currentDetail?.records ?? []).filter(isConversationMessage);
  const parentMessageId = [...currentMessages]
    .reverse()
    .find((message) => message.role === "assistant")?.message_id ?? null;
  const baseMessages = currentMessages;
  const streamingUser: ConversationMessage = {
    record_id: response.user_message_id,
    kind: "user",
    message_id: response.user_message_id,
    turn_id: response.turn_id,
    parent_message_id: parentMessageId ?? null,
    role: "user",
    model_id: response.model_id,
    thinking_mode: thinkingMode,
    content: rawText,
    context_resources: contextResources,
    created_at: response.created_at
  };
  const streamingAssistant = streamingAssistantMessage(response);
  const streamedMessages = [
    streamingUser,
    streamingAssistant
  ];

  return {
    session_id: response.session_id,
    member_id: response.member_id,
    member_name: response.member_name,
    access_state: "available",
    title: currentDetail?.title && currentDetail.title !== untitledTitle
      ? currentDetail.title
      : initialTitle,
    parent_session_id: currentDetail?.parent_session_id ?? null,
    seed_event_count: currentDetail?.seed_event_count ?? 0,
    fork_available: currentDetail?.fork_available ?? false,
    pending_turns: [],
    queued_inputs: currentDetail?.queued_inputs ?? [],
    resource_states: currentDetail?.resource_states ?? [],
    ...mergeStreamedMessages(currentDetail, baseMessages, streamedMessages)
  };
}

type RecordStartedData = Extract<
  ConversationStreamEvent,
  { event: "record_started" }
>["data"];
type RecordCompletedData = Extract<
  ConversationStreamEvent,
  { event: "record_completed" }
>["data"];

function insertStreamingRecord(
  records: ConversationRecord[],
  nextRecord: ConversationRecord
): ConversationRecord[] {
  const existingIndex = records.findIndex(
    (record) => (record.record_id ?? (isConversationMessage(record) ? record.message_id : "")) === nextRecord.record_id
  );
  if (existingIndex >= 0) {
    return records.map((record, index) =>
      index === existingIndex ? ({ ...record, ...nextRecord } as ConversationRecord) : record
    );
  }
  const assistantIndex = records.findIndex(
    (record) => isConversationMessage(record) &&
      record.turn_id === nextRecord.turn_id &&
      record.role === "assistant" &&
      record.status === "streaming"
  );
  if (assistantIndex < 0 || isConversationMessage(nextRecord) && nextRecord.role === "assistant") {
    return [...records, nextRecord];
  }
  return [
    ...records.slice(0, assistantIndex),
    nextRecord,
    ...records.slice(assistantIndex)
  ];
}

export function startStreamingRecordInDetail(
  detail: ConversationDetail | null,
  data: RecordStartedData
) {
  if (!detail) {
    return detail;
  }
  const nextRecord: ConversationRecord = { ...data };
  if (nextRecord.kind === "assistant") {
    const generated = [...detail.records].reverse().find((record) =>
      record.kind === "model" && record.channel === "content" &&
      record.turn_id === data.turn_id && record.purpose === "agent_action" &&
      !record.parent_tool_call_id && record.status === "completed"
    );
    if (generated?.kind === "model" && typeof generated.value === "string") {
      nextRecord.content = generated.value;
    }
  }
  const existing = detail.records.find((record) => record.record_id === data.record_id);
  if (existing && !(existing.kind === "assistant" && !existing.content && nextRecord.kind === "assistant" && nextRecord.content)) {
    return detail;
  }
  return {
    ...detail,
    records: insertStreamingRecord(detail.records, nextRecord)
  };
}

export function appendRecordDeltaToDetail(
  detail: ConversationDetail | null,
  recordId: string,
  delta: string,
  offset: number,
  channel?: "input" | "reasoning" | "content" | "raw_output" | "tool_request" | "result" | "name" | "arguments"
) {
  if (!detail || !delta) {
    return detail;
  }
  const update = (record: ConversationRecord): ConversationRecord => {
    const currentId = record.record_id ?? (isConversationMessage(record) ? record.message_id : "");
    if (
      currentId !== recordId ||
      (!isConversationMessage(record) && record.kind !== "model")
    ) {
      return record;
    }
    if (record.kind === "model") {
      if (record.channel === "tool_request" && channel === "name") {
        return {
          ...record,
          name: applyTextDelta(record.name ?? "", delta, offset),
          status: "streaming"
        };
      }
      if (record.channel === "tool_request" && channel === "arguments") {
        return {
          ...record,
          arguments: applyTextDelta(typeof record.arguments === "string" ? record.arguments : "", delta, offset),
          status: "streaming"
        };
      }
      return {
        ...record,
        value: applyTextDelta(typeof record.value === "string" ? record.value : "", delta, offset),
        status: "streaming"
      };
    }
    return { ...record, content: applyTextDelta(record.content ?? "", delta, offset), status: "streaming" };
  };
  return {
    ...detail,
    records: detail.records.map(update)
  };
}

export function applyTextDelta(current: string, delta: string, offset: number): string {
  if (offset < 0 || offset > current.length) {
    return current;
  }
  if (current.slice(offset, offset + delta.length) === delta) {
    return current;
  }
  return current.slice(0, offset) + delta;
}

export function completeStreamingRecordInDetail(
  detail: ConversationDetail | null,
  data: RecordCompletedData
) {
  if (!detail) {
    return detail;
  }
  const update = (record: ConversationRecord): ConversationRecord => {
    const currentId = record.record_id ?? (isConversationMessage(record) ? record.message_id : "");
    if (currentId !== data.record_id) {
      return record;
    }
    if (isConversationMessage(record)) {
      return {
        ...record,
        content: typeof data.content === "string" ? data.content : record.content,
        stop_reason: data.stop_reason ?? record.stop_reason,
        status: data.status ?? "completed",
        duration_ms: data.duration_ms ?? record.duration_ms
      };
    }
    if (record.kind === "context") {
      return {
        ...record,
        content: data.content ?? record.content,
        estimated_tokens_before: data.estimated_tokens_before ?? record.estimated_tokens_before,
        estimated_tokens_after: data.estimated_tokens_after ?? record.estimated_tokens_after,
        target_tokens: data.target_tokens ?? record.target_tokens,
        error: data.error ?? record.error,
        status: data.status ?? "completed",
        duration_ms: data.duration_ms ?? record.duration_ms
      };
    }
    if (record.kind === "model") {
      return {
        ...record,
        channel: data.channel ?? record.channel,
        value: data.value ?? data.content ?? record.value,
        context_window_tokens: data.context_window_tokens ?? record.context_window_tokens,
        tool_call_id: data.tool_call_id ?? record.tool_call_id,
        name: data.name ?? record.name,
        arguments: data.arguments ?? record.arguments,
        usage: data.usage ?? record.usage,
        stop_reason: data.stop_reason ?? record.stop_reason,
        status: data.status ?? "completed",
        error: data.error ?? record.error,
        duration_ms: data.duration_ms ?? record.duration_ms
      };
    }
    if (record.kind === "observation") {
      return {
        ...record,
        observation: data.observation ?? data.content ?? record.observation,
        status: data.status ?? "completed",
        error: data.error ?? record.error,
        duration_ms: data.duration_ms ?? record.duration_ms
      };
    }
    if (record.kind === "error") {
      return {
        ...record,
        status: "failed",
        error: data.error ?? record.error,
        duration_ms: data.duration_ms ?? record.duration_ms
      };
    }
    return {
      ...record,
      result: data.result ?? record.result,
      status: data.status ?? "completed",
      error: data.error ?? record.error,
      duration_ms: data.duration_ms ?? record.duration_ms
    };
  };
  return {
    ...detail,
    records: detail.records.map(update)
  };
}

export function completeStreamingTurnInDetail(
  detail: ConversationDetail | null,
  finalAssistantMessageId: string
) {
  return updateDetailMessages(detail, (message) => completeStreamingTurnMessage(message, finalAssistantMessageId));
}

export function cancelStreamingTurnInDetail(detail: ConversationDetail | null, turnId: string) {
  const updatedDetail = updateDetailMessages(detail, (message) => cancelStreamingTurnMessage(message, turnId));

  return updatedDetail
    ? {
      ...updatedDetail,
      pending_turns: updatedDetail.pending_turns.filter((turn) => turn["turn_id"] !== turnId)
    }
    : updatedDetail;
}
