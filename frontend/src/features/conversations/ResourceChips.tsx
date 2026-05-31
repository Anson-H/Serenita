import type { CSSProperties } from "react";

import type { UploadedResource } from "../../api/client";
import { PaperclipIcon, QuoteIcon } from "../../components/icons";
import {
  quotePreviewText,
  type FileContextResource,
  type QuoteContextResource,
  type UploadingResource
} from "./contextResources";

export type { FileContextResource, QuoteContextResource, UploadingResource } from "./contextResources";

type QuoteContextChipProps = {
  quote: QuoteContextResource;
  removable: boolean;
  onRemove?: () => void;
};

export function QuoteContextChip({ quote, removable, onRemove }: QuoteContextChipProps) {
  const quoteText = quote.quote_text.trim();
  const previewText = quote.preview ?? quotePreviewText(quoteText);
  return (
    <span
      aria-label={`引用全文：${quoteText}`}
      className="quote-context-chip"
      key={`${quote.resource_id}-${quoteText}`}
      tabIndex={0}
    >
      <QuoteIcon />
      <span className="quote-context-preview">“{previewText}”</span>
      <span className="quote-context-tooltip" role="tooltip">{quoteText}</span>
      {removable ? (
        <button
          aria-label="清除引用"
          className="quote-context-remove"
          onClick={onRemove}
          type="button"
        >
          ×
        </button>
      ) : null}
    </span>
  );
}

type UploadedResourceChipProps = {
  resource: UploadedResource;
  onRemove: (resourceId: string) => void;
};

export function UploadedResourceChip({ resource, onRemove }: UploadedResourceChipProps) {
  return (
    <span
      aria-label={`附件：${resource.name}`}
      className="file-context-chip"
      key={resource.resource_id}
      tabIndex={0}
      title={resource.name}
    >
      <PaperclipIcon />
      <span className="file-context-name">{resource.name}</span>
      <button
        aria-label={`移除附件：${resource.name}`}
        className="file-context-remove"
        onClick={() => onRemove(resource.resource_id)}
        type="button"
      >
        ×
      </button>
    </span>
  );
}

type UploadingResourceChipProps = {
  resource: UploadingResource;
};

export function UploadingResourceChip({ resource }: UploadingResourceChipProps) {
  return (
    <span
      aria-label={`正在上传：${resource.name}`}
      className="file-context-chip file-context-chip-uploading"
      key={resource.upload_id}
      tabIndex={0}
      title={resource.name}
    >
      <span
        aria-label={`上传进度 ${resource.progress}%`}
        aria-valuemax={100}
        aria-valuemin={0}
        aria-valuenow={resource.progress}
        className="file-upload-progress"
        role="progressbar"
        style={{ "--upload-progress": `${resource.progress}%` } as CSSProperties}
      />
      <span className="file-context-name">{resource.name}</span>
    </span>
  );
}

type MessageQuoteReferenceProps = {
  quote: QuoteContextResource;
};

export function MessageQuoteReference({ quote }: MessageQuoteReferenceProps) {
  const quoteText = quote.quote_text.trim();
  return (
    <span
      aria-label={`引用全文：${quoteText}`}
      className="message-quote-reference"
      key={`${quote.resource_id}-${quoteText}`}
      tabIndex={0}
    >
      <QuoteIcon />
      <span className="message-quote-copy">引用 “{quotePreviewText(quoteText)}”</span>
      <span className="quote-context-tooltip" role="tooltip">{quoteText}</span>
    </span>
  );
}

type MessageFileReferenceProps = {
  resource: FileContextResource;
  onRemove?: (resourceId: string) => void;
};

export function MessageFileReference({ resource, onRemove }: MessageFileReferenceProps) {
  return (
    <span
      aria-label={`附件：${resource.name}`}
      className="message-file-reference"
      key={resource.resource_id}
      tabIndex={0}
      title={resource.mime_type ? `${resource.name} · ${resource.mime_type}` : resource.name}
    >
      <PaperclipIcon />
      <span className="message-file-copy">{resource.name}</span>
      {onRemove ? (
        <button
          aria-label={`移除附件：${resource.name}`}
          className="file-context-remove message-file-remove"
          onClick={() => onRemove(resource.resource_id)}
          type="button"
        >
          ×
        </button>
      ) : null}
    </span>
  );
}
