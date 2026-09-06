import {
  useEffect,
  useRef,
  type Dispatch,
  type MutableRefObject,
  type SetStateAction,
} from "react";
import {
  apiClient,
  type ConversationDetail,
  type ConversationSummary,
  type Favorite,
  type UploadedResource
} from "../../api/client";
import {
  APP_PATH,
  SIGN_IN_PATH,
  chatPathForSession,
  sessionIdFromChatPath,
  type RoutePath
} from "../../app/routes";
import { useActiveScope } from "../../utils/useActiveScope";
import { emptyModelCatalog, fetchModelCatalog, type ModelCatalog } from "../modelConfiguration/modelCatalog";
import type { UploadingResource } from "./contextResources";
import { createConversationListActions } from './conversationListActions';
import type { HomeConversationDraft } from "./useConversationPageState";
import type {
  ActiveStream,
  AnnotatedContext,
  AnnotationSelection,
  ScenarioTab
} from "./workspaceTypes";

type ConversationLifecycleOptions = {
  refreshConversations: (isRelevant?: () => boolean) => Promise<void>;
  activeScenario: ScenarioTab;
  activeStreamRef: MutableRefObject<ActiveStream | null>;
  composerText: string;
  conversationDetail: ConversationDetail | null;
  conversationRequestSeqRef: MutableRefObject<number>;
  currentSessionId: string | null;
  homeConversationDraftRef: MutableRefObject<HomeConversationDraft | null>;
  onNavigate: (path: RoutePath, replace?: boolean) => void;
  onSignOut: () => Promise<void>;
  prepareConversationMutation: (key: string) => void;
  annotatedContexts: AnnotatedContext[];
  annotationSelection: AnnotationSelection | null;
  resetFavoriteWorkspaceState: () => void;
  resetModelControl: () => void;
  route: RoutePath;
  setActiveScenario: Dispatch<SetStateAction<ScenarioTab>>;
  setActiveStreamTurnId: Dispatch<SetStateAction<string | null>>;
  setCancellingTurnId: Dispatch<SetStateAction<string | null>>;
  setComposerError: Dispatch<SetStateAction<string>>;
  setComposerText: Dispatch<SetStateAction<string>>;
  setConversationDetail: Dispatch<SetStateAction<ConversationDetail | null>>;
  setConversations: Dispatch<SetStateAction<ConversationSummary[]>>;
  setCurrentSessionId: Dispatch<SetStateAction<string | null>>;
  setEditingMessageId: Dispatch<SetStateAction<string | null>>;
  setEditingMessageText: Dispatch<SetStateAction<string>>;
  setFavorites: Dispatch<SetStateAction<Favorite[]>>;
  setHighlightedMessageId: Dispatch<SetStateAction<string | null>>;
  setHighlightedMessageRequestId: Dispatch<SetStateAction<number>>;
  setMobileSidebarOpen: Dispatch<SetStateAction<boolean>>;
  setModelCatalog: Dispatch<SetStateAction<ModelCatalog>>;
  setAnnotatedContexts: Dispatch<SetStateAction<AnnotatedContext[]>>;
  setAnnotationSelection: Dispatch<SetStateAction<AnnotationSelection | null>>;
  setSending: Dispatch<SetStateAction<boolean>>;
  setSidebarCollapsed: Dispatch<SetStateAction<boolean>>;
  setUploadedResources: Dispatch<SetStateAction<UploadedResource[]>>;
  setUploadingResources: Dispatch<SetStateAction<UploadingResource[]>>;
  uploadedResources: UploadedResource[];
  uploadingResources: UploadingResource[];
};

