

export type ConversationSummary = {
  member_id: string | null;
  member_name: string | null;
  access_state: "available" | "history_only";
  session_id: string;
  title: string;
  created_at: string;
  last_active_at: string;
  parent_session_id: string | null;
  seed_event_count: number;
  is_pinned: boolean;
  pending_turn_status: "queued" | "streaming" | null;
  queued_input_count: number;
  fork_available: boolean;
};

type ConversationMessageBase = {
  record_id: string;
  message_id: string;
  turn_id: string;
  parent_message_id: string | null;
  model_id?: string | null;
  duration_ms?: number;
  turn_duration_ms?: number;
  content: string;
  context_resources?: Array<Record<string, unknown>>;
  stop_reason?: string | null;
  status?: string;
  created_at: string;
  time?: number;
  source_event_seqs?: number[];
};

export type ConversationUserRecord = ConversationMessageBase & {
  kind: "user";
  role: "user";
  thinking_mode?: string;
  editable?: boolean;
};

export type ConversationAssistantRecord = ConversationMessageBase & {
  kind: "assistant";
  role: "assistant";
  regenerable?: boolean;
  fork_anchor_seq?: number | null;
};

export type ConversationMessage =
  | ConversationUserRecord
  | ConversationAssistantRecord;

export type ConversationToolRecord = {
  record_id: string;
  kind: "tool";
  turn_id: string;
  call_id: string;
  tool_call_id?: string;
  step?: number;
  name: string;
  arguments: unknown;
  result: unknown;
  status: string;
  error?: unknown;
  duration_ms?: number;
  turn_duration_ms?: number;
  created_at?: string;
  time?: number;
  source_event_seqs: number[];
};

export type ConversationObservationRecord = {
  record_id: string;
  kind: "observation";
  turn_id: string;
  call_id?: string | null;
  step?: number;
  observation: unknown;
  status: string;
  error?: unknown;
  duration_ms?: number;
  turn_duration_ms?: number;
  created_at?: string;
  time?: number;
  source_event_seqs: number[];
};

type ConversationModelChannel =
  | "input"
  | "reasoning"
  | "content"
  | "raw_output"
  | "tool_request"
  | "result";

export type ConversationModelRecord = {
  record_id: string;
  kind: "model";
  channel: ConversationModelChannel;
  turn_id: string;
  call_id: string;
  purpose?: string;
  summary_kind?: "history" | "turn_prefix" | null;
  step?: number;
  model_id?: string | null;
  context_window_tokens?: number | null;
  transport_mode?: "native" | "text_tool";
  parent_tool_call_id?: string | null;
  tool_call_id?: string | null;
  provider_index?: number;
  name?: string;
  arguments?: unknown;
  value: unknown;
  usage?: Record<string, unknown>;
  stop_reason?: string | null;
  status: string;
  error?: unknown;
  duration_ms?: number;
  turn_duration_ms?: number;
  created_at?: string;
  time?: number;
  source_event_seqs: number[];
};

export type ConversationContextRecord = {
  record_id: string;
  kind: "context";
  turn_id: string;
  call_id: string;
  context_id: string;
  context_type: string;
  label: string;
  purpose?: string;
  step?: number;
  transport_mode?: "native" | "text_tool";
  parent_tool_call_id?: string | null;
  provider_source?: {
    path: string;
    start?: number;
    end?: number;
  };
  content: unknown;
  estimated_tokens_before?: number;
  estimated_tokens_after?: number;
  target_tokens?: number;
  error?: unknown;
  status: string;
  duration_ms?: number;
  turn_duration_ms?: number;
  created_at?: string;
  time?: number;
  source_event_seqs: number[];
};

export type ConversationErrorRecord = {
  record_id: string;
  kind: "error";
  turn_id: string;
  status: "failed";
  error: unknown;
  duration_ms?: number;
  turn_duration_ms?: number;
  created_at?: string;
  time?: number;
  source_event_seqs: number[];
};

export type ConversationRecord =
  | ConversationMessage
  | ConversationErrorRecord
  | ConversationModelRecord
  | ConversationContextRecord
  | ConversationObservationRecord
  | ConversationToolRecord;

export function isConversationMessage(record: ConversationRecord): record is ConversationMessage {
  return record.kind === "user" || record.kind === "assistant";
}

