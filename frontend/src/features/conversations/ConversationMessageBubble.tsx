import {
  useId,
  useMemo,
  type FormEvent,
  type RefObject
} from "react";

import {
  apiClient,
  type ConversationMessage,
  type ConversationModelRecord,
  type ConversationResourceState,
  type ReportContextResource
} from "../../api/client";
import { BranchIcon, CheckIcon, CopyIcon, EditIcon, RegenerateIcon, StarIcon } from "../../components/icons";
import { MarkdownContent } from "../../components/MarkdownContent";
import {
  keepTextControlFocused,
  syncCommittedText
} from "../../utils/inputMethod";
import {
  exportableCitationMarkdown,
  type WebCitationSource
} from "../../utils/markdownCitations";
import { reportResourceKey } from "../reports/reportContext";
import {
  partitionContextResources,
  type AnnotationContextResource,
  type FileContextResource,
} from "./contextResources";
import {
  ConversationTurnTokenUsage,
  hasConversationTokenUsage
} from "./ConversationTokenUsage";
import {
  RelatedReports,
  type RelatedReportReference
} from "./RelatedReports";
import {
  MessageAnnotationReferences,
  MessageFileReference,
  MessageReportReference
} from "./ResourceChips";

type ConversationMessageBubbleProps = {
  conversationSessionId: string | null;
  contextInputTextByResourceId?: Record<string, string>;
  citationSources?: readonly WebCitationSource[];
  copied: boolean;
  editingMessageContextResources: Array<Record<string, unknown>>;
  editingMessageId: string | null;
  editingMessageInputRef: RefObject<HTMLTextAreaElement | null>;
  editingMessageText: string;
  favorited: boolean;
  highlightedMessageId: string | null;
  message: ConversationMessage;
  onCancelEditingMessage: () => void;
  onCopyMessage: (message: ConversationMessage) => void | Promise<void>;
  onEditUserMessage: (message: ConversationMessage) => void;
  onForkConversation: (atSeq: number) => void | Promise<void>;
  onEditingMessageTextChange: (text: string) => void;
  onOpenReport: (reportId: string) => void | Promise<void>;
  onRegenerate: (message: ConversationMessage) => void | Promise<void>;
  onRegisterMessageElement: (messageId: string, node: HTMLElement | null) => void;
  onRemoveEditingContextResource: (resourceId: string) => void;
  onSubmitEditedUserMessage: (
    event: FormEvent<HTMLFormElement>,
    message: ConversationMessage
  ) => void | Promise<void>;
  onToggleFavorite: (message: ConversationMessage) => void | Promise<void>;
  relatedReportResources?: RelatedReportReference[];
  resourceStateByReportId: ReadonlyMap<string, ConversationResourceState>;
  sending: boolean;
  showRelatedContent: boolean;
  showTokenUsage: boolean;
  turnTokenUsageRecords?: ConversationModelRecord[];
};

const CANCELLED_MESSAGE_PLACEHOLDER = "生成已取消。";

function renderMarkdownContent(
  content: string,
  citationSources: readonly WebCitationSource[] = [],
  annotationSourceId?: string
) {
  return (
    <MarkdownContent processCitations
      annotationSourceId={annotationSourceId}
      citationSources={citationSources}
      content={content}
    />
  );
}

function renderMessageAnnotationReferences(
  annotations: AnnotationContextResource[],
  modelInputTextByResourceId: Record<string, string>,
  onRemove?: (resourceId: string) => void
) {
  return (
    <MessageAnnotationReferences
      annotations={annotations}
      key={annotations.map((annotation) => annotation.resource_id).join("-")}
      modelInputTextByResourceId={modelInputTextByResourceId}
      onRemove={onRemove}
    />
  );
}

function renderMessageFileReference(
  resource: FileContextResource,
  options?: { href?: string; onRemove?: (resourceId: string) => void }
) {
  return (
    <MessageFileReference
      href={options?.href}
      key={resource.resource_id}
      resource={resource}
      onRemove={options?.onRemove}
    />
  );
}

function renderMessageReportReference(
  resource: ReportContextResource,
  options: {
    modelInputText?: string;
    onOpen: (reportId: string) => void | Promise<void>;
    onRemove?: (resourceId: string) => void;
    resourceState?: ConversationResourceState;
  }
) {
  return (
    <MessageReportReference
      key={resource.resource_id}
      modelInputText={options.modelInputText}
      onOpen={options.onOpen}
      resource={resource}
      resourceState={options.resourceState}
      onRemove={options?.onRemove}
    />
  );
}

