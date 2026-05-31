import type {
  ConversationDetail,
  ConversationMessage,
  SendMessageResponse
} from "../../api/client";

type MessageUpdater = (message: ConversationMessage) => ConversationMessage;

type StreamingTurnDetailOptions = {
  response: SendMessageResponse;
  account: string;
  currentDetail: ConversationDetail | null;
  rawText: string;
  parentMessageId: string | null | undefined;
  contextResources: Array<Record<string, unknown>>;
  thinkingMode: string;
  untitledTitle: string;
};

type RegeneratingTurnDetailOptions = {
  response: SendMessageResponse;
  account: string;
  currentDetail: ConversationDetail | null;
  baseMessages: ConversationMessage[];
  titleFallback: string;
};

function streamingThinkingMessage(response: SendMessageResponse): ConversationMessage | null {
  return response.thinking_message_id
    ? {
        message_id: response.thinking_message_id,
        turn_id: response.turn_id,
        parent_message_id: response.user_message_id,
        role: "thinking",
        model_id: response.model_id,
        content: "",
        created_at: response.created_at
      }
    : null;
}

function streamingAssistantMessage(
  response: SendMessageResponse,
  streamingThinking: ConversationMessage | null
): ConversationMessage {
  return {
    message_id: response.assistant_message_id,
    turn_id: response.turn_id,
    parent_message_id: response.assistant_parent_message_id ?? streamingThinking?.message_id ?? response.user_message_id,
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
  streamedMessages: ConversationMessage[]
) {
  const streamedIds = new Set(streamedMessages.map((message) => message.message_id));
  const existingAllMessages = currentDetail?.all_messages ?? currentDetail?.messages ?? [];

  return {
    active_path_message_ids: [...baseMessages, ...streamedMessages].map((message) => message.message_id),
    messages: [...baseMessages, ...streamedMessages],
    all_messages: [
      ...existingAllMessages.filter((message) => !streamedIds.has(message.message_id)),
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
    messages: detail.messages.map(updateMessage),
    all_messages: detail.all_messages?.map(updateMessage) ?? detail.all_messages
  };
}

function appendStreamDeltaToMessage(
  message: ConversationMessage,
  messageId: string | null | undefined,
  delta: string
): ConversationMessage {
  return message.message_id === messageId
    ? {
        ...message,
        content: `${message.content}${delta}`,
        status: message.role === "assistant" ? "streaming" : message.status
      }
    : message;
}

function completeStreamingTurnMessage(
  message: ConversationMessage,
  assistantMessageId: string
): ConversationMessage {
  return message.message_id === assistantMessageId
    ? {
        ...message,
        status: "completed"
      }
    : message;
}

function completeStreamingThinkingMessage(
  message: ConversationMessage,
  turnId: string,
  durationMs: number,
  minDurationMs: number
): ConversationMessage {
  return message.turn_id === turnId && message.role === "thinking" && !message.duration_ms
    ? {
        ...message,
        duration_ms: Math.max(minDurationMs, Math.round(durationMs))
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
  account,
  currentDetail,
  rawText,
  parentMessageId,
  contextResources,
  thinkingMode,
  untitledTitle
}: StreamingTurnDetailOptions): ConversationDetail {
  const currentMessages = currentDetail?.messages ?? [];
  const parentIndex = parentMessageId
    ? currentMessages.findIndex((message) => message.message_id === parentMessageId)
    : -1;
  const baseMessages = parentMessageId && parentIndex >= 0
    ? currentMessages.slice(0, parentIndex + 1)
    : currentMessages;
  const streamingUser: ConversationMessage = {
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
  const streamingThinking = streamingThinkingMessage(response);
  const streamingAssistant = streamingAssistantMessage(response, streamingThinking);
  const streamedMessages = [
    streamingUser,
    ...(streamingThinking ? [streamingThinking] : []),
    streamingAssistant
  ];

  return {
    session_id: response.session_id,
    account,
    title: currentDetail?.title && currentDetail.title !== untitledTitle
      ? currentDetail.title
      : untitledTitle,
    pending_turns: [],
    ...mergeStreamedMessages(currentDetail, baseMessages, streamedMessages)
  };
}

export function buildRegeneratingTurnDetail({
  response,
  account,
  currentDetail,
  baseMessages,
  titleFallback
}: RegeneratingTurnDetailOptions): ConversationDetail {
  const streamingThinking = streamingThinkingMessage(response);
  const streamingAssistant = streamingAssistantMessage(response, streamingThinking);
  const streamedMessages = [
    ...(streamingThinking ? [streamingThinking] : []),
    streamingAssistant
  ];

  return {
    session_id: response.session_id,
    account,
    title: currentDetail?.title ?? titleFallback,
    pending_turns: [],
    ...mergeStreamedMessages(currentDetail, baseMessages, streamedMessages)
  };
}

export function appendStreamDeltaToMessages(
  messages: ConversationMessage[],
  messageId: string | null | undefined,
  delta: string
) {
  if (!messageId || !delta) {
    return messages;
  }

  return messages.map((message) => appendStreamDeltaToMessage(message, messageId, delta));
}

export function appendStreamDeltaToDetail(
  detail: ConversationDetail | null,
  messageId: string | null | undefined,
  delta: string
) {
  if (!messageId || !delta) {
    return detail;
  }

  return updateDetailMessages(detail, (message) => appendStreamDeltaToMessage(message, messageId, delta));
}

export function completeStreamingTurnMessages(
  messages: ConversationMessage[],
  assistantMessageId: string
) {
  return messages.map((message) => completeStreamingTurnMessage(message, assistantMessageId));
}

export function completeStreamingTurnInDetail(
  detail: ConversationDetail | null,
  assistantMessageId: string
) {
  return updateDetailMessages(detail, (message) => completeStreamingTurnMessage(message, assistantMessageId));
}

export function completeStreamingThinkingMessages(
  messages: ConversationMessage[],
  turnId: string,
  durationMs: number,
  minDurationMs: number
) {
  return messages.map((message) =>
    completeStreamingThinkingMessage(message, turnId, durationMs, minDurationMs)
  );
}

export function completeStreamingThinkingInDetail(
  detail: ConversationDetail | null,
  turnId: string,
  durationMs: number,
  minDurationMs: number
) {
  return updateDetailMessages(detail, (message) =>
    completeStreamingThinkingMessage(message, turnId, durationMs, minDurationMs)
  );
}

export function cancelStreamingTurnMessages(messages: ConversationMessage[], turnId: string) {
  return messages.map((message) => cancelStreamingTurnMessage(message, turnId));
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

export function currentStreamingContentForMessages(messages: ConversationMessage[], turnId: string) {
  const partialAssistant = messages.find(
    (message) => message.turn_id === turnId && message.role === "assistant"
  );
  const partialThinking = messages.find(
    (message) => message.turn_id === turnId && message.role === "thinking"
  );

  return {
    partialContent: partialAssistant?.content ?? "",
    partialThinking: partialThinking?.content ?? ""
  };
}

export function currentStreamingContentForDetail(detail: ConversationDetail | null, turnId: string) {
  const sourceMessages = detail?.all_messages ?? detail?.messages ?? [];
  return currentStreamingContentForMessages(sourceMessages, turnId);
}

export function isStreamingAssistantMessage(message: ConversationMessage) {
  return message.role === "assistant" && message.status === "streaming";
}

export function regenerateTargetMessageIdForMessage(
  message: ConversationMessage,
  messagesById: Map<string, ConversationMessage>
) {
  if (!isStreamingAssistantMessage(message)) {
    return message.message_id;
  }

  const parent = message.parent_message_id ? messagesById.get(message.parent_message_id) : null;
  if (parent?.role === "thinking" && parent.parent_message_id) {
    return parent.parent_message_id;
  }
  if (parent?.role === "user") {
    return parent.message_id;
  }
  return message.message_id;
}
