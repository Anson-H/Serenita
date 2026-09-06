type ToolRequestRecord = {
  kind: "model";
  channel: string;
  call_id: string;
  transport_mode?: "native" | "text_tool";
};

type ToolResultRecord = {
  kind: "tool";
  tool_call_id?: string;
  error?: unknown;
  result: unknown;
};

type ContextRecord = {
  kind: "context";
  context_type: string;
  content: unknown;
};

type TraceRecord = ToolRequestRecord | ToolResultRecord | ContextRecord | {
  kind: string;
  [key: string]: unknown;
};

const TEXT_TOOL_OBSERVATION_PREFIX = "TOOL_OBSERVATION\n";

function compactJson(value: unknown) {
  const serialized = JSON.stringify(value);
  return serialized ?? String(value);
}

function readableObservationFromContext(content: unknown) {
  if (!content || typeof content !== "object" || Array.isArray(content)) {
    return null;
  }
  const message = content as Record<string, unknown>;
  if (message.role === "tool") {
    return {
      toolCallId: String(message.tool_call_id ?? ""),
      content: typeof message.content === "string"
        ? message.content
        : compactJson(message.content)
    };
  }
  if (
    message.role !== "user" ||
    typeof message.content !== "string" ||
    !message.content.startsWith(TEXT_TOOL_OBSERVATION_PREFIX)
  ) {
    return null;
  }
  try {
    const envelope = JSON.parse(
      message.content.slice(TEXT_TOOL_OBSERVATION_PREFIX.length)
    ) as Record<string, unknown>;
    return {
      toolCallId: String(envelope.tool_call_id ?? ""),
      content: message.content
    };
  } catch {
    return null;
  }
}

/** Raw text-tool output is merged into its Tool Request row, not duplicated. */
export function mergedTextToolRawOutputCallIds(records: readonly TraceRecord[]) {
  return new Set(
    records
      .filter((record): record is ToolRequestRecord => (
        record.kind === "model" &&
        record.channel === "tool_request" &&
        record.transport_mode === "text_tool"
      ))
      .map((record) => record.call_id)
  );
}

/**
 * Prefer the exact content slice from the next persisted provider payload.
 * Native routing metadata stays hidden; readable text-protocol envelopes stay
 * visible because they are part of the model's actual input text.
 */
export function modelReadableToolResultContent(
  record: ToolResultRecord,
  records: readonly TraceRecord[]
) {
  const recordIndex = records.indexOf(record);
  const following = recordIndex >= 0 ? records.slice(recordIndex + 1) : records;
  for (const candidate of following) {
    if (candidate.kind !== "context" || candidate.context_type !== "tool_observation") {
      continue;
    }
    const observation = readableObservationFromContext(candidate.content);
    if (observation?.toolCallId === String(record.tool_call_id ?? "")) {
      return observation.content;
    }
  }
  const logicalContent = record.error !== undefined && record.error !== null
    ? { error: record.error }
    : record.result;
  return typeof logicalContent === "string"
    ? logicalContent
    : compactJson(logicalContent);
}
