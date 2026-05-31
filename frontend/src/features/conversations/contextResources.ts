import type { ConversationMessage } from "../../api/client";

export const QUOTE_PREVIEW_LENGTH = 10;

export type QuoteContextResource = {
  resource_id: string;
  quote_text: string;
  preview?: string;
};

export type FileContextResource = {
  resource_id: string;
  name: string;
  mime_type?: string;
};

export type UploadingResource = {
  upload_id: string;
  name: string;
  progress: number;
};

export function quotePreviewText(quoteText: string) {
  const normalized = quoteText.trim();
  if (normalized.length <= QUOTE_PREVIEW_LENGTH) {
    return normalized;
  }
  return `${normalized.slice(0, QUOTE_PREVIEW_LENGTH)}...`;
}

export function quoteResourcesFromContextResources(
  contextResources: Array<Record<string, unknown>>,
  fallbackId: string
): QuoteContextResource[] {
  return contextResources
    .map((resource, index) => {
      if (resource.resource_type !== "message_quote" || typeof resource.quote_text !== "string") {
        return null;
      }
      const quoteText = resource.quote_text.trim();
      if (!quoteText) {
        return null;
      }
      return {
        resource_id:
          typeof resource.resource_id === "string"
            ? resource.resource_id
            : `${fallbackId}-quote-${index}`,
        quote_text: quoteText
      };
    })
    .filter((resource): resource is QuoteContextResource => Boolean(resource));
}

export function quoteResourcesFromMessage(message: ConversationMessage): QuoteContextResource[] {
  return quoteResourcesFromContextResources(message.context_resources ?? [], message.message_id);
}

export function fileResourcesFromContextResources(
  contextResources: Array<Record<string, unknown>>,
  fallbackId: string
): FileContextResource[] {
  return contextResources
    .map((resource, index) => {
      if (resource.resource_type !== "file") {
        return null;
      }
      return {
        resource_id:
          typeof resource.resource_id === "string"
            ? resource.resource_id
            : `${fallbackId}-file-${index}`,
        name: typeof resource.name === "string" && resource.name.trim() ? resource.name.trim() : "附件",
        ...(typeof resource.mime_type === "string" ? { mime_type: resource.mime_type } : {})
      };
    })
    .filter((resource): resource is FileContextResource => Boolean(resource));
}

export function fileResourcesFromMessage(message: ConversationMessage): FileContextResource[] {
  return fileResourcesFromContextResources(message.context_resources ?? [], message.message_id);
}
