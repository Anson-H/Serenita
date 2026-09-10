import {
  type Dispatch,
  type FormEvent,
  type MutableRefObject,
  type SetStateAction,
  useEffect,
} from "react";
import { useActiveScope } from "../../utils/useActiveScope";
import { useMembers } from "../members/MemberProvider";
import { createConversationQueueActions } from './conversationQueueActions';
import type { ConversationDraftStore } from './conversationDraftStore';

import {
  apiClient,
  type ConversationDetail,
  type ConversationMessage,
  type ConversationSummary,
  type ReportContextResource,
  type StartedMessageResponse,
  type UploadedResource
} from "../../api/client";
import { chatPathForSession, type RoutePath } from "../../app/routes";
import { showStatusNotification } from "../../components/StatusNotificationCenter";
import { formTextValue } from "../../utils/inputMethod";
import { type UploadingResource } from "./contextResources";
import { hasSubmittableDraft, submittedContextResourcesFromDraft } from "./conversationDraft";
import {
  buildStreamingTurnDetail
} from "./streamingMessages";
import { useConversationStreamController } from "./useConversationStreamController";
import {
  type ActiveStream,
  type AnnotatedContext,
  type AnnotationSelection,
  type ScenarioTab
} from "./workspaceTypes";

const UNTITLED_CONVERSATION_TITLE = "新聊天";

type ConversationWorkspaceOptions = {
  draftStore: ConversationDraftStore;
  conversationViewRef: MutableRefObject<number>;
  refreshConversations: (isRelevant?: () => boolean) => Promise<void>;
  activeScenario: ScenarioTab;
  activeStreamRef: MutableRefObject<ActiveStream | null>;
  composerText: string;
  currentSessionId: string | null;
  conversationDetail: ConversationDetail | null;
  conversationEnabled: boolean;
  conversationVisible: boolean;
  activeReportResource?: ReportContextResource | null;
  bindActiveReportResource?: boolean;
  annotatedContexts: AnnotatedContext[];
  selectedModelId: string;
  thinkingMode: string;
  uploadedResources: UploadedResource[];
  uploadingResources: UploadingResource[];
  setActiveStreamTurnId: Dispatch<SetStateAction<string | null>>;
  setCancellingTurnId: Dispatch<SetStateAction<string | null>>;
  setComposerError: Dispatch<SetStateAction<string>>;
  setComposerText: Dispatch<SetStateAction<string>>;
  setConversations: Dispatch<SetStateAction<ConversationSummary[]>>;
  setCurrentSessionId: Dispatch<SetStateAction<string | null>>;
  setConversationDetail: Dispatch<SetStateAction<ConversationDetail | null>>;
  setAnnotatedContexts: Dispatch<SetStateAction<AnnotatedContext[]>>;
  setAnnotationSelection: Dispatch<SetStateAction<AnnotationSelection | null>>;
  setEditingMessageId: Dispatch<SetStateAction<string | null>>;
  setEditingMessageText: Dispatch<SetStateAction<string>>;
  setSending: Dispatch<SetStateAction<boolean>>;
  setUploadedResources: Dispatch<SetStateAction<UploadedResource[]>>;
  setUploadingResources: Dispatch<SetStateAction<UploadingResource[]>>;
  clearHomeConversationDraft: () => void;
  clearHighlightedMessage: () => void;
  forceConversationLatest: (reason: string) => void;
  prepareConversationMutation: (key: string) => void;
  navigateTo: (path: RoutePath, replace?: boolean) => void;
  openConversation: (sessionId: string, sourceMessageId?: string | null) => Promise<boolean>;
  onThinkingModeChanged: (mode: string) => void;
  onTurnSettled: () => void;
  onRestoreQueuedInputPreferences?: (modelId: string, thinkingMode: string) => void | Promise<void>;
  onBeforeSubmit?: () => void | { startNewConversation?: boolean };
};