type PendingConversationTurn = {
  turn_id: string;
  status: string;
  stream_id: string;
  user_message_id: string;
  final_assistant_message_id: string;
  created_at: string;
  updated_at: string;
};

export type ConversationResourceState = {
  member_id: string;
  resource_type: "report" | "medical_log" | "medication" | "medication_plan" | "medication_batch" | "body_record";
  resource_id: string;
  availability: "available" | "deleted" | "forbidden";
  current_created_at?: string;
  current_updated_at?: string;
};

export type ConversationDetail = {
  member_id: string | null;
  member_name: string | null;
  access_state: "available" | "history_only";
  session_id: string;
  title: string;
  parent_session_id: string | null;
  seed_event_count: number;
  fork_available: boolean;
  pending_turns: PendingConversationTurn[];
  queued_inputs: QueuedConversationInput[];
  resource_states: ConversationResourceState[];
  records: ConversationRecord[];
};

export type ForkConversationResponse = {
  session: ConversationSummary;
};

export type QueuedConversationInput = {
  input_id: string;
  content: string;
  model_id: string;
  thinking_mode: string;
  context_resources: Array<Record<string, unknown>>;
  created_at: string;
  position: number;
};

export type StartedMessageResponse = {
  member_id: string | null;
  member_name: string | null;
  disposition?: "started";
  session_id: string;
  title: string;
  turn_id: string;
  user_message_id: string;
  final_assistant_message_id: string;
  assistant_parent_message_id?: string | null;
  model_id: string;
  message_status: string;
  stream_id: string;
  content: string;
  context_resources?: Array<Record<string, unknown>>;
  created_at: string;
};

export type QueuedMessageResponse = {
  disposition: "queued";
  member_id: string | null;
  member_name: string | null;
  session_id: string;
  title: string;
  queued_input: QueuedConversationInput;
  queued_inputs: QueuedConversationInput[];
};

export type SendMessageResponse = StartedMessageResponse | QueuedMessageResponse;

export type CancelTurnResponse = {
  session_id: string;
  turn_id: string;
  status: "cancelled";
  preserve_partial: boolean;
  stream_id: string;
  final_assistant_message_id?: string | null;
};

export type ConversationStreamEvent =
  | {
    event: "thinking_mode_changed";
    data: {
      session_id: string;
      turn_id: string;
      requested_mode: string;
      effective_mode: string;
      reasons: string[];
    };
  }
  | {
    event: "session_title_updated";
    data: {
      session_id: string;
      turn_id: string;
      title: string;
    };
  }
  | {
    event: "record_started";
    data: Exclude<ConversationRecord, ConversationMessage> & { session_id: string }
    | (ConversationMessage & { kind: "assistant"; session_id: string });
  }
  | {
    event: "record_delta";
    data: {
      session_id: string;
      turn_id: string;
      record_id: string;
      kind: "context" | "error" | "model" | "observation" | "tool" | "assistant";
      delta: string;
      /** Absolute UTF-16 offset, allowing replay over an existing snapshot. */
      offset: number;
      channel?: ConversationModelChannel | "name" | "arguments";
    };
  }
  | {
    event: "record_completed";
    data: {
      session_id: string;
      turn_id: string;
      record_id: string;
      kind: "context" | "error" | "model" | "observation" | "tool" | "assistant";
      content?: unknown;
      estimated_tokens_before?: number;
      estimated_tokens_after?: number;
      target_tokens?: number;
      channel?: ConversationModelChannel;
      value?: unknown;
      context_window_tokens?: number | null;
      tool_call_id?: string;
      name?: string;
      arguments?: unknown;
      observation?: unknown;
      usage?: Record<string, unknown>;
      stop_reason?: string | null;
      result?: unknown;
      status?: string;
      error?: unknown;
      duration_ms?: number;
    };
  }
  | {
    event: "turn_completed";
    data: {
      session_id: string;
      turn_id: string;
      final_assistant_message_id?: string | null;
    };
  }
  | {
    event: "turn_failed";
    data: {
      session_id: string;
      turn_id: string;
      code?: string;
      message?: string;
    };
  }
  | {
    event: "turn_cancelled";
    data: {
      session_id: string;
      turn_id: string;
      code?: string;
      message?: string;
    };
  };

export type UploadedResource = {
  member_id?: string | null;
  resource_id: string;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  relative_path?: string;
  sha256?: string;
  storage_status: "ready";
  lifecycle_status: "pending" | "attached";
  expires_at?: string | null;
};
