import type {
  ConversationMessage,
  UploadedResource
} from "../../api/client";
import type { QuotedContext } from "./workspaceTypes";

export function latestAssistantMessageIdFrom(messages: ConversationMessage[]) {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index].role === "assistant") {
      return messages[index].message_id;
    }
  }
  return null;
}

export function nextParentMessageIdFor(
  messages: ConversationMessage[],
  parentForNextMessage: string | null | undefined
) {
  if (parentForNextMessage !== undefined) {
    return parentForNextMessage;
  }
  return latestAssistantMessageIdFrom(messages);
}

export function submittedContextResourcesFromDraft(
  uploadedResources: UploadedResource[],
  quotedContext: QuotedContext | null
) {
  return [
    ...uploadedResources.map((resource) => ({
      resource_type: "file",
      resource_id: resource.resource_id
    })),
    ...(quotedContext
      ? [
          {
            resource_type: "message_quote",
            resource_id: quotedContext.resource_id,
            quote_text: quotedContext.quote_text
          }
        ]
      : [])
  ];
}

export function hasSubmittableDraft(rawText: string, contextResources: Array<Record<string, unknown>>) {
  return Boolean(rawText.trim() || contextResources.length);
}

export function editDraftFromMessage(message: ConversationMessage) {
  return {
    messageId: message.message_id,
    text: message.content,
    contextResources: message.context_resources ?? []
  };
}

export function removeContextResourceById(contextResources: Array<Record<string, unknown>>, resourceId: string) {
  return contextResources.filter((resource) => resource.resource_id !== resourceId);
}
