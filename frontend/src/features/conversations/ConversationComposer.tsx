import type { ChangeEvent, FormEvent, ReactNode, RefObject } from "react";

import type { UploadedResource } from "../../api/client";
import { ArrowUpIcon, PaperclipIcon, StopIcon } from "../../components/icons";
import type { QuoteContextResource, UploadingResource } from "./contextResources";

type ConversationComposerProps = {
  activeScenario: string;
  activeStreamTurnId: string | null;
  canAttachFiles: boolean;
  cancellingTurnId: string | null;
  composerError: string;
  composerRef: RefObject<HTMLFormElement | null>;
  composerTextareaRef: RefObject<HTMLTextAreaElement | null>;
  composerText: string;
  onCancelActiveGeneration: () => void;
  onComposerTextChange: (text: string) => void;
  onFileUpload: (event: ChangeEvent<HTMLInputElement>) => void | Promise<void>;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void | Promise<void>;
  quotedContext: QuoteContextResource | null;
  renderComposerModelControl: () => ReactNode;
  renderQuoteContextChip: (quote: QuoteContextResource, removable: boolean) => ReactNode;
  renderUploadedResourceChip: (resource: UploadedResource) => ReactNode;
  renderUploadingResourceChip: (resource: UploadingResource) => ReactNode;
  selectedModelFileMimeTypes: string[];
  selectedScenarioPlaceholder: string;
  sending: boolean;
  uploadedResources: UploadedResource[];
  uploadingResources: UploadingResource[];
};

export function ConversationComposer({
  activeScenario,
  activeStreamTurnId,
  canAttachFiles,
  cancellingTurnId,
  composerError,
  composerRef,
  composerTextareaRef,
  composerText,
  onCancelActiveGeneration,
  onComposerTextChange,
  onFileUpload,
  onSubmit,
  quotedContext,
  renderComposerModelControl,
  renderQuoteContextChip,
  renderUploadedResourceChip,
  renderUploadingResourceChip,
  selectedModelFileMimeTypes,
  selectedScenarioPlaceholder,
  sending,
  uploadedResources,
  uploadingResources
}: ConversationComposerProps) {
  return (
    <form className="assistant-composer conversation-composer" onSubmit={onSubmit} ref={composerRef}>
      {quotedContext ? (
        <div className="resource-list quote-context-list">
          {renderQuoteContextChip(quotedContext, true)}
        </div>
      ) : null}
      {uploadingResources.length || uploadedResources.length ? (
        <div className="resource-list file-context-list">
          {uploadingResources.map((resource) => renderUploadingResourceChip(resource))}
          {uploadedResources.map((resource) => renderUploadedResourceChip(resource))}
        </div>
      ) : null}
      <div className="composer-input-frame">
        <textarea
          aria-label="输入健康问题"
          disabled={activeScenario !== "home" || sending}
          onChange={(event) => onComposerTextChange(event.target.value)}
          placeholder={selectedScenarioPlaceholder}
          ref={composerTextareaRef}
          rows={1}
          value={composerText}
        />
      </div>
      <div className="composer-footer">
        {canAttachFiles ? (
          <label aria-label="附加文件" className="file-button icon-button" title="附加文件">
            <PaperclipIcon />
            <input accept={selectedModelFileMimeTypes.join(",")} onChange={onFileUpload} type="file" />
          </label>
        ) : null}
        {renderComposerModelControl()}
        {activeStreamTurnId ? (
          <button
            aria-label="停止生成"
            className="command-button send-button stop-button"
            disabled={Boolean(cancellingTurnId)}
            onClick={onCancelActiveGeneration}
            title="停止生成"
            type="button"
          >
            <StopIcon />
          </button>
        ) : (
          <button
            aria-label={sending ? "发送中..." : "发送"}
            className="command-button send-button"
            disabled={sending}
            title={sending ? "发送中..." : "发送"}
            type="submit"
          >
            {sending ? <span aria-hidden="true">...</span> : <ArrowUpIcon />}
          </button>
        )}
      </div>
      {composerError ? <p className="status-message error">{composerError}</p> : null}
    </form>
  );
}