export function useConversationLifecycle(options: ConversationLifecycleOptions) {
  const isCurrentScope = useActiveScope(options.route);
  const {
    refreshConversations,
    activeScenario,
    activeStreamRef,
    composerText,
    conversationDetail,
    conversationRequestSeqRef,
    currentSessionId,
    homeConversationDraftRef,
    onNavigate,
    onSignOut,
    prepareConversationMutation,
    annotatedContexts,
    annotationSelection,
    resetFavoriteWorkspaceState,
    resetModelControl,
    route,
    setActiveScenario,
    setActiveStreamTurnId,
    setCancellingTurnId,
    setComposerError,
    setComposerText,
    setConversationDetail,
    setConversations,
    setCurrentSessionId,
    setEditingMessageId,
    setEditingMessageText,
    setFavorites,
    setHighlightedMessageId,
    setHighlightedMessageRequestId,
    setMobileSidebarOpen,
    setModelCatalog,
    setAnnotatedContexts,
    setAnnotationSelection,
    setSending,
    setSidebarCollapsed,
    setUploadedResources,
    setUploadingResources,
    uploadedResources,
    uploadingResources
  } = options;
  const visibleConversationRef = useRef({ currentSessionId, conversationDetail });
  // Starting another draft can leave the URL and session ID unchanged.
  const conversationViewRef = useRef(0);
  const detailRequestRef = useRef<AbortController | null>(null);
  visibleConversationRef.current = { currentSessionId, conversationDetail };

  useEffect(() => () => { detailRequestRef.current?.abort(); }, []);

  useEffect(() => {
    void loadWorkspaceData().catch((error) => {
      const detail = error instanceof Error && error.message
        ? error.message
        : "工作区初始化失败。";
      setComposerError(
        detail.includes("UNSUPPORTED_SCHEMA")
          ? `${detail} 当前数据目录不属于本版本；后端不会自动迁移或改写旧数据。请停止后端，设置 DATA_ROOT 指向空目录后重新启动。`
          : detail
      );
    });
  }, []);

  useEffect(() => {
    const routeSessionId = sessionIdFromChatPath(route);
    detachVisibleStream(routeSessionId);
    if (!routeSessionId || routeSessionId === currentSessionId) {
      return;
    }
    void openConversation(routeSessionId).catch((error) => {
      setCurrentSessionId(null);
      setConversationDetail(null);
      setComposerError(error instanceof Error ? error.message : "聊天加载失败。");
    });
  }, [currentSessionId, route]);

  function hasConversationActivity(detail: ConversationDetail | null) {
    return Boolean(detail?.records.length || detail?.pending_turns.length);
  }

  function hasHomeConversationDraftContent(draft: HomeConversationDraft) {
    return Boolean(
      draft.composerText.trim() ||
      draft.uploadedResources.length ||
      draft.uploadingResources.length ||
      draft.annotatedContexts.length
    );
  }

  function isHomeConversationDraftContext() {
    return (
      activeScenario === "home" &&
      (
        currentSessionId === null ||
        !conversationDetail ||
        (
          conversationDetail.session_id === currentSessionId &&
          !hasConversationActivity(conversationDetail)
        )
      )
    );
  }

  function saveHomeConversationDraft() {
    if (!isHomeConversationDraftContext()) {
      return;
    }
    const draft: HomeConversationDraft = {
      currentSessionId,
      conversationDetail,
      composerText,
      annotatedContexts: [...annotatedContexts],
      annotationSelection,
      uploadedResources: [...uploadedResources],
      uploadingResources: [...uploadingResources]
    };
    homeConversationDraftRef.current = hasHomeConversationDraftContent(draft) ? draft : null;
  }

  function clearHomeConversationDraft() {
    homeConversationDraftRef.current = null;
  }

  function clearActiveComposerDraft() {
    conversationViewRef.current += 1;
    setSending(false);
    setComposerText("");
    setUploadingResources([]);
    setUploadedResources([]);
    setAnnotatedContexts([]);
    setAnnotationSelection(null);
    setHighlightedMessageId(null);
    setHighlightedMessageRequestId(0);
    setEditingMessageId(null);
    setEditingMessageText("");
  }

  function restoreHomeConversationDraft() {
    const draft = homeConversationDraftRef.current;
    if (!draft) {
      return false;
    }
    setCurrentSessionId(draft.currentSessionId);
    setConversationDetail(draft.conversationDetail);
    setComposerText(draft.composerText);
    setUploadingResources([...draft.uploadingResources]);
    setUploadedResources([...draft.uploadedResources]);
    setAnnotatedContexts([...draft.annotatedContexts]);
    setAnnotationSelection(draft.annotationSelection);
    setHighlightedMessageId(null);
    setHighlightedMessageRequestId(0);
    setEditingMessageId(null);
    setEditingMessageText("");
    setComposerError("");
    return true;
  }

  function navigateTo(path: RoutePath, replace = false) {
    detailRequestRef.current?.abort();
    conversationViewRef.current += 1;
    setSending(false);
    conversationRequestSeqRef.current += 1;
    if (path !== APP_PATH && path !== SIGN_IN_PATH) {
      saveHomeConversationDraft();
    }
    detachVisibleStream(sessionIdFromChatPath(path));
    setMobileSidebarOpen(false);
    onNavigate(path, replace);
  }

  async function loadWorkspaceData() {
    await Promise.all([
      refreshConversations(),
      apiClient.fetchFavorites().then((response) => setFavorites(response.favorites)),
      fetchModelCatalog().then(setModelCatalog).catch(error => {
        const message = error instanceof Error ? error.message : "模型配置读取失败。";
        setModelCatalog(current => ({ ...current, status: "error", error: message }));
        setComposerError(message);
      })
    ]);
  }

  function resetWorkspaceState() {
    conversationRequestSeqRef.current += 1;
    clearHomeConversationDraft();
    activeStreamRef.current?.abortController.abort();
    activeStreamRef.current = null;
    setActiveScenario("home");
    setComposerText("");
    setComposerError("");
    setSending(false);
    setActiveStreamTurnId(null);
    setCancellingTurnId(null);
    setMobileSidebarOpen(false);
    setSidebarCollapsed(false);
    setCurrentSessionId(null);
    setConversationDetail(null);
    setConversations([]);
    resetFavoriteWorkspaceState();
    setModelCatalog(emptyModelCatalog());
    resetModelControl();
    setUploadingResources([]);
    setUploadedResources([]);
    setAnnotatedContexts([]);
    setAnnotationSelection(null);
    setHighlightedMessageId(null);
    setHighlightedMessageRequestId(0);
    setEditingMessageId(null);
    setEditingMessageText("");
  }

  function resetForMemberSelection() {
    conversationRequestSeqRef.current += 1;
    clearHomeConversationDraft();
    detachVisibleStream(null);
    setActiveScenario("home");
    setComposerError("");
    setSending(false);
    setActiveStreamTurnId(null);
    setCancellingTurnId(null);
    setMobileSidebarOpen(false);
    setCurrentSessionId(null);
    setConversationDetail(null);
    resetModelControl();
    clearActiveComposerDraft();
  }

  async function openConversation(sessionId: string, sourceMessageId: string | null = null) {
    const visible = visibleConversationRef.current;
    const switchingConversation =
      visible.currentSessionId !== sessionId || visible.conversationDetail?.session_id !== sessionId;
    if (switchingConversation) {
      saveHomeConversationDraft();
      detachVisibleStream(sessionId);
    }
    const requestId = conversationRequestSeqRef.current + 1;
    conversationRequestSeqRef.current = requestId;
    detailRequestRef.current?.abort();
    const request = new AbortController();
    detailRequestRef.current = request;
    let detail: ConversationDetail;
    try {
      detail = await apiClient.getConversation(sessionId, request.signal);
    } catch (error) {
      if (!isCurrentScope() || requestId !== conversationRequestSeqRef.current) {
        return false;
      }
      throw error;
    }
    if (!isCurrentScope() || requestId !== conversationRequestSeqRef.current) {
      return false;
    }
    setCurrentSessionId(sessionId);
    if (!switchingConversation) {
      prepareConversationMutation(`conversation-refresh:${sessionId}:${requestId}`);
    }
    setConversationDetail(detail);
    setComposerError("");
    if (switchingConversation) {
      clearActiveComposerDraft();
      setActiveScenario("home");
      setHighlightedMessageId(sourceMessageId);
    } else if (sourceMessageId !== null) {
      setHighlightedMessageId(sourceMessageId);
    }
    if (sourceMessageId !== null) {
      setHighlightedMessageRequestId((current) => current + 1);
    }
    return true;
  }

  function detachVisibleStream(nextSessionId: string | null) {
    const activeStream = activeStreamRef.current;
    if (!activeStream || activeStream.sessionId === nextSessionId) {
      return;
    }
    activeStreamRef.current = null;
    activeStream.abortController.abort();
    setActiveStreamTurnId(null);
    setCancellingTurnId(null);
  }

  async function openFavoriteSourceConversation(sessionId: string, sourceMessageId: string) {
    const opened = await openConversation(sessionId, sourceMessageId);
    if (opened) navigateTo(chatPathForSession(sessionId));
  }

  async function openConversationFromSidebar(sessionId: string) {
    navigateTo(chatPathForSession(sessionId));
    // The route effect owns the detail read; issuing another here queues two
    // copies of the same request and immediately makes the first one stale.
    if (sessionIdFromChatPath(route) === sessionId) await openConversation(sessionId);
  }

  async function signOut() {
    try {
      await onSignOut();
    } finally {
      resetWorkspaceState();
      navigateTo(SIGN_IN_PATH);
    }
  }

  function startConversation() {
    conversationRequestSeqRef.current += 1;
    const shouldRestoreDraft = !(route === APP_PATH && isHomeConversationDraftContext());
    if (shouldRestoreDraft) {
      saveHomeConversationDraft();
    }
    navigateTo(APP_PATH);
    setActiveScenario("home");
    if (shouldRestoreDraft && restoreHomeConversationDraft()) {
      return;
    }
    clearHomeConversationDraft();
    setCurrentSessionId(null);
    setConversationDetail(null);
    clearActiveComposerDraft();
    setComposerError("");
  }

  function startReportConversation() {
    conversationRequestSeqRef.current += 1;
    saveHomeConversationDraft();
    navigateTo(APP_PATH);
    setActiveScenario("home");
    setCurrentSessionId(null);
    setConversationDetail(null);
    clearActiveComposerDraft();
    setComposerError("");
  }
  const {
    deleteConversationFromSidebar,
    renameConversationFromSidebar,
    setConversationPinnedFromSidebar,
    batchPinConversationsFromSidebar,
    batchDeleteConversationsFromSidebar
  } = createConversationListActions({
    refreshConversations,
    setConversations,
    setComposerError,
    visibleConversationRef,
    currentSessionId,
    isCurrentScope,
    setConversationDetail,
    setCurrentSessionId,
    setUploadingResources,
    setUploadedResources,
    setAnnotatedContexts,
    setAnnotationSelection,
    route,
    navigateTo
  });

  return {
    conversationViewRef,
    batchDeleteConversationsFromSidebar,
    batchPinConversationsFromSidebar,
    clearHomeConversationDraft,
    deleteConversationFromSidebar,
    navigateTo,
    openConversation,
    openConversationFromSidebar,
    openFavoriteSourceConversation,
    renameConversationFromSidebar,
    resetForMemberSelection,
    resetWorkspaceState,
    setConversationPinnedFromSidebar,
    signOut,
    startConversation,
    startReportConversation,
  };
}
