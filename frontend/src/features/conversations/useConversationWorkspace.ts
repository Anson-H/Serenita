import {
  type Dispatch,
  type FormEvent,
  type MutableRefObject,
  type SetStateAction,
} from "react";

import {
  type ConversationDetail,
  type ConversationMessage,
  type ConversationSummary,
  type SendMessageResponse,
  type UploadedResource,
  apiClient
} from "../../api/client";
import { chatPathForSession, type RoutePath } from "../../app/routes";
import {
  buildRegeneratingTurnDetail,
  buildStreamingTurnDetail,
  isStreamingAssistantMessage,
  regenerateTargetMessageIdForMessage
} from "./streamingMessages";
import { hasSubmittableDraft, latestAssistantMessageIdFrom, submittedContextResourcesFromDraft } from "./conversationDraft";
import { type UploadingResource } from "./contextResources";
import { pathToMessageId } from "./branching";
import { useConversationStreamController } from "./useConversationStreamController";
import {
  type ActiveStream,
  type QuoteSelection,
  type QuotedContext,
  type ScenarioTab
} from "./workspaceTypes";

const UNTITLED_CONVERSATION_TITLE = "新对话";

type ConversationWorkspaceOptions = {
  activeScenario: ScenarioTab;
  activeStreamRef: MutableRefObject<ActiveStream | null>;
  composerText: string;
  currentSessionAccount: string;
  currentSessionId: string | null;
  conversationDetail: ConversationDetail | null;
  messages: ConversationMessage[];
  messagesById: Map<string, ConversationMessage>;
  parentForNextMessage: string | null | undefined;
  quotedContext: QuotedContext | null;
  selectedModelId: string;
  thinkingMode: string;
  uploadedResources: UploadedResource[];
  setActiveStreamTurnId: Dispatch<SetStateAction<string | null>>;
  setActivelyThinkingTurnId: Dispatch<SetStateAction<string | null>>;
  setCancellingTurnId: Dispatch<SetStateAction<string | null>>;
  setComposerError: Dispatch<SetStateAction<string>>;
  setComposerText: Dispatch<SetStateAction<string>>;
  setConversations: Dispatch<SetStateAction<ConversationSummary[]>>;
  setCurrentSessionId: Dispatch<SetStateAction<string | null>>;
  setConversationDetail: Dispatch<SetStateAction<ConversationDetail | null>>;
  setParentForNextMessage: Dispatch<SetStateAction<string | null | undefined>>;
  setQuoteSelection: Dispatch<SetStateAction<QuoteSelection | null>>;
  setQuotedContext: Dispatch<SetStateAction<QuotedContext | null>>;
  setEditingMessageId: Dispatch<SetStateAction<string | null>>;
  setEditingMessageText: Dispatch<SetStateAction<string>>;
  setSending: Dispatch<SetStateAction<boolean>>;
  setUploadedResources: Dispatch<SetStateAction<UploadedResource[]>>;
  setUploadingResources: Dispatch<SetStateAction<UploadingResource[]>>;
  clearHomeConversationDraft: () => void;
  markConversationTailShouldFollow: () => void;
  navigateTo: (path: RoutePath, replace?: boolean) => void;
  openConversation: (sessionId: string, sourceMessageId?: string | null) => Promise<boolean>;
};