export function useConversationWorkspace(options: ConversationWorkspaceOptions) {
  const { activeMemberId } = useMembers();
  const memberId = options.conversationDetail ? options.conversationDetail.member_id : activeMemberId;
  const isCurrentScope = useActiveScope(`${memberId ?? "unbound"}:${options.currentSessionId ?? ""}`);
  const {
    draftStore,
    refreshConversations,
    activeScenario,
    activeStreamRef,
    composerText,
    currentSessionId,
    conversationDetail,
    conversationEnabled,
    conversationVisible,
    activeReportResource,
    bindActiveReportResource = false,
    forceConversationLatest,
    prepareConversationMutation,
    navigateTo,
    openConversation,
    onBeforeSubmit,
    onThinkingModeChanged,
    onTurnSettled,
    onRestoreQueuedInputPreferences,
    annotatedContexts,
    selectedModelId,
    setActiveStreamTurnId,
    setCancellingTurnId,
    clearHomeConversationDraft,
    clearHighlightedMessage,
    setComposerError,
    setComposerText,
    setConversations,
    setCurrentSessionId,
    setConversationDetail,
    setAnnotatedContexts,
    setEditingMessageId,
    setEditingMessageText,
    setSending,
    setUploadedResources,
    thinkingMode,
    uploadedResources,
    uploadingResources
  } = options;
  const {
    cancelActiveGeneration: cancelActiveGenerationFromStream,
    startResponseStream
  } = useConversationStreamController({
    activeStreamRef,
    openConversation,
    onThinkingModeChanged,
    onTurnSettled,
    prepareConversationMutation,
    refreshConversations,
    setActiveStreamTurnId,
    setCancellingTurnId,
    setComposerError,
    setConversationDetail,
    setConversations
  });

  async function cancelActiveGeneration(
    input: Parameters<typeof cancelActiveGenerationFromStream>[0]
  ) {
    clearHighlightedMessage();
    return cancelActiveGenerationFromStream(input);
  }


  const pendingTurn = conversationDetail?.pending_turns[0] ?? null;
  const pendingStreamId = pendingTurn?.stream_id ?? null;

  useEffect(() => {
    if (
      !conversationVisible ||
      !pendingTurn ||
      !conversationDetail ||
      conversationDetail.session_id !== currentSessionId ||
      activeStreamRef.current?.streamId === pendingStreamId
    ) {
      return;
    }
    void startResponseStream({
      session_id: conversationDetail.session_id,
      member_id: conversationDetail.member_id,
      member_name: conversationDetail.member_name,
      title: conversationDetail.title,
      turn_id: pendingTurn.turn_id,
      user_message_id: pendingTurn.user_message_id,
      final_assistant_message_id: pendingTurn.final_assistant_message_id,
      model_id: selectedModelId,
      message_status: pendingTurn.status,
      stream_id: pendingTurn.stream_id,
      content: "",
      created_at: pendingTurn.created_at
    }).catch((error) => {
      setComposerError(error instanceof Error ? error.message : "恢复流式订阅失败。");
    });
  }, [conversationDetail?.session_id, currentSessionId, pendingStreamId, conversationVisible]);

  function showPendingConversationSummary(
    response: StartedMessageResponse
  ) {
    setConversations((currentSessions) => {
      const existingSummary = currentSessions.find(
        (session) => session.session_id === response.session_id
      );
      const pendingSummary: ConversationSummary = {
        session_id: response.session_id,
        member_id: response.member_id,
        member_name: response.member_name,
        access_state: "available",
        title: response.title,
        created_at: response.created_at,
        last_active_at: response.created_at,
        parent_session_id: existingSummary?.parent_session_id ?? null,
        seed_event_count: existingSummary?.seed_event_count ?? 0,
        is_pinned: existingSummary?.is_pinned ?? false,
        pending_turn_status: response.message_status === "queued" ? "queued" : "streaming",
        queued_input_count: existingSummary?.queued_input_count ?? 0,
        fork_available: existingSummary?.fork_available ?? false
      };
      return [
        pendingSummary,
        ...currentSessions.filter((session) => session.session_id !== response.session_id)
      ];
    });
  }

  function showStreamingTurn(
    response: StartedMessageResponse,
    rawText: string,
    contextResources: Array<Record<string, unknown>>,
    baseDetail: ConversationDetail | null = conversationDetail
  ) {
    forceConversationLatest("explicit-turn-start");
    setConversationDetail(buildStreamingTurnDetail({
      response,
      currentDetail: baseDetail,
      rawText,
      contextResources,
      thinkingMode,
      untitledTitle: UNTITLED_CONVERSATION_TITLE,
      initialTitle: response.title
    }));
  }

  function markConversationQueued(sessionId: string | null) {
    if (!sessionId) {
      return;
    }
    setConversations((current) => current.map((conversation) =>
      conversation.session_id === sessionId
        ? { ...conversation, pending_turn_status: "queued" }
        : conversation
    ));
  }

  async function restoreConversationExecutionState(sessionId: string | null) {
    try {
      await refreshConversations();
    } catch {
      if (sessionId && isCurrentScope()) setComposerError("会话状态刷新失败，请重新打开聊天重试。");
    }
  }

  async function submitConversationMessage(input: {
    rawText: string;
    contextResources: Array<Record<string, unknown>>;
    startNewConversation?: boolean;
    memberId?: string;
    isCurrent?: () => boolean;
    sessionId?: string | null;
    onSubmitted?: (sessionId: string) => void;
  }) {
    const view = options.conversationViewRef.current;
    const current = () => options.conversationViewRef.current === view
      && isCurrentScope() && (!input.isCurrent || input.isCurrent());
    if (!current() || !conversationEnabled) return;
    clearHighlightedMessage();
    const targetSessionId = input.sessionId !== undefined
      ? input.sessionId
      : input.startNewConversation
        ? null
        : currentSessionId;
    markConversationQueued(targetSessionId);
    setSending(true);
    setComposerError("");
    try {
      const response = await apiClient.sendMessage({
        memberId: input.memberId ?? memberId,
        sessionId: targetSessionId,
        rawText: input.rawText,
        modelId: selectedModelId || null,
        thinkingMode,
        contextResources: input.contextResources
      });
      if (!current()) {
        void refreshConversations().catch(() => undefined);
        return response;
      }
      if (response.disposition === "queued") {
        input.onSubmitted?.(response.session_id);
        prepareConversationMutation(`queue-accepted:${response.session_id}:${response.queued_inputs.length}`);
        setConversationDetail((current) =>
          current?.session_id === response.session_id
            ? { ...current, queued_inputs: response.queued_inputs }
            : current
        );
        setConversations((current) => current.map((conversation) =>
          conversation.session_id === response.session_id
            ? {
              ...conversation,
              queued_input_count: response.queued_inputs.length
            }
            : conversation
        ));
        // Sidebar refresh is not part of submitting the input. A slow summary
        // read must not keep the composer locked after the queue accepted it.
        void refreshConversations().catch(() => undefined);
        return response;
      }
      setSending(false);
      setCurrentSessionId(response.session_id);
      navigateTo(chatPathForSession(response.session_id));
      // Navigation captures the home draft from this render. Consume the
      // submitted draft afterwards so it cannot be restored as unsent input.
      input.onSubmitted?.(response.session_id);
      const submittedContextResources = response.context_resources ?? input.contextResources;
      showPendingConversationSummary(response);
      showStreamingTurn(
        response,
        input.rawText,
        submittedContextResources,
        input.startNewConversation ? null : conversationDetail
      );
      void startResponseStream(response).catch((error) => {
        setComposerError(error instanceof Error ? error.message : "流式订阅失败，正在后台继续执行。");
      });
      return response;
    } catch (error) {
      if (!current()) return;
      await restoreConversationExecutionState(targetSessionId);
      if (!current()) return;
      setComposerError(error instanceof Error ? error.message : "发送失败，请稍后重试。");
    } finally {
      if (current()) setSending(false);
    }
  }

  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const rawText = formTextValue(event.currentTarget, "message", composerText);
    const submittedDraft = draftStore.capture();

    if (!conversationEnabled) {
      return;
    }

    const submittedContextResources = [
      ...submittedContextResourcesFromDraft(uploadedResources, annotatedContexts),
      ...draftStore.snapshot().contextResources
    ];

    if (!hasSubmittableDraft(rawText, submittedContextResources)) {
      setComposerError("");
      return;
    }

    const submitPreparation = onBeforeSubmit?.();
    const startNewConversation = Boolean(submitPreparation && submitPreparation.startNewConversation);
    const contextResourcesWithReport = [...submittedContextResources];
    if (
      activeScenario === "reports" &&
      bindActiveReportResource &&
      activeReportResource &&
      !contextResourcesWithReport.some(
        (resource) =>
          resource.resource_type === "report" &&
          resource.resource_id === activeReportResource.resource_id
      )
    ) {
      contextResourcesWithReport.push(activeReportResource);
    }

    await submitConversationMessage({
      rawText,
      contextResources: contextResourcesWithReport,
      startNewConversation,
      sessionId: startNewConversation ? undefined : submittedDraft.sessionId ?? currentSessionId,
      onSubmitted: sessionId => {
        draftStore.complete(submittedDraft, sessionId);
        setEditingMessageId(null);
        setEditingMessageText("");
        clearHomeConversationDraft();
      }
    });
  }

  async function regenerate(message: ConversationMessage) {
    if (!currentSessionId || message.role !== "assistant" || !message.regenerable) {
      return;
    }
    clearHighlightedMessage();
    setSending(true);
    markConversationQueued(currentSessionId);
    setComposerError("");
    try {
      if (activeStreamRef.current) {
        const cancelled = await cancelActiveGeneration({
          preservePartial: false,
          refreshAfterCancel: false
        });
        if (!isCurrentScope() || !cancelled) {
          return;
        }
      }
      const response = await apiClient.regenerateMessage(
        currentSessionId,
        message.message_id,
        thinkingMode
      );
      if (!isCurrentScope()) return;
      const opened = await openConversation(response.session_id);
      if (!isCurrentScope() || !opened) return;
      forceConversationLatest("regenerate");
      void startResponseStream(response);
    } catch (error) {
      if (!isCurrentScope()) return;
      await restoreConversationExecutionState(currentSessionId);
      if (!isCurrentScope()) return;
      setComposerError(error instanceof Error ? error.message : "重新生成失败。");
    } finally {
      if (isCurrentScope()) setSending(false);
    }
  }

  async function editMessage(input: {
    message: ConversationMessage;
    rawText: string;
    contextResources: Array<Record<string, unknown>>;
    onSubmitted?: () => void;
  }) {
    if (
      !currentSessionId ||
      input.message.role !== "user" ||
      !input.message.editable
    ) {
      return;
    }
    clearHighlightedMessage();
    setSending(true);
    markConversationQueued(currentSessionId);
    setComposerError("");
    try {
      const response = await apiClient.editMessage(
        currentSessionId,
        input.message.message_id,
        {
          rawText: input.rawText,
          modelId: selectedModelId || null,
          thinkingMode,
          contextResources: input.contextResources
        }
      );
      if (!isCurrentScope()) return;
      input.onSubmitted?.();
      const opened = await openConversation(response.session_id);
      if (!isCurrentScope() || !opened) return;
      forceConversationLatest("edit-submit");
      void startResponseStream(response);
    } catch (error) {
      if (!isCurrentScope()) return;
      await restoreConversationExecutionState(currentSessionId);
      if (!isCurrentScope()) return;
      setComposerError(error instanceof Error ? error.message : "编辑消息失败。");
    } finally {
      if (isCurrentScope()) setSending(false);
    }
  }

  async function createFork(sessionId: string, atSeq?: number | null) {
    if (!sessionId) {
      return;
    }
    try {
      const response = await apiClient.forkConversation(sessionId, atSeq);
      if (!isCurrentScope()) return;
      setConversations((current) => [
        response.session,
        ...current.filter((item) => item.session_id !== response.session.session_id)
      ]);
      setCurrentSessionId(response.session.session_id);
      navigateTo(chatPathForSession(response.session.session_id));
      await openConversation(response.session.session_id);
    } catch (error) {
      if (!isCurrentScope()) return;
      showStatusNotification({
        id: "conversation-fork-error",
        title: "无法创建分支",
        message: error instanceof Error ? error.message : "创建独立聊天分支失败。",
        tone: "error"
      });
    }
  }

  async function forkConversation(atSeq?: number | null) {
    if (currentSessionId) {
      await createFork(currentSessionId, atSeq);
    }
  }

  async function forkConversationFromSidebar(sessionId: string) {
    await createFork(sessionId);
  }
  const { reorderQueuedInputs, deleteQueuedInput, restoreQueuedInputToDraft, runQueuedInputNow } = createConversationQueueActions({
    draftStore: options.draftStore,
    prepareConversationMutation,
    setConversationDetail,
    currentSessionId,
    setConversations,
    conversationDetail,
    isCurrentScope,
    openConversation,
    setComposerError,
    refreshConversations,
    composerText,
    uploadedResources,
    uploadingResources,
    annotatedContexts,
    setComposerText,
    setUploadedResources,
    setAnnotatedContexts,
    onRestoreQueuedInputPreferences,
    clearHighlightedMessage
  });

  return {
    cancelActiveGeneration,
    deleteQueuedInput,
    editMessage,
    forkConversation,
    forkConversationFromSidebar,
    regenerate,
    reorderQueuedInputs,
    restoreQueuedInputToDraft,
    runQueuedInputNow,
    sendMessage,
    showPendingConversationSummary,
    showStreamingTurn,
    startResponseStream,
    submitConversationMessage
  };
}
