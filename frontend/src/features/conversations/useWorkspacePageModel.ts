import type { AuthSession } from "../../api/client";
import {
  FAVORITES_PATH,
  type RoutePath
} from "../../app/routes";
import { useWorkspaceRouteShell } from "../../app/WorkspaceRouteShell";
import { useFavoriteListAlignment } from "../favorites/useFavoriteListAlignment";
import { useFavoriteMessageActions } from "../favorites/useFavoriteMessageActions";
import { useFavoriteWorkspace } from "../favorites/useFavoriteWorkspace";
import { useConversationAttachments } from "./useConversationAttachments";
import { useConversationBranching } from "./useConversationBranching";
import { useConversationLayout } from "./useConversationLayout";
import { useConversationLifecycle } from "./useConversationLifecycle";
import { useConversationMessageActions } from "./useConversationMessageActions";
import { useConversationModelControl } from "./useConversationModelControl";
import { useConversationPageState } from "./useConversationPageState";
import { useConversationViewState } from "./useConversationViewState";
import { useConversationWorkspace } from "./useConversationWorkspace";

type UseWorkspacePageModelOptions = {
  route: RoutePath;
  onNavigate: (path: RoutePath, replace?: boolean) => void;
  session: Extract<AuthSession, { authenticated: true }>;
  onSignOut: () => Promise<void>;
};

export function useWorkspacePageModel({
  route,
  onNavigate,
  session,
  onSignOut
}: UseWorkspacePageModelOptions) {
  const workspaceShell = useWorkspaceRouteShell();
  const pageState = useConversationPageState();
  const {
    activeScenario,
    activeStreamRef,
    activeStreamTurnId,
    activeView,
    composerError,
    composerModelControlRef,
    composerRef,
    composerText,
    composerTextareaRef,
    conversationDetail,
    conversationRequestSeqRef,
    conversationStageRef,
    conversationSurfaceRef,
    copySuccessTimeoutRef,
    currentSessionId,
    editingMessageContextResources,
    editingMessageId,
    editingMessageInputRef,
    editingMessageText,
    highlightedMessageId,
    homeConversationDraftRef,
    messageListRef,
    messageRefs,
    models,
    parentForNextMessage,
    quotedContext,
    quoteSelection,
    setActiveScenario,
    setActiveStreamTurnId,
    setActiveView,
    setActivelyThinkingTurnId,
    setCancellingTurnId,
    setComposerError,
    setComposerText,
    setConversationDetail,
    setConversations,
    setCopiedMessageId,
    setCurrentSessionId,
    setEditingMessageContextResources,
    setEditingMessageId,
    setEditingMessageText,
    setHighlightedMessageId,
    setModels,
    setParentForNextMessage,
    setQuoteSelection,
    setQuotedContext,
    setSending,
    setUploadedResources,
    setVisionParseModel,
    setUploadingResources,
    uploadedResources,
    uploadingResources,
    visionParseModel
  } = pageState;
  const modelControl = useConversationModelControl({
    composerModelControlRef,
    models,
    setComposerError,
    setModels,
    setVisionParseModel
  });
  const {
    resetModelControl,
    selectedModel,
    selectedModelId,
    thinkingMode
  } = modelControl;
  const viewState = useConversationViewState({
    activeScenario,
    conversationDetail,
    parentForNextMessage,
    selectedModel,
    visionParseModel,
  });
  const {
    allMessages,
    messages,
    messagesById,
    selectedModelFileMimeTypes
  } = viewState;
  const layout = useConversationLayout({
    activeScenario,
    activeStreamTurnId,
    activeView,
    composerError,
    composerRef,
    composerText,
    composerTextareaRef,
    conversationSessionId: conversationDetail?.session_id ?? null,
    conversationStageRef,
    conversationSurfaceRef,
    highlightedMessageId,
    messageListRef,
    messageRefs,
    messages,
    onClearQuoteSelection: () => setQuoteSelection(null),
    parentForNextMessage,
    quotedContext,
    route,
    uploadedResourcesLength: uploadedResources.length,
    uploadingResourcesLength: uploadingResources.length
  });
  const {
    markConversationTailShouldFollow
  } = layout;
  const favoriteWorkspace = useFavoriteWorkspace({
    setComposerError
  });
  const {
    favorites,
    resetFavoriteWorkspaceState,
    setFavorites
  } = favoriteWorkspace;
  useFavoriteListAlignment({
    active: route === FAVORITES_PATH,
    favoriteDetailId: favoriteWorkspace.favoriteDetail?.favorite_id ?? null,
    favoriteListPanelRef: favoriteWorkspace.favoriteListPanelRef,
    favoriteListRef: favoriteWorkspace.favoriteListRef,
    favoriteSelectionMode: favoriteWorkspace.favoriteSelectionMode,
    favoritesLength: favoriteWorkspace.favorites.length
  });
  const {
    toggleFavorite
  } = useFavoriteMessageActions({
    currentSessionId,
    favorites,
    setComposerError,
    setFavorites
  });
  const lifecycle = useConversationLifecycle({
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
    setMobileSidebarOpen: workspaceShell.setMobileSidebarOpen,
    setModels,
    setParentForNextMessage,
    setQuoteSelection,
    setQuotedContext,
    setSending,
    setSidebarCollapsed: workspaceShell.setSidebarCollapsed,
    setUploadedResources,
    setVisionParseModel,
    setUploadingResources,
    uploadedResources,
    uploadingResources
  });
  const {
    navigateTo,
    openConversation
  } = lifecycle;
  const workspaceActions = useConversationWorkspace({
    activeScenario,
    activeStreamRef,
    composerText,
    currentSessionAccount: session.account,
    currentSessionId,
    conversationDetail,
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
    setComposerError,
    setComposerText,
    setConversations,
    setCurrentSessionId,
    setConversationDetail,
    setEditingMessageId,
    setEditingMessageText,
    setParentForNextMessage,
    setQuoteSelection,
    setQuotedContext,
    setSending,
    setUploadedResources,
    setUploadingResources,
    thinkingMode,
    uploadedResources,
    clearHomeConversationDraft: lifecycle.clearHomeConversationDraft,
    markConversationTailShouldFollow
  });
  const {
    submitConversationMessage
  } = workspaceActions;
  const messageActions = useConversationMessageActions({
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
  });
  const branching = useConversationBranching({
    allMessages,
    conversationDetail,
    currentSessionId,
    messagesById,
    openConversation,
    setComposerText,
    setParentForNextMessage
  });
  const attachments = useConversationAttachments({
    conversationDetail,
    currentSessionId,
    selectedModelId: selectedModel?.model_id ?? null,
    selectedModelFileMimeTypes,
    setComposerError,
    setConversationDetail,
    setCurrentSessionId,
    setUploadedResources,
    setUploadingResources,
    uploadedResourcesLength: uploadedResources.length
  });

  return {
    attachments,
    branching,
    favoriteWorkspace,
    favorites,
    layout,
    lifecycle,
    messageActions,
    modelControl,
    onToggleFavorite: toggleFavorite,
    pageState,
    route,
    session,
    viewState,
    workspaceActions,
    workspaceShell
  };
}
