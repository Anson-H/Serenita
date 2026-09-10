import { assertAuthContext, captureAuthContext, isAuthContextCurrent } from "./authLifecycle";
import {
  parseContextResourceUploadResponse,
  type ContextResourceUploadResponse
} from "./contextResourceUpload";
import { API_BASE_URL, apiResponseError, networkFailureMessage, request, requestResponse } from "./request";
import {
  CancelTurnResponse,
  ConversationDetail,
  ConversationStreamEvent,
  ConversationSummary,
  ForkConversationResponse,
  QueuedConversationInput,
  SendMessageResponse,
  StartedMessageResponse
} from "./types";

export type AttachmentCapabilities = { model_id: string | null; file_mime_types: string[] };

export function fetchAttachmentCapabilities(modelId?: string | null) {
  const query = modelId ? `?model_id=${encodeURIComponent(modelId)}` : "";
  return request<AttachmentCapabilities>(`/conversations/attachment-capabilities${query}`);
}

export function fetchConversations(cursor?: string) {
  return request<{ sessions: ConversationSummary[]; has_more: boolean; next_cursor: string | null }>(
    `/conversations${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ""}`
  );
}

export function updateConversation(
  sessionId: string,
  input: { title?: string; is_pinned?: boolean }
) {
  return request<{ session: ConversationSummary }>(`/conversations/${sessionId}`, {
    method: "PATCH",
    body: JSON.stringify(input)
  });
}

export function batchPinConversations(sessionIds: string[], isPinned: boolean) {
  return request<{ sessions: ConversationSummary[] }>("/conversations/batch-pin", {
    method: "POST",
    body: JSON.stringify({ session_ids: sessionIds, is_pinned: isPinned })
  });
}

export function batchDeleteConversations(sessionIds: string[]) {
  return request<{
    success: boolean;
    deleted_ids: string[];
    failed: Array<{ session_id: string; code: string; message: string }>;
  }>("/conversations/batch-delete", {
    method: "POST",
    body: JSON.stringify({ session_ids: sessionIds })
  });
}

export function getConversation(sessionId: string, signal?: AbortSignal) {
  return request<ConversationDetail>(`/conversations/${sessionId}`, { signal });
}

export function sendMessage(input: {
  memberId: string | null;
  sessionId?: string | null;
  rawText: string;
  modelId?: string | null;
  thinkingMode: string;
  contextResources?: Array<Record<string, unknown>>;
}) {
  return request<SendMessageResponse>("/conversations/messages", {
    method: "POST",
    body: JSON.stringify({
      session_id: input.sessionId ?? null,
      member_id: input.memberId,
      raw_text: input.rawText,
      model_id: input.modelId ?? null,
      thinking_mode: input.thinkingMode,
      context_resources: contextResourceRefs(input.contextResources ?? [])
    })
  });
}

export function editMessage(
  sessionId: string,
  messageId: string,
  input: {
    rawText: string;
    modelId?: string | null;
    thinkingMode: string;
    contextResources?: Array<Record<string, unknown>>;
  }
) {
  return request<StartedMessageResponse>(
    `/conversations/${sessionId}/messages/${messageId}/edit`,
    {
      method: "POST",
      body: JSON.stringify({
        raw_text: input.rawText,
        model_id: input.modelId ?? null,
        thinking_mode: input.thinkingMode,
        context_resources: contextResourceRefs(input.contextResources ?? [])
      })
    }
  );
}

function contextResourceRefs(resources: Array<Record<string, unknown>>) {
  return resources.map((resource) => ({
    resource_type: resource.resource_type,
    resource_id: resource.resource_id,
    ...(resource.resource_type === "record_annotation"
      ? {
        source_record_id: resource.source_record_id,
        annotation_text: resource.annotation_text
      }
      : {}),
    ...(resource.resource_type === "report" && typeof resource.member_id === "string"
      ? { member_id: resource.member_id }
      : {})
  }));
}

export function forkConversation(sessionId: string, atSeq?: number | null) {
  return request<ForkConversationResponse>(`/conversations/${sessionId}/fork`, {
    method: "POST",
    body: JSON.stringify(atSeq == null ? {} : { at_seq: atSeq })
  });
}

export function regenerateMessage(sessionId: string, messageId: string, thinkingMode: string) {
  return request<StartedMessageResponse>(`/conversations/${sessionId}/messages/${messageId}/regenerate`, {
    method: "POST",
    body: JSON.stringify({ thinking_mode: thinkingMode })
  });
}

export function cancelTurn(
  sessionId: string,
  turnId: string,
  input: {
    preservePartial: boolean;
  }
) {
  return request<CancelTurnResponse>(`/conversations/${sessionId}/turns/${turnId}/cancel`, {
    method: "POST",
    body: JSON.stringify({
      preserve_partial: input.preservePartial
    })
  });
}

type QueueMutationResponse = {
  session_id: string;
  queued_inputs: QueuedConversationInput[];
  queued_input?: QueuedConversationInput;
};

export function reorderQueuedInputs(sessionId: string, inputIds: string[]) {
  return request<QueueMutationResponse>(`/conversations/${sessionId}/queued-inputs/order`, {
    method: "PATCH",
    body: JSON.stringify({ input_ids: inputIds })
  });
}

