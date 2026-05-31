import {
  type Dispatch,
  type FormEvent,
  type MutableRefObject,
  type SetStateAction,
  useEffect,
} from "react";

import { type ConversationMessage } from "../../api/client";
import { editDraftFromMessage, hasSubmittableDraft, removeContextResourceById } from "./conversationDraft";
import { type QuoteSelection, type QuotedContext } from "./workspaceTypes";

const COPY_SUCCESS_VISIBLE_MS = 1400;

type SubmitConversationMessage = (input: {
  rawText: string;
  parentMessageId: string | null | undefined;
  contextResources: Array<Record<string, unknown>>;
  onSubmitted?: () => void;
}) => Promise<void>;

type ConversationMessageActionsOptions = {
  copySuccessTimeoutRef: MutableRefObject<number | null>;
  editingMessageContextResources: Array<Record<string, unknown>>;
  editingMessageId: string | null;
  editingMessageInputRef: MutableRefObject<HTMLTextAreaElement | null>;
  editingMessageText: string;
  messageRefs: MutableRefObject<Map<string, HTMLElement>>;
  quoteSelection: QuoteSelection | null;
  setComposerError: Dispatch<SetStateAction<string>>;
  setCopiedMessageId: Dispatch<SetStateAction<string | null>>;
  setEditingMessageContextResources: Dispatch<SetStateAction<Array<Record<string, unknown>>>>;
  setEditingMessageId: Dispatch<SetStateAction<string | null>>;
  setEditingMessageText: Dispatch<SetStateAction<string>>;
  setHighlightedMessageId: Dispatch<SetStateAction<string | null>>;
  setParentForNextMessage: Dispatch<SetStateAction<string | null | undefined>>;
  setQuoteSelection: Dispatch<SetStateAction<QuoteSelection | null>>;
  setQuotedContext: Dispatch<SetStateAction<QuotedContext | null>>;
  submitConversationMessage: SubmitConversationMessage;
};

export function useConversationMessageActions(options: ConversationMessageActionsOptions) {
  const {
    copySuccessTimeoutRef,
    editingMessageContextResources,
    editingMessageId,
    editingMessageInputRef,
    editingMessageText,
    messageRefs,
    quoteSelection,
    setComposerError,
    setCopiedMessageId,
    setEditingMessageContextResources,
    setEditingMessageId,
    setEditingMessageText,
    setHighlightedMessageId,
    setParentForNextMessage,
    setQuoteSelection,
    setQuotedContext,
    submitConversationMessage
  } = options;

  useEffect(() => {
    if (!editingMessageId) {
      return;
    }
    const frameHandle = window.requestAnimationFrame(() => {
      editingMessageInputRef.current?.focus();
      editingMessageInputRef.current?.select();
    });
    return () => window.cancelAnimationFrame(frameHandle);
  }, [editingMessageId, editingMessageInputRef]);

  useEffect(() => {
    if (!editingMessageId) {
      return;
    }
    const frameHandle = window.requestAnimationFrame(() => {
      const input = editingMessageInputRef.current;
      if (!input) {
        return;
      }
      input.style.height = "auto";
      input.style.height = `${input.scrollHeight}px`;
    });
    return () => window.cancelAnimationFrame(frameHandle);
  }, [editingMessageId, editingMessageInputRef, editingMessageText]);

  useEffect(() => {
    return () => {
      if (copySuccessTimeoutRef.current !== null) {
        window.clearTimeout(copySuccessTimeoutRef.current);
      }
    };
  }, [copySuccessTimeoutRef]);

  async function copyMessage(message: ConversationMessage) {
    if (!navigator.clipboard?.writeText) {
      return;
    }
    await navigator.clipboard.writeText(message.content);
    setCopiedMessageId(message.message_id);
    if (copySuccessTimeoutRef.current !== null) {
      window.clearTimeout(copySuccessTimeoutRef.current);
    }
    copySuccessTimeoutRef.current = window.setTimeout(() => {
      setCopiedMessageId((currentMessageId) =>
        currentMessageId === message.message_id ? null : currentMessageId
      );
      copySuccessTimeoutRef.current = null;
    }, COPY_SUCCESS_VISIBLE_MS);
  }

  function updateQuoteSelection(message: ConversationMessage) {
    if (message.role === "thinking") {
      setQuoteSelection(null);
      return;
    }
    const selection = window.getSelection();
    const selectedText = selection?.toString().trim() || "";
    const messageElement = messageRefs.current.get(message.message_id);
    const anchorNode = selection?.anchorNode ?? null;
    const focusNode = selection?.focusNode ?? null;
    if (
      !selection ||
      !selectedText ||
      !messageElement ||
      !anchorNode ||
      !focusNode ||
      !messageElement.contains(anchorNode) ||
      !messageElement.contains(focusNode) ||
      selection.rangeCount === 0
    ) {
      setQuoteSelection(null);
      return;
    }
    const range = selection.getRangeAt(0);
    const rect = range.getBoundingClientRect();
    if (!rect.width && !rect.height) {
      setQuoteSelection(null);
      return;
    }
    const popoverHalfWidth = 72;
    const left = Math.min(
      Math.max(rect.left + rect.width / 2, popoverHalfWidth + 12),
      window.innerWidth - popoverHalfWidth - 12
    );
    const top = Math.max(rect.top, 16);
    setQuoteSelection({
      resource_id: message.message_id,
      quote_text: selectedText,
      preview: selectedText.length > 60 ? `${selectedText.slice(0, 60)}...` : selectedText,
      left,
      top
    });
  }

  function addSelectedTextToConversation() {
    if (!quoteSelection) {
      return;
    }
    setQuotedContext({
      resource_id: quoteSelection.resource_id,
      quote_text: quoteSelection.quote_text,
      preview: quoteSelection.preview
    });
    window.getSelection()?.removeAllRanges();
    setQuoteSelection(null);
  }

  function editUserMessage(message: ConversationMessage) {
    const draft = editDraftFromMessage(message);
    setEditingMessageId(draft.messageId);
    setEditingMessageText(draft.text);
    setEditingMessageContextResources(draft.contextResources);
    setComposerError("");
  }

  function cancelEditingMessage() {
    setEditingMessageId(null);
    setEditingMessageText("");
    setEditingMessageContextResources([]);
    setComposerError("");
  }

  function removeEditingContextResource(resourceId: string) {
    setEditingMessageContextResources((current) =>
      removeContextResourceById(current, resourceId)
    );
  }

  async function submitEditedUserMessage(event: FormEvent<HTMLFormElement>, message: ConversationMessage) {
    event.preventDefault();
    const trimmedText = editingMessageText.trim();
    if (!hasSubmittableDraft(trimmedText, editingMessageContextResources)) {
      setComposerError("编辑内容不能为空。");
      return;
    }

    await submitConversationMessage({
      rawText: trimmedText,
      parentMessageId: message.parent_message_id,
      contextResources: editingMessageContextResources,
      onSubmitted: () => {
        setEditingMessageId(null);
        setEditingMessageText("");
        setEditingMessageContextResources([]);
        setParentForNextMessage(undefined);
        setHighlightedMessageId(null);
      }
    });
  }

  return {
    addSelectedTextToConversation,
    cancelEditingMessage,
    copyMessage,
    editUserMessage,
    removeEditingContextResource,
    submitEditedUserMessage,
    updateQuoteSelection
  };
}
