import { ConversationWorkspaceSurface } from "./ConversationWorkspaceSurface";
import { useEffect, useLayoutEffect, useRef } from "react";
import { useMembers } from "../members/MemberProvider";

import { apiClient, type AuthSession } from "../../api/client";
import { useConversationAttachments } from "./useConversationAttachments";
import { useConversationLayout } from "./useConversationLayout";
import { useConversationLifecycle } from "./useConversationLifecycle";
import { useConversationMessageActions } from "./useConversationMessageActions";
import { useConversationModelControl } from "./useConversationModelControl";
import { useConversationPageState } from "./useConversationPageState";
import { useConversationViewState } from "./useConversationViewState";
import { useConversationWorkspace } from "./useConversationWorkspace";
import { useFavoriteMessageActions } from "../favorites/useFavoriteMessageActions";
import { useFavoriteWorkspace } from "../favorites/useFavoriteWorkspace";
import { useReportWorkspace } from "../reports/useReportWorkspace";
import {
  APP_PATH,
  REPORTS_PATH,
  chatPathForSession,
  isReportRoute,
  isBodyMetricRoute,
  isMedicalLogRoute,
  medicationRoute,
  memberIdFromHealthPath,
  memberIdFromReportPath,
  reportIdFromReportPath,
  reportPathForReport,
  sessionIdFromChatPath,
  type RoutePath
} from "../../app/routes";
import { useWorkspaceRouteShell } from "../../app/WorkspaceRouteShell";

type UseConversationControllerOptions = {
  route: RoutePath;
  onNavigate: (path: RoutePath, replace?: boolean) => void;
  session: Extract<AuthSession, { authenticated: true }>;
  onSignOut: () => Promise<void>;
};

