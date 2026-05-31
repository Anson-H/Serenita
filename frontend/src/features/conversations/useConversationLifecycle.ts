import {
  type Dispatch,
  type MutableRefObject,
  type RefObject,
  type SetStateAction,
  useEffect,
} from "react";

import {
  type AddedModel,
  type ConversationDetail,
  type ConversationSummary,
  type Favorite,
  type UploadedResource,
  apiClient
} from "../../api/client";
import {
  APP_PATH,
  FAVORITES_PATH,
  SIGN_IN_PATH,
  chatPathForSession,
  sessionIdFromChatPath,
  type RoutePath
} from "../../app/routes";
import type { UploadingResource } from "./contextResources";
import { mergeModelsWithChatDefault } from "./conversationModels";
import type { HomeConversationDraft } from "./useConversationPageState";
import type {
  ActiveStream,
  QuoteSelection,
  QuotedContext,
  ScenarioTab,
  WorkspaceView
} from "./workspaceTypes";

type ConversationLifecycleOptions = {
  activeScenario: ScenarioTab;
  activeStreamRef: MutableRefObject<ActiveStream | null>;
  activeView: WorkspaceView;
  composerText: string;
  conversationDetail: ConversationDetail | null;
  conversationRequestSeqRef: MutableRefObject<number>;
  conversationSurfaceRef: RefObject<HTMLDivElement | null>;
  currentSessionId: string | null;
  homeConversationDraftRef: MutableRefObject<HomeConversationDraft | null>;
  onNavigate: (path: RoutePath, replace?: boolean) => void;
  onSignOut: () => Promise<void>;
  parentForNextMessage: string | null | undefined;
  quotedContext: QuotedContext | null;
  quoteSelection: QuoteSelection | null;
  resetFavoriteWorkspaceState: () => void;
  resetModelControl: () => void;
  route: RoutePath;
  setActiveScenario: Dispatch<SetStateAction<ScenarioTab>>;
  setActiveStreamTurnId: Dispatch<SetStateAction<string | null>>;
  setActiveView: Dispatch<SetStateAction<WorkspaceView>>;
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
  setMobileSidebarOpen: Dispatch<SetStateAction<boolean>>;
  setModels: Dispatch<SetStateAction<AddedModel[]>>;
  setParentForNextMessage: Dispatch<SetStateAction<string | null | undefined>>;
  setQuoteSelection: Dispatch<SetStateAction<QuoteSelection | null>>;
  setQuotedContext: Dispatch<SetStateAction<QuotedContext | null>>;
  setSending: Dispatch<SetStateAction<boolean>>;
  setSidebarCollapsed: Dispatch<SetStateAction<boolean>>;
  setUploadedResources: Dispatch<SetStateAction<UploadedResource[]>>;
  setVisionParseModel: Dispatch<SetStateAction<AddedModel | null>>;
  setUploadingResources: Dispatch<SetStateAction<UploadingResource[]>>;
  uploadedResources: UploadedResource[];
  uploadingResources: UploadingResource[];
};

