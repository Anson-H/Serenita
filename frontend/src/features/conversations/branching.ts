import type { ConversationMessage } from "../../api/client";

export function createMessageIndex(messages: ConversationMessage[]) {
  const map = new Map<string, ConversationMessage>();
  for (const message of messages) {
    map.set(message.message_id, message);
  }
  return map;
}

export function branchParentKeyForMessage(
  message: ConversationMessage,
  messagesById: Map<string, ConversationMessage>
) {
  const actualParent = message.parent_message_id ? messagesById.get(message.parent_message_id) : null;
  if (message.role === "assistant" && actualParent?.role === "thinking") {
    return actualParent.parent_message_id ?? "root";
  }
  return message.parent_message_id ?? "root";
}

export function buildChildrenByParent(
  allMessages: ConversationMessage[],
  messagesById: Map<string, ConversationMessage>
) {
  const map = new Map<string, ConversationMessage[]>();
  for (const message of allMessages) {
    if (message.role === "thinking") {
      continue;
    }
    const key = branchParentKeyForMessage(message, messagesById);
    map.set(key, [...(map.get(key) ?? []), message]);
  }
  return map;
}

export function pathToMessageId(
  messageId: string,
  messagesById: Map<string, ConversationMessage>
) {
  const path: string[] = [];
  let currentId: string | null | undefined = messageId;
  const seen = new Set<string>();
  while (currentId && !seen.has(currentId)) {
    const message = messagesById.get(currentId);
    if (!message) {
      break;
    }
    seen.add(currentId);
    path.push(currentId);
    currentId = message.parent_message_id;
  }
  return path.reverse();
}