export function useConversationController({
  route,
  onNavigate,
  session,
  onSignOut
}: UseConversationControllerOptions) {
  const members = useMembers();
  const workspaceShell = useWorkspaceRouteShell();
  const pageState = useConversationPageState();
  const {
    refreshConversations,
    activeScenario,
    activeStreamRef,
    activeStreamTurnId,
    composerError,
    composerModelControlRef,
    composerRef,
    composerText,
    composerTextareaRef,
    conversationDetail,
    conversationRequestSeqRef,
    conversationStageRef,
    conversationSurfaceRef,
    conversations,
    copySuccessTimeoutRef,
    currentSessionId,
    editingMessageContextResources,
    editingMessageId,
    editingMessageInputRef,
    editingMessageText,
    highlightedMessageId,
    highlightedMessageRequestId,
    homeConversationDraftRef,
    messageListRef,
    messageRefs,
    modelCatalog,
    annotatedContexts,
    annotationSelection,
    setActiveScenario,
    setActiveStreamTurnId,
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
    setHighlightedMessageRequestId,
    setModelCatalog,
    refreshModelCatalog,
    setAnnotatedContexts,
    setAnnotationSelection,
    setSending,
    setUploadedResources,
    setUploadingResources,
    uploadedResources,
    uploadingResources,
    visionParseModel
  } = pageState;
  useEffect(() => {
    if (conversationDetail?.access_state === "available") members.adoptConversationMember(conversationDetail.member_id);
  }, [conversationDetail?.session_id, conversationDetail?.member_id, conversationDetail?.access_state]);

  const memberAccessRevision = useRef(members.collection.access_revision);
  useEffect(() => {
    if (memberAccessRevision.current === members.collection.access_revision) return;
    memberAccessRevision.current = members.collection.access_revision;
    let disposed = false;
    const request = new AbortController();
    void refreshConversations(() => !disposed).catch(() => undefined);
    if (currentSessionId) {
      void apiClient.getConversation(currentSessionId, request.signal).then(detail => {
        if (disposed) return;
        setConversationDetail(current => {
          if (current?.session_id !== detail.session_id) return current;
          return {
            ...current, member_id: detail.member_id, member_name: detail.member_name,
            access_state: detail.access_state, resource_states: detail.resource_states,
            fork_available: detail.fork_available
          };
        });
      }).catch(() => undefined);
    }
    return () => { disposed = true; request.abort(); };
  }, [members.collection.access_revision]);

  const hasBackgroundConversationWork = Boolean(activeStreamTurnId || conversationDetail?.pending_turns.length) || conversations.some(
    (conversation) => conversation.pending_turn_status || conversation.queued_input_count > 0
  );

  useEffect(() => {
    if (!hasBackgroundConversationWork) {
      return;
    }
    let pending = false;
    let disposed = false;
    const interval = window.setInterval(() => {
      if (pending) return;
      pending = true;
      void refreshConversations(() => !disposed).catch(() => undefined).finally(() => { pending = false; });
    }, 2500);
    return () => {
      disposed = true;
      window.clearInterval(interval);
    };
  }, [hasBackgroundConversationWork, setConversations]);
  const modelControl = useConversationModelControl({
    composerModelControlRef,
    modelCatalog,
    setComposerError,
    setModelCatalog,
    refreshModelCatalog
  });
  const {
    applyEffectiveThinkingMode,
    chooseSessionModel,
    chooseThinkingMode,
    clearEffectiveThinkingMode,
    preferredThinkingMode,
    resetModelControl,
    selectedModel,
    selectedModelId
  } = modelControl;
  const favoriteWorkspace = useFavoriteWorkspace({
    setComposerError,
    memberCollection: members.collection
  });
  const {
    favorites,
    resetFavoriteWorkspaceState,
    setFavorites
  } = favoriteWorkspace;
  const reportRouteActive = isReportRoute(route);
  const healthRouteActive = Boolean(memberIdFromHealthPath(route));
  const routeSessionId = sessionIdFromChatPath(route);
  const requestedReportId = reportIdFromReportPath(route);
  const requestedMemberId = memberIdFromReportPath(route) ?? memberIdFromHealthPath(route);
  const reportMember = requestedMemberId ? members.collection.members.find(member => member.member_id === requestedMemberId) ?? null : members.activeMember;
  useEffect(() => {
    if (requestedMemberId && reportMember) members.adoptConversationMember(reportMember.member_id);
    if ((reportRouteActive || healthRouteActive) && !reportMember) onNavigate(APP_PATH, true);
  }, [requestedMemberId, reportRouteActive, healthRouteActive, Boolean(reportMember)]);

  useLayoutEffect(() => {
    if (reportRouteActive) {
      setActiveScenario("reports");
      return;
    }
    if (routeSessionId || route === APP_PATH) {
      setActiveScenario("home");
    }
  }, [reportRouteActive, routeSessionId, route, setActiveScenario,]);

  const viewState = useConversationViewState({
    activeScenario,
    conversationDetail,
    selectedModel,
    visionParseModel,
  });
  const reportWorkspace = useReportWorkspace({
    conversationDetail,
    attachmentCapabilities: viewState,
    member: reportMember ?? members.activeMember,
    active: Boolean(reportMember) && (reportRouteActive || healthRouteActive && !isBodyMetricRoute(route) && !isMedicalLogRoute(route) && !medicationRoute(route)),
    favorites,
    onConversationStarted: (sessionId) => {
      setActiveScenario("home");
      workspaceShell.setMobileSidebarOpen(false);
      onNavigate(chatPathForSession(sessionId));
    },
    onReportCleared: () => onNavigate(REPORTS_PATH),
    onReportSelected: (reportId) => {
      if (reportMember) onNavigate(reportPathForReport(reportId, reportMember.member_id));
    },
    requestedReportId,
    setConversationDetail,
    setFavorites,
    selectedModelId,
    thinkingMode: preferredThinkingMode
  });
  const conversationEnabled = conversationDetail?.access_state !== "history_only" && (activeScenario === "home" || activeScenario === "reports");
  const {
    selectedModelFileMimeTypes
  } = viewState;
  const layout = useConversationLayout({
    activeScenario,
    activeStreamTurnId,
    composerError,
    composerRef,
    composerText,
    composerTextareaRef,
    conversationEnabled,
    conversationSessionId: conversationDetail?.session_id ?? null,
    conversationStageRef,
    conversationSurfaceRef,
    highlightedMessageId,
    highlightedMessageRequestId,
    messageListRef,
    messageRefs,
    onClearAnnotationSelection: () => setAnnotationSelection(null),
    annotatedContexts,
    route,
    queuedInputsLength: conversationDetail?.queued_inputs.length ?? 0,
    uploadedResourcesLength: uploadedResources.length,
    uploadingResourcesLength: uploadingResources.length
  });
  const { forceLatest: forceConversationLatest } = layout;
  const {
    toggleFavorite
  } = useFavoriteMessageActions({
    currentSessionId,
    favorites,
    setComposerError,
    setFavorites
  });
  const lifecycle = useConversationLifecycle({
    draftStore: pageState.draftStore,
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
    prepareConversationMutation: layout.prepareMutation,
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
    setMobileSidebarOpen: workspaceShell.setMobileSidebarOpen,
    setModelCatalog,
    refreshModelCatalog,
    setAnnotatedContexts,
    setAnnotationSelection,
    setSending,
    setSidebarCollapsed: workspaceShell.setSidebarCollapsed,
    setUploadedResources,
    setUploadingResources,
    uploadedResources,
    uploadingResources
  });
  const appliedSelectionVersionRef = useRef(members.selectionVersion);
  useLayoutEffect(() => {
    if (appliedSelectionVersionRef.current === members.selectionVersion) return;
    appliedSelectionVersionRef.current = members.selectionVersion;
    lifecycle.resetForMemberSelection();
  }, [members.selectionVersion]);
  const {
    navigateTo,
    openConversation
  } = lifecycle;
  const workspaceActions = useConversationWorkspace({
    draftStore: pageState.draftStore,
    conversationViewRef: lifecycle.conversationViewRef,
    refreshConversations,
    activeScenario,
    activeStreamRef,
    composerText,
    currentSessionId,
    conversationDetail,
    conversationEnabled,
    conversationVisible: route === APP_PATH || sessionIdFromChatPath(route) === currentSessionId && currentSessionId !== null,
    activeReportResource: reportWorkspace.activeReportResource,
    bindActiveReportResource:
      activeScenario === "reports" &&
      reportWorkspace.detailVisible &&
      Boolean(reportWorkspace.selectedReport),
    navigateTo,
    openConversation,
    onBeforeSubmit:
      activeScenario === "reports"
        ? () => {
          lifecycle.startReportConversation();
          return { startNewConversation: true };
        }
        : undefined,
    annotatedContexts,
    selectedModelId,
    setActiveStreamTurnId,
    setCancellingTurnId,
    setComposerError,
    setComposerText,
    setConversations,
    setCurrentSessionId,
    setConversationDetail,
    setEditingMessageId,
    setEditingMessageText,
    setAnnotatedContexts,
    setAnnotationSelection,
    setSending,
    setUploadedResources,
    setUploadingResources,
    onThinkingModeChanged: applyEffectiveThinkingMode,
    onTurnSettled: clearEffectiveThinkingMode,
    onRestoreQueuedInputPreferences: async (modelId, mode) => {
      await chooseSessionModel(modelId);
      chooseThinkingMode(mode);
    },
    thinkingMode: preferredThinkingMode,
    uploadedResources,
    uploadingResources,
    clearHomeConversationDraft: lifecycle.clearHomeConversationDraft,
    clearHighlightedMessage: () => setHighlightedMessageId(null),
    forceConversationLatest,
    prepareConversationMutation: layout.prepareMutation
  });
  const messageActions = useConversationMessageActions({
    copySuccessTimeoutRef,
    editingMessageContextResources,
    editingMessageId,
    editingMessageInputRef,
    editingMessageText,
    messageRefs,
    annotationSelection,
    preserveConversationAnchor: layout.preserveConversationAnchor,
    setComposerError,
    setCopiedMessageId,
    setEditingMessageContextResources,
    setEditingMessageId,
    setEditingMessageText,
    setHighlightedMessageId,
    setAnnotatedContexts,
    setAnnotationSelection,
    editConversationMessage: workspaceActions.editMessage
  });
  const attachments = useConversationAttachments({
    draftStore: pageState.draftStore,
    conversationDetail,
    currentSessionId,
    selectedModelId: selectedModel?.model_id ?? null,
    selectedModelFileMimeTypes,
    attachmentCapabilitiesReady: viewState.attachmentCapabilitiesReady,
    setComposerError,
    setConversationDetail,
    setCurrentSessionId,
    setUploadedResources,
    setUploadingResources,
    uploadedResourcesLength: uploadedResources.length
  });

  function renderConversation(options: {
    composerPlaceholder?: string;
    conversationEnabled?: boolean;
    surfaceMode?: "workspace" | "composer";
    onOpenReport: (reportId: string) => void | Promise<void>;
  }) {
    return <ConversationWorkspaceSurface
      accountId={session.account_id} attachments={attachments} favorites={favorites}
      layout={layout} messageActions={messageActions} modelControl={modelControl}
      onOpenReport={options.onOpenReport} onToggleFavorite={toggleFavorite} pageState={pageState}
      composerPlaceholder={options.composerPlaceholder}
      conversationEnabled={conversationDetail?.access_state !== "history_only" && options.conversationEnabled !== false}
      sidebarToggle={() => workspaceShell.renderSidebarToggle()} surfaceMode={options.surfaceMode}
      viewState={viewState} workspaceActions={workspaceActions}
    />;
  }

  // The application coordinates routes through commands and rendered surfaces.
  // Mutable conversation state and DOM/stream references stay inside this feature.
  return {
    attachments: { uploadFiles: attachments.uploadFiles },
    favoriteWorkspace,
    lifecycle: {
      batchDeleteConversationsFromSidebar: lifecycle.batchDeleteConversationsFromSidebar,
      batchPinConversationsFromSidebar: lifecycle.batchPinConversationsFromSidebar,
      deleteConversationFromSidebar: lifecycle.deleteConversationFromSidebar,
      navigateTo: lifecycle.navigateTo,
      openConversation: lifecycle.openConversation,
      openConversationFromSidebar: lifecycle.openConversationFromSidebar,
      renameConversationFromSidebar: lifecycle.renameConversationFromSidebar,
      startConversation: lifecycle.startConversation,
      setConversationPinnedFromSidebar: lifecycle.setConversationPinnedFromSidebar,
      openFavoriteSourceConversation: lifecycle.openFavoriteSourceConversation,
      signOut: lifecycle.signOut,
    },
    pageState: {
      composerError, activeScenario, currentSessionId, conversationDetail,
      conversations, conversationPagination: pageState.conversationPagination, modelCatalog,
    },
    catalogActions: { update: setModelCatalog, refresh: refreshModelCatalog },
    reportError: (message: string) => setComposerError(message),
    enterReports: () => setActiveScenario("reports"),
    renderConversation,
    reportWorkspace,
    route,
    session,
    workspaceActions: {
      submitConversationMessage: workspaceActions.submitConversationMessage,
      forkConversationFromSidebar: workspaceActions.forkConversationFromSidebar,
    },
    workspaceShell
  };
}