export function ConversationMessageBubble({
  conversationSessionId,
  contextInputTextByResourceId = {},
  citationSources = [],
  copied,
  editingMessageContextResources,
  editingMessageId,
  editingMessageInputRef,
  editingMessageText,
  favorited,
  highlightedMessageId,
  message,
  onCancelEditingMessage,
  onCopyMessage,
  onEditUserMessage,
  onForkConversation,
  onEditingMessageTextChange,
  onOpenReport,
  onRegenerate,
  onRegisterMessageElement,
  onRemoveEditingContextResource,
  onSubmitEditedUserMessage,
  onToggleFavorite,
  relatedReportResources = [],
  resourceStateByReportId,
  sending,
  showRelatedContent,
  showTokenUsage,
  turnTokenUsageRecords
}: ConversationMessageBubbleProps) {
  const editFormId = useId();
  const isEditingMessage = message.role === "user" && editingMessageId === message.message_id;
  const visibleContextResources = isEditingMessage ? editingMessageContextResources : message.context_resources ?? [];
  const contextResources = useMemo(
    () => partitionContextResources(visibleContextResources, message.message_id),
    [message.message_id, visibleContextResources]
  );
  const annotationResources = contextResources.annotations;
  const fileResources = contextResources.files;
  const reportResources = contextResources.reports;
  const fileResourceHref = (resourceId: string) =>
    conversationSessionId
      ? apiClient.conversationContextResourceUrl(conversationSessionId, resourceId)
      : undefined;
  const isCancelledAssistant = message.role === "assistant" && message.status === "cancelled";
  const hasFinishedAssistantOutput =
    message.role === "assistant" && message.status !== "streaming";
  const visibleMessageContent =
    isCancelledAssistant && message.content.trim() === CANCELLED_MESSAGE_PLACEHOLDER
      ? ""
      : message.content;
  const hasVisibleMessageBody = Boolean(
    visibleMessageContent || fileResources.length || annotationResources.length || reportResources.length
  );
  const isEmptyAssistantPlaceholder =
    message.role === "assistant" &&
    !hasVisibleMessageBody;
  const shouldShowRelatedContent = Boolean(
    showRelatedContent &&
    hasFinishedAssistantOutput &&
    visibleMessageContent &&
    relatedReportResources.length
  );
  const shouldShowTokenUsage = Boolean(
    showTokenUsage &&
    hasFinishedAssistantOutput &&
    hasConversationTokenUsage(turnTokenUsageRecords)
  );

  if (isEmptyAssistantPlaceholder) {
    return null;
  }

  return (
    <article
      className={`message-entry ${message.role}`}
      data-highlighted={highlightedMessageId === message.message_id ? "true" : undefined}
      key={message.message_id}
      ref={(node) => onRegisterMessageElement(message.message_id, node)}
    >
      <div
        className={`message-bubble ${message.role}`}
        data-input-surface={message.role === "user" ? "secondary" : undefined}
      >
        {isEditingMessage ? (
          <form
            className="message-edit-form"
            id={editFormId}
            onSubmit={(event) => void onSubmitEditedUserMessage(event, message)}
          >
            {reportResources.length || fileResources.length || annotationResources.length ? (
              <div className="message-context-list">
                {reportResources.map((resource) => renderMessageReportReference(resource, {
                  modelInputText: contextInputTextByResourceId[resource.resource_id],
                  onOpen: onOpenReport,
                  onRemove: onRemoveEditingContextResource,
                  resourceState: resourceStateByReportId.get(reportResourceKey(resource))
                }))}
                {fileResources.map((resource) => renderMessageFileReference(resource, {
                  href: fileResourceHref(resource.resource_id),
                  onRemove: onRemoveEditingContextResource
                }))}
                {annotationResources.length ? (
                  renderMessageAnnotationReferences(
                    annotationResources,
                    contextInputTextByResourceId,
                    onRemoveEditingContextResource
                  )
                ) : null}
              </div>
            ) : null}
            <div className="message-edit-text-frame" data-input-area>
              <span
                aria-hidden="true"
                className={`message-edit-text-mirror${editingMessageText ? "" : " message-edit-empty-mirror"}`}
              >
                {editingMessageText || "\u00a0"}
                {"\u200b"}
              </span>
              <textarea
                aria-label="编辑历史提问"
                disabled={sending}
                name="edited-message"
                onChange={(event) => onEditingMessageTextChange(event.target.value)}
                onCompositionEnd={(event) => syncCommittedText(event, onEditingMessageTextChange)}
                onInput={(event) => onEditingMessageTextChange(event.currentTarget.value)}
                ref={editingMessageInputRef}
                rows={1}
                value={editingMessageText}
              />
            </div>
          </form>
        ) : (
          <>
            {reportResources.length || fileResources.length || annotationResources.length ? (
              <div className="message-context-list">
                {reportResources.map((resource) => renderMessageReportReference(resource, {
                  modelInputText: contextInputTextByResourceId[resource.resource_id],
                  onOpen: onOpenReport,
                  resourceState: resourceStateByReportId.get(reportResourceKey(resource))
                }))}
                {fileResources.map((resource) => renderMessageFileReference(resource, {
                  href: fileResourceHref(resource.resource_id)
                }))}
                {annotationResources.length ? (
                  renderMessageAnnotationReferences(
                    annotationResources,
                    contextInputTextByResourceId
                  )
                ) : null}
              </div>
            ) : null}
            {visibleMessageContent
              ? renderMarkdownContent(
                visibleMessageContent,
                citationSources,
                message.record_id
              )
              : null}
          </>
        )}
      </div>
      {shouldShowRelatedContent || shouldShowTokenUsage ? (
        <div className="assistant-turn-supplements root-disclosure-stack">
          {shouldShowRelatedContent ? (
            <RelatedReports
              messageId={message.message_id}
              onOpenReport={onOpenReport}
              reports={relatedReportResources}
              resourceStateByReportId={resourceStateByReportId}
            />
          ) : null}
          {shouldShowTokenUsage && turnTokenUsageRecords ? (
            <ConversationTurnTokenUsage records={turnTokenUsageRecords} />
          ) : null}
        </div>
      ) : null}
      {isEditingMessage ? (
        <div className="message-edit-actions">
          <button
            className="message-edit-button message-edit-cancel-button"
            disabled={sending}
            onClick={onCancelEditingMessage}
            type="button"
          >
            取消
          </button>
          <button
            className="message-edit-button message-edit-send-button"
            disabled={sending}
            form={editFormId}
            onMouseDown={keepTextControlFocused}
            type="submit"
          >
            {sending ? "发送中..." : "发送"}
          </button>
        </div>
      ) : (
        <div className={`message-actions ${message.role}-actions`}>
          <button
            aria-label={copied ? "消息已复制" : "复制消息"}
            className="control control--inline control--icon control--ghost message-icon-button"
            data-feedback={copied ? "success" : undefined}
            onClick={() => void onCopyMessage(
              message.role === "assistant" && citationSources.length
                ? {
                  ...message,
                  content: exportableCitationMarkdown(message.content, citationSources)
                }
                : message
            )}
            title={copied ? "已复制" : "复制"}
            type="button"
          >
            {copied ? <CheckIcon className="message-action-icon" /> : <CopyIcon />}
          </button>
          {message.role === "user" && message.editable ? (
            <button
              aria-label="编辑消息"
              className="control control--inline control--icon control--ghost message-icon-button"
              onClick={() => onEditUserMessage(message)}
              title="编辑"
              type="button"
            >
              <EditIcon />
            </button>
          ) : null}
          {message.role === "assistant" ? (
            <>
              {message.regenerable ? (
                <button
                  aria-label="重新生成"
                  className="control control--inline control--icon control--ghost message-icon-button"
                  onClick={() => void onRegenerate(message)}
                  title="重新生成"
                  type="button"
                >
                  <RegenerateIcon />
                </button>
              ) : null}
              <button
                aria-label={message.fork_anchor_seq == null ? "当前回答没有稳定分支边界" : "创建分支"}
                className="control control--inline control--icon control--ghost message-icon-button"
                disabled={message.fork_anchor_seq == null}
                onClick={() => {
                  if (message.fork_anchor_seq != null) {
                    void onForkConversation(message.fork_anchor_seq);
                  }
                }}
                title={message.fork_anchor_seq == null ? "本轮尚未形成可复制的稳定边界" : "从此回答创建独立聊天"}
                type="button"
              >
                <BranchIcon />
              </button>
              <button
                aria-label={favorited ? "取消收藏回答" : "收藏回答"}
                className="control control--inline control--icon control--ghost message-icon-button"
                data-active={favorited ? "true" : undefined}
                onClick={() => void onToggleFavorite(message)}
                title={favorited ? "取消收藏回答" : "收藏回答"}
                type="button"
              >
                <StarIcon filled={favorited} />
              </button>
            </>
          ) : null}
        </div>
      )}
    </article>
  );
}