export function useConversationWorkspace(options: ConversationWorkspaceOptions) {
  const {
    activeScenario,
    activeStreamRef,
    composerText,
    currentSessionAccount,
    currentSessionId,
    conversationDetail,
    markConversationTailShouldFollow,
    messages,
    messagesById,
    navigateTo,
    openConversation,
    parentForNextMessage,
    quotedContext,
    selectedModelId,
    setActiveStreamTurnId,
    setActivelyThinkingTurnId,
    setCancellingTurnId,
    clearHomeConversationDraft,
    setComposerError,
    setComposerText,
    setConversations,
    setCurrentSessionId,
    setConversationDetail,
    setParentForNextMessage,
    setQuoteSelection,
    setQuotedContext,
    setEditingMessageId,
    setEditingMessageText,
    setSending,
    setUploadedResources,
    setUploadingResources,
    thinkingMode,
    uploadedResources
  } = options;
  const {
    cancelActiveGeneration,
    startResponseStream
  } = useConversationStreamController({
    activeStreamRef,
    conversationDetail,
    openConversation,
    refreshConversations,
    setActiveStreamTurnId,
    setActivelyThinkingTurnId,
    setCancellingTurnId,
    setComposerError,
    setConversationDetail,
    setSending
  });

  function latestAssistantMessageId() {
    return latestAssistantMessageIdFrom(messages);
  }

  function nextParentMessageId() {
    if (parentForNextMessage !== undefined) {
      return parentForNextMessage;
    }
    return latestAssistantMessageId();
  }

  function showPendingConversationSummary(response: SendMessageResponse, rawText: string) {
    setConversations((currentSessions) => {
      const pendingSummary: ConversationSummary = {
        session_id: response.session_id,
        title: UNTITLED_CONVERSATION_TITLE,
        last_message_preview: rawText.slice(0, 120),
        created_at: response.created_at,
        last_active_at: response.created_at
      };
      return [
        pendingSummary,
        ...currentSessions.filter((session) => session.session_id !== response.session_id)
      ];
    });
  }

  function showStreamingTurn(
    response: SendMessageResponse,
    rawText: string,
    parentMessageId: string | null | undefined,
    contextResources: Array<Record<string, unknown>>
  ) {
    markConversationTailShouldFollow();
    setConversationDetail(buildStreamingTurnDetail({
      response,
      account: currentSessionAccount,
      currentDetail: conversationDetail,
      rawText,
      parentMessageId,
      contextResources,
      thinkingMode,
      untitledTitle: UNTITLED_CONVERSATION_TITLE
    }));
  }

  function showRegeneratingTurn(response: SendMessageResponse, targetMessage: ConversationMessage) {
    markConversationTailShouldFollow();
    const userPath = pathToMessageId(response.user_message_id, messagesById);
    const baseMessages = userPath
      .map((messageId) => messagesById.get(messageId))
      .filter((message): message is ConversationMessage => Boolean(message));
    const targetParent = targetMessage.parent_message_id
      ? messagesById.get(targetMessage.parent_message_id)
      : null;
    const fallbackUserMessage =
      targetParent?.role === "thinking" && targetParent.parent_message_id
        ? messagesById.get(targetParent.parent_message_id)
        : targetParent;
    const resolvedBaseMessages = baseMessages.length
      ? baseMessages
      : fallbackUserMessage?.role === "user"
        ? [fallbackUserMessage]
        : messages;

    setConversationDetail(buildRegeneratingTurnDetail({
      response,
      account: currentSessionAccount,
      currentDetail: conversationDetail,
      baseMessages: resolvedBaseMessages,
      titleFallback: UNTITLED_CONVERSATION_TITLE
    }));
  }

  function isStreamingAssistant(message: ConversationMessage) {
    return isStreamingAssistantMessage(message);
  }

  function regenerateTargetMessageId(message: ConversationMessage) {
    if (!isStreamingAssistant(message)) {
      return message.message_id;
    }
    return regenerateTargetMessageIdForMessage(message, messagesById);
  }

  async function refreshConversations() {
    const conversationResponse = await apiClient.fetchConversations();
    setConversations(conversationResponse.sessions);
  }

  async function submitConversationMessage(input: {
    rawText: string;
    parentMessageId: string | null | undefined;
    contextResources: Array<Record<string, unknown>>;
    onSubmitted?: () => void;
  }) {
    const wasBrandNewConversation = currentSessionId === null;
    setSending(true);
    setComposerError("");
    try {
      const response = await apiClient.sendMessage({
        sessionId: currentSessionId,
        parentMessageId: input.parentMessageId,
        rawText: input.rawText,
        modelId: selectedModelId || null,
        thinkingMode,
        contextResources: input.contextResources
      });
      setCurrentSessionId(response.session_id);
      navigateTo(chatPathForSession(response.session_id));
      if (wasBrandNewConversation) {
        showPendingConversationSummary(response, input.rawText);
      }
      showStreamingTurn(response, input.rawText, input.parentMessageId, response.context_resources ?? input.contextResources);
      input.onSubmitted?.();
      const streamResult = await startResponseStream(response);
      if (streamResult === "completed") {
        await openConversation(response.session_id);
        await refreshConversations();
      }
    } catch (error) {
      setComposerError(error instanceof Error ? error.message : "发送失败，请稍后重试。");
    } finally {
      setSending(false);
    }
  }

  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedText = composerText.trim();

    if (activeScenario !== "home") {
      return;
    }

    const parentMessageId = nextParentMessageId();
    const submittedContextResources = submittedContextResourcesFromDraft(uploadedResources, quotedContext);

    if (!hasSubmittableDraft(trimmedText, submittedContextResources)) {
      setComposerError("");
      return;
    }

    await submitConversationMessage({
      rawText: trimmedText,
      parentMessageId,
      contextResources: submittedContextResources,
      onSubmitted: () => {
        setComposerText("");
        setUploadingResources([]);
        setUploadedResources([]);
        setQuotedContext(null);
        setQuoteSelection(null);
        setParentForNextMessage(undefined);
        setEditingMessageId(null);
        setEditingMessageText("");
        clearHomeConversationDraft();
      }
    });
  }

  async function regenerate(message: ConversationMessage) {
    if (!currentSessionId) {
      return;
    }
    setSending(true);
    setComposerError("");
    try {
      if (activeStreamRef.current) {
        const cancelled = await cancelActiveGeneration({
          preservePartial: false,
          refreshAfterCancel: false,
          keepSending: true
        });
        if (!cancelled) {
          return;
        }
      }
      const targetMessageId = regenerateTargetMessageId(message);
      const response = await apiClient.regenerateMessage(currentSessionId, targetMessageId, thinkingMode);
      showRegeneratingTurn(response, message);
      const streamResult = await startResponseStream(response);
      if (streamResult === "completed") {
        await openConversation(response.session_id);
        await refreshConversations();
      }
    } catch (error) {
      setComposerError(error instanceof Error ? error.message : "重新生成失败。");
    } finally {
      setSending(false);
    }
  }

  return {
    cancelActiveGeneration,
    isStreamingAssistant,
    nextParentMessageId,
    regenerate,
    regenerateTargetMessageId,
    sendMessage,
    showPendingConversationSummary,
    showRegeneratingTurn,
    showStreamingTurn,
    startResponseStream,
    submitConversationMessage
  };
}
