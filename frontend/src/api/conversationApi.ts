import {
  CancelTurnResponse,
  ConversationDetail,
  ConversationStreamEvent,
  ConversationSummary,
  SendMessageResponse,
  UploadedResource
} from "./types";
import { networkFailureMessage, request, serverFailureMessage } from "./request";
import { getSessionToken } from "./sessionToken";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";

export function fetchConversations() {
  return request<{ sessions: ConversationSummary[]; has_more: boolean; next_cursor: string | null }>(
    "/conversations"
  );
}

export function getConversation(sessionId: string) {
  return request<ConversationDetail>(`/conversations/${sessionId}`);
}

export function sendMessage(input: {
  sessionId?: string | null;
  parentMessageId?: string | null;
  rawText: string;
  modelId?: string | null;
  thinkingMode: string;
  contextResources?: Array<Record<string, unknown>>;
}) {
  return request<SendMessageResponse>("/conversations/messages", {
    method: "POST",
    body: JSON.stringify({
      session_id: input.sessionId ?? null,
      parent_message_id: input.parentMessageId ?? null,
      raw_text: input.rawText,
      model_id: input.modelId ?? null,
      thinking_mode: input.thinkingMode,
      context_resources: input.contextResources ?? []
    })
  });
}

export function regenerateMessage(sessionId: string, messageId: string, thinkingMode: string) {
  return request<SendMessageResponse>(`/conversations/${sessionId}/messages/${messageId}/regenerate`, {
    method: "POST",
    body: JSON.stringify({ thinking_mode: thinkingMode })
  });
}

export function cancelTurn(
  sessionId: string,
  turnId: string,
  input: {
    preservePartial: boolean;
    partialContent?: string;
    partialThinking?: string;
  }
) {
  return request<CancelTurnResponse>(`/conversations/${sessionId}/turns/${turnId}/cancel`, {
    method: "POST",
    body: JSON.stringify({
      preserve_partial: input.preservePartial,
      partial_content: input.partialContent ?? "",
      partial_thinking: input.partialThinking ?? ""
    })
  });
}

export function setActivePath(sessionId: string, activePathMessageIds: string[]) {
  return request<{ success: boolean; session_id: string }>(`/conversations/${sessionId}/active-path`, {
    method: "PATCH",
    body: JSON.stringify({ active_path_message_ids: activePathMessageIds })
  });
}

export function uploadContextResource(
  sessionId: string | null,
  file: File,
  modelId?: string | null,
  onUploadProgress?: (progress: number) => void
) {
  const formData = new FormData();
  formData.append("session_id", sessionId ?? "");
  formData.append("model_id", modelId ?? "");
  formData.append("file", file);

  return new Promise<{ session_id: string; resource: UploadedResource }>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE_URL}/conversations/context-resources`);
    const token = getSessionToken();
    if (token) {
      xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    }
    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable || event.total <= 0) {
        return;
      }
      onUploadProgress?.(Math.min(99, Math.max(1, Math.round((event.loaded / event.total) * 100))));
    };
    xhr.onload = () => {
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(new Error(xhrFailureMessage(xhr)));
        return;
      }
      try {
        onUploadProgress?.(100);
        resolve(JSON.parse(xhr.responseText));
      } catch {
        reject(new Error("上传响应不是有效 JSON。"));
      }
    };
    xhr.onerror = () => reject(new Error(networkFailureMessage(new Error("XMLHttpRequest error"))));
    xhr.send(formData);
  });
}

function xhrFailureMessage(xhr: XMLHttpRequest) {
  try {
    const errorBody = JSON.parse(xhr.responseText);
    if (typeof errorBody.detail === "string") {
      return errorBody.detail;
    }
    if (errorBody.detail?.message) {
      return errorBody.detail.message;
    }
    if (errorBody.detail?.code) {
      return errorBody.detail.code;
    }
  } catch {
    if (xhr.status >= 500) {
      return serverFailureMessage({ status: xhr.status } as Response);
    }
  }
  return `请求失败：${xhr.status}`;
}

export function deleteConversation(sessionId: string) {
  return request<{ success: boolean; session_id: string; message: string }>(`/conversations/${sessionId}`, {
    method: "DELETE"
  });
}

export async function streamConversation(
  streamId: string,
  handlers: {
    signal?: AbortSignal;
    onEvent: (event: ConversationStreamEvent) => void;
  }
) {
  const token = getSessionToken();
  const response = await fetch(`${API_BASE_URL}/conversations/streams/${encodeURIComponent(streamId)}`, {
    headers: {
      "Accept": "text/event-stream",
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    },
    signal: handlers.signal
  });

  if (!response.ok) {
    throw new Error(await streamErrorMessage(response));
  }
  if (!response.body) {
    throw new Error("浏览器不支持读取流式响应。");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    buffer = await emitCompleteSseEvents(buffer, handlers.onEvent);
  }

  buffer += decoder.decode();
  await emitCompleteSseEvents(`${buffer}\n\n`, handlers.onEvent);
}

async function streamErrorMessage(response: Response) {
  let message = `流式订阅失败：${response.status}`;
  try {
    const errorBody = await response.json();
    if (typeof errorBody.detail === "string") {
      message = errorBody.detail;
    } else if (errorBody.detail?.message) {
      message = errorBody.detail.message;
    } else if (errorBody.detail?.code) {
      message = errorBody.detail.code;
    }
  } catch {
    if (response.status >= 500) {
      message = serverFailureMessage(response);
    }
  }
  return message;
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
      await yieldToBrowserPaint();
    }
  }
  return pending;
}

function yieldToBrowserPaint() {
  return new Promise<void>((resolve) => {
    if (typeof window === "undefined" || typeof window.requestAnimationFrame !== "function") {
      setTimeout(resolve, 0);
      return;
    }
    window.requestAnimationFrame(() => window.setTimeout(resolve, 0));
  });
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
  if (!["thinking_delta", "content_delta", "completed", "failed", "cancelled"].includes(eventName)) {
    return null;
  }
  return {
    event: eventName,
    data: JSON.parse(dataLines.join("\n"))
  } as ConversationStreamEvent;
}
