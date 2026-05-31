import type { FormEvent, ReactNode, RefObject } from "react";

import type { ConversationMessage } from "../../api/client";
import { BranchIcon, CopyIcon, EditIcon, RegenerateIcon, StarIcon } from "../../components/icons";
import { MarkdownContent } from "../../components/MarkdownContent";
import {
  fileResourcesFromContextResources,
  quoteResourcesFromContextResources,
  type FileContextResource,
  type QuoteContextResource
} from "./contextResources";
import { MessageFileReference, MessageQuoteReference } from "./ResourceChips";
import { thinkingSummaryText } from "./thinking";

type ConversationMessageBubbleProps = {
  activelyThinkingTurnId: string | null;
  branchControls: ReactNode;
  branchingFromThisMessage: boolean;
  copied: boolean;
  editingMessageContextResources: Array<Record<string, unknown>>;
  editingMessageId: string | null;
  editingMessageInputRef: RefObject<HTMLTextAreaElement | null>;
  editingMessageText: string;
  favorited: boolean;
  highlightedMessageId: string | null;
  message: ConversationMessage;
  onBranchAfter: (message: ConversationMessage) => void;
  onCancelEditingMessage: () => void;
  onCopyMessage: (message: ConversationMessage) => void | Promise<void>;
  onEditUserMessage: (message: ConversationMessage) => void;
  onEditingMessageTextChange: (text: string) => void;
  onRegenerate: (message: ConversationMessage) => void | Promise<void>;
  onRegisterMessageElement: (messageId: string, node: HTMLElement | null) => void;
  onRemoveEditingContextResource: (resourceId: string) => void;
  onSubmitEditedUserMessage: (
    event: FormEvent<HTMLFormElement>,
    message: ConversationMessage
  ) => void | Promise<void>;
  onToggleFavorite: (message: ConversationMessage) => void | Promise<void>;
  onUpdateQuoteSelection: (message: ConversationMessage) => void;
  sending: boolean;
};

function renderMarkdownContent(content: string) {
  return <MarkdownContent content={content} />;
}

function renderMessageQuoteReference(quote: QuoteContextResource) {
  return <MessageQuoteReference quote={quote} />;
}

function renderMessageFileReference(
  resource: FileContextResource,
  options?: { onRemove?: (resourceId: string) => void }
) {
  return <MessageFileReference resource={resource} onRemove={options?.onRemove} />;
}

