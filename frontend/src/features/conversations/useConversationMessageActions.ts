import {
  type Dispatch,
  type FormEvent,
  type MutableRefObject,
  type SetStateAction,
  useEffect,
} from "react";

import { type ConversationMessage } from "../../api/client";
import { copyTextToClipboard } from "../../utils/clipboard";
import {
  focusWithoutScroll,
  formTextValue
} from "../../utils/inputMethod";
import { TRANSIENT_SUCCESS_ICON_DURATION_MS } from "../../utils/transientFeedback";
import { editDraftFromMessage, hasSubmittableDraft, removeContextResourceById } from "./conversationDraft";
import { type AnnotatedContext, type AnnotationSelection } from "./workspaceTypes";

type EditConversationMessage = (input: {
  message: ConversationMessage;
  rawText: string;
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
  annotationSelection: AnnotationSelection | null;
  preserveConversationAnchor: (anchor: HTMLElement) => void;
  setComposerError: Dispatch<SetStateAction<string>>;
  setCopiedMessageId: Dispatch<SetStateAction<string | null>>;
  setEditingMessageContextResources: Dispatch<SetStateAction<Array<Record<string, unknown>>>>;
  setEditingMessageId: Dispatch<SetStateAction<string | null>>;
  setEditingMessageText: Dispatch<SetStateAction<string>>;
  setHighlightedMessageId: Dispatch<SetStateAction<string | null>>;
  setAnnotatedContexts: Dispatch<SetStateAction<AnnotatedContext[]>>;
  setAnnotationSelection: Dispatch<SetStateAction<AnnotationSelection | null>>;
  editConversationMessage: EditConversationMessage;
};

export function useConversationMessageActions(options: ConversationMessageActionsOptions) {
  const {
    copySuccessTimeoutRef,
    editingMessageContextResources,
    editingMessageId,
    editingMessageInputRef,
    editingMessageText,
    messageRefs,
    annotationSelection,
    preserveConversationAnchor,
    setComposerError,
    setCopiedMessageId,
    setEditingMessageContextResources,
    setEditingMessageId,
    setEditingMessageText,
    setHighlightedMessageId,
    setAnnotatedContexts,
    setAnnotationSelection,
    editConversationMessage
  } = options;
  useEffect(() => {
    if (!editingMessageId) {
      return;
    }
    const frameHandle = window.requestAnimationFrame(() => {
      const input = editingMessageInputRef.current;
      focusWithoutScroll(input);
      input?.setSelectionRange(0, input.value.length);
    });
    return () => window.cancelAnimationFrame(frameHandle);
  }, [editingMessageId, editingMessageInputRef]);

  useEffect(() => {
    return () => {
      if (copySuccessTimeoutRef.current !== null) {
        window.clearTimeout(copySuccessTimeoutRef.current);
      }
    };
  }, [copySuccessTimeoutRef]);

  useEffect(() => {
    if (!annotationSelection) {
      return;
    }
    function dismissOnOutsidePointer(event: PointerEvent) {
      const target = event.target;
      if (target instanceof Element && target.closest(".selection-annotation-popover")) {
        return;
      }
      setAnnotationSelection(null);
    }
    function dismissOnEscape(event: KeyboardEvent) {
      if (event.key !== "Escape") {
        return;
      }
      window.getSelection()?.removeAllRanges();
      setAnnotationSelection(null);
    }
    document.addEventListener("pointerdown", dismissOnOutsidePointer);
    document.addEventListener("keydown", dismissOnEscape);
    return () => {
      document.removeEventListener("pointerdown", dismissOnOutsidePointer);
      document.removeEventListener("keydown", dismissOnEscape);
    };
  }, [annotationSelection, setAnnotationSelection]);

  async function copyMessage(message: ConversationMessage) {
    try {
      await copyTextToClipboard(message.content);
    } catch (error) {
      setComposerError(error instanceof Error ? error.message : "消息复制失败，请检查剪贴板权限。");
      return;
    }
    setCopiedMessageId(message.message_id);
    if (copySuccessTimeoutRef.current !== null) {
      window.clearTimeout(copySuccessTimeoutRef.current);
    }
    copySuccessTimeoutRef.current = window.setTimeout(() => {
      setCopiedMessageId((currentMessageId) =>
        currentMessageId === message.message_id ? null : currentMessageId
      );
      copySuccessTimeoutRef.current = null;
    }, TRANSIENT_SUCCESS_ICON_DURATION_MS);
  }

  function updateAnnotationSelection() {
    const selection = window.getSelection();
    const selectedText = selection?.toString().trim() || "";
    const anchorNode = selection?.anchorNode ?? null;
    const focusNode = selection?.focusNode ?? null;
    const anchorElement = anchorNode instanceof Element ? anchorNode : anchorNode?.parentElement;
    const focusElement = focusNode instanceof Element ? focusNode : focusNode?.parentElement;
    const anchorSource = anchorElement?.closest<HTMLElement>("[data-annotation-source-id]") ?? null;
    const focusSource = focusElement?.closest<HTMLElement>("[data-annotation-source-id]") ?? null;
    const sourceRecordId = anchorSource?.dataset.annotationSourceId?.trim() || "";
    if (
      !selection ||
      !selectedText ||
      !anchorNode ||
      !focusNode ||
      !anchorSource ||
      !focusSource ||
      !sourceRecordId ||
      focusSource.dataset.annotationSourceId?.trim() !== sourceRecordId ||
      selection.rangeCount === 0
    ) {
      setAnnotationSelection(null);
      return;
    }
    const range = selection.getRangeAt(0);
    const rect = range.getBoundingClientRect();
    if (!rect.width && !rect.height) {
      setAnnotationSelection(null);
      return;
    }
    const popoverHalfWidth = 72;
    const left = Math.min(
      Math.max(rect.left + rect.width / 2, popoverHalfWidth + 12),
      window.innerWidth - popoverHalfWidth - 12
    );
    const top = Math.max(rect.top, 16);
    setAnnotationSelection({
      source_record_id: sourceRecordId,
      annotation_text: selectedText,
      preview: selectedText.length > 60 ? `${selectedText.slice(0, 60)}...` : selectedText,
      left,
      top
    });
  }

  function addSelectedTextToConversation() {
    if (!annotationSelection) {
      return;
    }
    setAnnotatedContexts((currentAnnotations) => {
      const alreadyAdded = currentAnnotations.some(
        (annotation) =>
          annotation.source_record_id === annotationSelection.source_record_id
          && annotation.annotation_text === annotationSelection.annotation_text
      );
      if (alreadyAdded) {
        return currentAnnotations;
      }
      return [
        ...currentAnnotations,
        {
          resource_id: window.crypto.randomUUID(),
          source_record_id: annotationSelection.source_record_id,
          annotation_text: annotationSelection.annotation_text,
          preview: annotationSelection.preview
        }
      ];
    });
    window.getSelection()?.removeAllRanges();
    setAnnotationSelection(null);
  }

  function editUserMessage(message: ConversationMessage) {
    const draft = editDraftFromMessage(message);
    const messageElement = messageRefs.current.get(message.message_id);
    if (messageElement) {
      preserveConversationAnchor(messageElement);
    }
    setEditingMessageId(draft.messageId);
    setEditingMessageText(draft.text);
    setEditingMessageContextResources(draft.contextResources);
    setComposerError("");
  }

  function cancelEditingMessage() {
    const messageElement = editingMessageId
      ? messageRefs.current.get(editingMessageId)
      : null;
    if (messageElement) {
      preserveConversationAnchor(messageElement);
    }
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
    const trimmedText = formTextValue(event.currentTarget, "edited-message", editingMessageText).trim();
    if (!hasSubmittableDraft(trimmedText, editingMessageContextResources)) {
      setComposerError("编辑内容不能为空。");
      return;
    }

    await editConversationMessage({
      message,
      rawText: trimmedText,
      contextResources: editingMessageContextResources,
      onSubmitted: () => {
        setEditingMessageId(null);
        setEditingMessageText("");
        setEditingMessageContextResources([]);
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
    updateAnnotationSelection
  };
}