export function useConversationLifecycle(options: ConversationLifecycleOptions) {
  const {
    activeScenario,
    activeStreamRef,
    activeView,
    composerText,
    conversationDetail,
    conversationRequestSeqRef,
    conversationSurfaceRef,
    currentSessionId,
    homeConversationDraftRef,
    onNavigate,
    onSignOut,
    parentForNextMessage,
    quotedContext,
    quoteSelection,
    resetFavoriteWorkspaceState,
    resetModelControl,
    route,
    setActiveScenario,
    setActiveStreamTurnId,
    setActiveView,
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
    setMobileSidebarOpen,
    setModels,
    setParentForNextMessage,
    setQuoteSelection,
    setQuotedContext,
    setSending,
    setSidebarCollapsed,
    setUploadedResources,
    setVisionParseModel,
    setUploadingResources,
    uploadedResources,
    uploadingResources
  } = options;

  useEffect(() => {
    void loadWorkspaceData();
  }, []);

  useEffect(() => {
    const routeSessionId = sessionIdFromChatPath(route);
    if (!routeSessionId || routeSessionId === currentSessionId) {
      return;
    }
    void openConversation(routeSessionId).catch((error) => {
      setCurrentSessionId(null);
      setConversationDetail(null);
      setComposerError(error instanceof Error ? error.message : "会话加载失败。");
    });
  }, [currentSessionId, route]);

  function hasConversationActivity(detail: ConversationDetail | null) {
    return Boolean(detail?.messages.length || detail?.all_messages?.length || detail?.pending_turns.length);
  }

  function hasHomeConversationDraftContent(draft: HomeConversationDraft) {
    return Boolean(
      draft.composerText.trim() ||
        draft.uploadedResources.length ||
        draft.uploadingResources.length ||
        draft.quotedContext
    );
  }

  function isHomeConversationDraftContext() {
    return (
      activeView === "home" &&
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
      parentForNextMessage,
      quotedContext,
      quoteSelection,
      uploadedResources: [...uploadedResources],
      uploadingResources: [...uploadingResources]
    };
    homeConversationDraftRef.current = hasHomeConversationDraftContent(draft) ? draft : null;
  }

  function clearHomeConversationDraft() {
    homeConversationDraftRef.current = null;
  }

  function clearActiveComposerDraft() {
    setComposerText("");
    setUploadingResources([]);
    setUploadedResources([]);
    setQuotedContext(null);
    setQuoteSelection(null);
    setParentForNextMessage(undefined);
    setHighlightedMessageId(null);
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
    setQuotedContext(draft.quotedContext);
    setQuoteSelection(draft.quoteSelection);
    setParentForNextMessage(draft.parentForNextMessage);
    setHighlightedMessageId(null);
    setEditingMessageId(null);
    setEditingMessageText("");
    setComposerError("");
    return true;
  }

  function navigateTo(path: RoutePath, replace = false) {
    if (path !== APP_PATH && path !== SIGN_IN_PATH) {
      saveHomeConversationDraft();
    }
    setMobileSidebarOpen(false);
    onNavigate(path, replace);
  }

  async function loadWorkspaceData() {
    const [conversationResponse, favoriteResponse, modelResponse, defaultsResponse] = await Promise.all([
      apiClient.fetchConversations(),
      apiClient.fetchFavorites(),
      apiClient.fetchModels(),
      apiClient.fetchModelDefaults().catch(() => null)
    ]);
    setConversations(conversationResponse.sessions);
    setFavorites(favoriteResponse.favorites);
    setModels(mergeModelsWithChatDefault(modelResponse.models, defaultsResponse?.defaults.chat ?? null));
    setVisionParseModel(defaultsResponse?.defaults.vision_parse ?? null);
    const routeSessionId = sessionIdFromChatPath(route);
    if (routeSessionId) {
      await openConversation(routeSessionId);
      return;
    }
    if (conversationResponse.sessions[0] && !currentSessionId) {
      await openConversation(conversationResponse.sessions[0].session_id);
    }
  }

  function resetWorkspaceState() {
    conversationRequestSeqRef.current += 1;
    clearHomeConversationDraft();
    activeStreamRef.current?.abortController.abort();
    activeStreamRef.current = null;
    setActiveView("home");
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
    setModels([]);
    setVisionParseModel(null);
    resetModelControl();
    setUploadingResources([]);
    setUploadedResources([]);
    setParentForNextMessage(undefined);
    setQuotedContext(null);
    setQuoteSelection(null);
    setHighlightedMessageId(null);
    setEditingMessageId(null);
    setEditingMessageText("");
  }

  async function openConversation(sessionId: string, sourceMessageId: string | null = null) {
    saveHomeConversationDraft();
    const requestId = conversationRequestSeqRef.current + 1;
    conversationRequestSeqRef.current = requestId;
    let detail: ConversationDetail;
    try {
      detail = await apiClient.getConversation(sessionId);
    } catch (error) {
      if (requestId !== conversationRequestSeqRef.current) {
        return false;
      }
      throw error;
    }
    if (requestId !== conversationRequestSeqRef.current) {
      return false;
    }
    conversationSurfaceRef.current?.scrollTo({ top: 0, behavior: "auto" });
    setCurrentSessionId(sessionId);
    setConversationDetail(detail);
    clearActiveComposerDraft();
    setComposerError("");
    setActiveView("home");
    setActiveScenario("home");
    setHighlightedMessageId(sourceMessageId);
    return true;
  }

  async function openFavoriteSourceConversation(sessionId: string, sourceMessageId: string) {
    await openConversation(sessionId, sourceMessageId);
    navigateTo(chatPathForSession(sessionId));
  }

  async function openConversationFromSidebar(sessionId: string) {
    navigateTo(chatPathForSession(sessionId));
    await openConversation(sessionId);
  }

  async function signOut() {
    try {
      await onSignOut();
    } finally {
      resetWorkspaceState();
      navigateTo(SIGN_IN_PATH);
    }
  }

  function switchView(view: WorkspaceView) {
    if (view !== "home") {
      saveHomeConversationDraft();
    }
    setMobileSidebarOpen(false);
    setActiveView(view);
    setComposerError("");
  }

  function changeScenario(scenario: ScenarioTab) {
    if (scenario !== "home") {
      saveHomeConversationDraft();
    }
    setActiveScenario(scenario);
    setComposerError("");
  }

  function startConversation() {
    conversationRequestSeqRef.current += 1;
    const shouldRestoreDraft = !(route === APP_PATH && isHomeConversationDraftContext());
    if (shouldRestoreDraft) {
      saveHomeConversationDraft();
    }
    navigateTo(APP_PATH);
    setActiveView("home");
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

  async function deleteConversationFromSidebar(sessionId: string) {
    try {
      await apiClient.deleteConversation(sessionId);
      if (sessionId === currentSessionId) {
        setConversationDetail(null);
        setCurrentSessionId(null);
        setUploadingResources([]);
        setUploadedResources([]);
        setQuotedContext(null);
        setQuoteSelection(null);
        setParentForNextMessage(undefined);
        if (route !== FAVORITES_PATH) {
          navigateTo(APP_PATH);
        }
      }
      const conversationResponse = await apiClient.fetchConversations();
      setConversations(conversationResponse.sessions);
      setComposerError("");
    } catch (error) {
      setComposerError(error instanceof Error ? error.message : "删除会话失败。");
    }
  }

  return {
    changeScenario,
    clearHomeConversationDraft,
    deleteConversationFromSidebar,
    navigateTo,
    openConversation,
    openConversationFromSidebar,
    openFavoriteSourceConversation,
    resetWorkspaceState,
    signOut,
    startConversation,
    switchView
  };
}