export function deleteQueuedInput(sessionId: string, inputId: string) {
  return request<QueueMutationResponse>(`/conversations/${sessionId}/queued-inputs/${inputId}`, {
    method: "DELETE"
  });
}

export function restoreQueuedInputToDraft(sessionId: string, inputId: string) {
  return request<Required<QueueMutationResponse>>(
    `/conversations/${sessionId}/queued-inputs/${inputId}/restore-to-draft`,
    { method: "POST" }
  );
}

export function runQueuedInputNow(sessionId: string, inputId: string) {
  return request<QueueMutationResponse & { started_turn: Record<string, unknown> | null }>(
    `/conversations/${sessionId}/queued-inputs/${inputId}/run-now`,
    { method: "POST" }
  );
}

export function uploadContextResource(
  memberId: string | null,
  sessionId: string | null,
  file: File,
  modelId?: string | null,
  onUploadProgress?: (progress: number) => void
) {
  const context = captureAuthContext();
  const formData = new FormData();
  if (memberId !== null) formData.append("member_id", memberId);
  formData.append("session_id", sessionId ?? "");
  formData.append("model_id", modelId ?? "");
  formData.append("file", file);

  return new Promise<ContextResourceUploadResponse>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE_URL}/conversations/context-resources`);
    xhr.withCredentials = true;
    if (context.accountId) xhr.setRequestHeader("X-Serenita-Account-ID", context.accountId);
    xhr.upload.onprogress = (event) => {
      if (!isAuthContextCurrent(context) || !event.lengthComputable || event.total <= 0) {
        return;
      }
      onUploadProgress?.(Math.min(99, Math.max(1, Math.round((event.loaded / event.total) * 100))));
    };
    xhr.onload = () => {
      try { assertAuthContext(context); } catch (error) { reject(error); return; }
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(xhrFailure(xhr));
        return;
      }
      try {
        const response = parseContextResourceUploadResponse(JSON.parse(xhr.responseText));
        onUploadProgress?.(100);
        resolve(response);
      } catch {
        reject(new Error("上传响应无效。"));
      }
    };
    xhr.onerror = () => {
      try { assertAuthContext(context); } catch (error) { reject(error); return; }
      reject(new Error(networkFailureMessage(new Error("XMLHttpRequest error"))));
    };
    xhr.send(formData);
  });
}

export function conversationContextResourceUrl(sessionId: string, resourceId: string) {
  return `${API_BASE_URL}/conversations/${encodeURIComponent(sessionId)}/context-resources/${encodeURIComponent(resourceId)}`;
}

function xhrFailure(xhr: XMLHttpRequest) {
  let body: unknown = null;
  try { body = JSON.parse(xhr.responseText); } catch { /* Use the status-based error. */ }
  return apiResponseError(xhr.status, body);
}

export function deleteConversation(sessionId: string) {
  return request<{ success: boolean; session_id: string; message: string }>(`/conversations/${sessionId}`, {
    method: "DELETE"
  });
}

export async function streamConversation(
  sessionId: string,
  streamId: string,
  handlers: {
    signal?: AbortSignal;
    onEvent: (event: ConversationStreamEvent) => void;
  }
) {
  const context = captureAuthContext();
  const response = await requestResponse(`/conversations/${encodeURIComponent(sessionId)}/streams/${encodeURIComponent(streamId)}`, {
    credentials: "include",
    headers: {
      "Accept": "text/event-stream"
    },
    signal: handlers.signal
  });

  if (!response.body) {
    throw new Error("浏览器不支持读取流式响应。");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let terminal = false;
  const onEvent = (event: ConversationStreamEvent) => {
    assertAuthContext(context);
    if (terminal) return;
    terminal = event.event === "turn_completed"
      || event.event === "turn_cancelled"
      || event.event === "turn_failed";
    handlers.onEvent(event);
  };

  try {
    while (!terminal) {
      const { value, done } = await reader.read();
      if (done) {
        buffer += decoder.decode();
        await emitCompleteSseEvents(`${buffer}\n\n`, onEvent);
        return;
      }
      buffer += decoder.decode(value, { stream: true });
      buffer = await emitCompleteSseEvents(buffer, onEvent);
    }
  } finally {
    // A terminal event completes the subscription even if the transport stays open.
    void reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}

async function emitCompleteSseEvents(
  buffer: string,
  onEvent: (event: ConversationStreamEvent) => void
) {
  const blocks = buffer.split(/\n\n/);
  const pending = blocks.pop() ?? "";
  for (const block of blocks) {
    const event = parseSseEvent(block);
    if (event) {
      onEvent(event);
    }
  }
  return pending;
}

function parseSseEvent(block: string): ConversationStreamEvent | null {
  let eventName = "message";
  const dataLines: string[] = [];
  for (const line of block.split(/\n/)) {
    if (line.startsWith("event:")) {
      eventName = line.slice("event:".length).trim();
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trimStart());
    }
  }
  if (!dataLines.length) {
    return null;
  }
  if (!["thinking_mode_changed", "session_title_updated", "record_started", "record_delta", "record_completed", "turn_completed", "turn_failed", "turn_cancelled"].includes(eventName)) {
    return null;
  }
  return {
    event: eventName,
    data: JSON.parse(dataLines.join("\n"))
  } as ConversationStreamEvent;
}
