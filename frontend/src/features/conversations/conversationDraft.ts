import type {
  ConversationMessage,
  UploadedResource
} from "../../api/client";
import type { AnnotatedContext } from "./workspaceTypes";

export function submittedContextResourcesFromDraft(
  uploadedResources: UploadedResource[],
  annotatedContexts: AnnotatedContext[]
) {
  return [
    ...uploadedResources.map((resource) => ({
      resource_type: "file",
      resource_id: resource.resource_id
    })),
    ...annotatedContexts.map((annotation) => ({
      resource_type: "record_annotation",
      resource_id: annotation.resource_id,
      source_record_id: annotation.source_record_id,
      annotation_text: annotation.annotation_text
    }))
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