export function ConversationMessageBubble({
  activelyThinkingTurnId,
  branchControls,
  branchingFromThisMessage,
  copied,
  editingMessageContextResources,
  editingMessageId,
  editingMessageInputRef,
  editingMessageText,
  favorited,
  highlightedMessageId,
  message,
  onBranchAfter,
  onCancelEditingMessage,
  onCopyMessage,
  onEditUserMessage,
  onEditingMessageTextChange,
  onRegenerate,
  onRegisterMessageElement,
  onRemoveEditingContextResource,
  onSubmitEditedUserMessage,
  onToggleFavorite,
  onUpdateQuoteSelection,
  sending
}: ConversationMessageBubbleProps) {
  if (message.role === "thinking") {
    return (
      <details
        className="thinking-process"
        data-highlighted={highlightedMessageId === message.message_id ? "true" : undefined}
        key={message.message_id}
        ref={(node) => onRegisterMessageElement(message.message_id, node)}
      >
        <summary>
          <span className="thinking-duration">
            {thinkingSummaryText(message, activelyThinkingTurnId === message.turn_id)}
          </span>
        </summary>
        {message.content ? renderMarkdownContent(message.content) : <span className="message-meta">正在展开思考过程...</span>}
      </details>
    );
  }

  const emptyMessageText =
    message.role === "assistant" && message.status === "cancelled"
      ? "生成已取消。"
      : "正在生成回答...";
  const isEditingMessage = message.role === "user" && editingMessageId === message.message_id;
  const visibleContextResources = isEditingMessage ? editingMessageContextResources : message.context_resources ?? [];
  const quoteResources = quoteResourcesFromContextResources(visibleContextResources, message.message_id);
  const fileResources = fileResourcesFromContextResources(visibleContextResources, message.message_id);
  const hasVisibleMessageBody = Boolean(message.content || fileResources.length || quoteResources.length);

  return (
    <article
      className={`message-entry ${message.role}`}
      data-highlighted={highlightedMessageId === message.message_id ? "true" : undefined}
      key={message.message_id}
      onKeyUp={() => onUpdateQuoteSelection(message)}
      onMouseUp={() => onUpdateQuoteSelection(message)}
      ref={(node) => onRegisterMessageElement(message.message_id, node)}
    >
      <div
        className={`message-bubble ${message.role}`}
      >
        {isEditingMessage ? (
          <form
            className="message-edit-form"
            onSubmit={(event) => void onSubmitEditedUserMessage(event, message)}
          >
            {fileResources.length || quoteResources.length ? (
              <div className="message-context-list message-edit-context-list">
                {fileResources.map((resource) => renderMessageFileReference(resource, {
                  onRemove: onRemoveEditingContextResource
                }))}
                {quoteResources.length ? (
                  quoteResources.map((quote) => renderMessageQuoteReference(quote))
                ) : null}
              </div>
            ) : null}
            <textarea
              aria-label="编辑历史提问"
              disabled={sending}
              onChange={(event) => onEditingMessageTextChange(event.target.value)}
              ref={editingMessageInputRef}
              rows={Math.max(1, editingMessageText.split(/\r\n|\r|\n/).length)}
              value={editingMessageText}
            />
            <div className="message-edit-actions">
              <button
                className="message-edit-button message-edit-cancel-button"
                disabled={sending}
                onClick={onCancelEditingMessage}
                type="button"
              >
                取消
              </button>
              <button className="message-edit-button message-edit-send-button" disabled={sending} type="submit">
                {sending ? "发送中..." : "发送"}
              </button>
            </div>
          </form>
        ) : (
          <>
            {fileResources.length || quoteResources.length ? (
              <div className="message-context-list">
                {fileResources.map((resource) => renderMessageFileReference(resource))}
                {quoteResources.length ? (
                  quoteResources.map((quote) => renderMessageQuoteReference(quote))
                ) : null}
              </div>
            ) : null}
            {hasVisibleMessageBody ? (
              message.content ? renderMarkdownContent(message.content) : null
            ) : message.role === "assistant" ? <span className="message-meta">{emptyMessageText}</span> : null}
            {message.role === "assistant" && message.status === "cancelled" && message.content ? (
              <span className="message-meta">生成已取消。</span>
            ) : null}
          </>
        )}
      </div>
      {!isEditingMessage ? (
        <div className={`message-actions ${message.role}-actions`}>
          <button
            aria-label="复制消息"
            className="message-icon-button"
            onClick={() => void onCopyMessage(message)}
            title={copied ? "已复制" : "复制"}
            type="button"
          >
            {copied ? <span className="copy-success-icon">✓</span> : <CopyIcon />}
          </button>
          {message.role === "user" ? (
            <button
              aria-label="编辑消息"
              className="message-icon-button"
              onClick={() => onEditUserMessage(message)}
              title="编辑"
              type="button"
            >
              <EditIcon />
            </button>
          ) : null}
          {message.role === "assistant" ? (
            <>
              <button
                aria-label="重新生成"
                className="message-icon-button"
                onClick={() => void onRegenerate(message)}
                title="重新生成"
                type="button"
              >
                <RegenerateIcon />
              </button>
              <button
                aria-label={branchingFromThisMessage ? "已选择分支起点" : "创建分支"}
                className="message-icon-button"
                data-active={branchingFromThisMessage ? "true" : undefined}
                onClick={() => onBranchAfter(message)}
                title={branchingFromThisMessage ? "已选择分支起点" : "创建分支"}
                type="button"
              >
                {branchingFromThisMessage ? <span className="copy-success-icon">✓</span> : <BranchIcon />}
              </button>
              <button
                aria-label={favorited ? "取消收藏回答" : "收藏回答"}
                className="message-icon-button"
                data-active={favorited ? "true" : undefined}
                onClick={() => void onToggleFavorite(message)}
                title={favorited ? "取消收藏回答" : "收藏回答"}
                type="button"
              >
                <StarIcon filled={favorited} />
              </button>
              {branchControls}
            </>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}
