import type * as React from "react";
import { captureAuthContext, isAuthContextCurrent, type AuthContext } from "../../api/authLifecycle";
import {
  type Dispatch,
  type SetStateAction
} from "react";
import {
  apiClient,
  type ConversationDetail,
  type ConversationSummary,
  type UploadedResource
} from "../../api/client";
import {
  APP_PATH,
  FAVORITES_PATH,
  type RoutePath
} from "../../app/routes";
import { showStatusNotification } from "../../components/StatusNotificationCenter";
import type { UploadingResource } from "./contextResources";
import { compareConversationSummaries } from './conversationSummaryOrder';
import type {
  AnnotatedContext,
  AnnotationSelection
} from "./workspaceTypes";

type Dependencies = {
  onDeletedSessions: (sessionIds: string[]) => void;
  refreshConversations: () => Promise<void>;
  setConversations: Dispatch<SetStateAction<ConversationSummary[]>>;
  setComposerError: Dispatch<SetStateAction<string>>;
  visibleConversationRef: React.RefObject<{ currentSessionId: string | null; conversationDetail: ConversationDetail | null; }>;
  currentSessionId: string | null;
  isCurrentScope: () => boolean;
  setConversationDetail: Dispatch<SetStateAction<ConversationDetail | null>>;
  setCurrentSessionId: Dispatch<SetStateAction<string | null>>;
  setUploadingResources: Dispatch<SetStateAction<UploadingResource[]>>;
  setUploadedResources: Dispatch<SetStateAction<UploadedResource[]>>;
  setAnnotatedContexts: Dispatch<SetStateAction<AnnotatedContext[]>>;
  setAnnotationSelection: Dispatch<SetStateAction<AnnotationSelection | null>>;
  route: RoutePath;
  navigateTo: (path: RoutePath, replace?: boolean) => void;
};

export function createConversationListActions({
  onDeletedSessions,
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
}: Dependencies) {
  async function deleteConversationFromSidebar(sessionId: string) {
    const auth = captureAuthContext();
    try {
      await apiClient.deleteConversation(sessionId);
      clearDeletedCurrentConversation([sessionId], auth);
      await refreshConversations();
      setComposerError("");
      showStatusNotification({
        id: "conversation-delete-success",
        message: "聊天已删除。",
        tone: "success"
      });
      return true;
    } catch (error) {
      setComposerError(error instanceof Error ? error.message : "删除聊天失败。");
      return false;
    }
  }

  function clearDeletedCurrentConversation(deletedIds: string[], auth: AuthContext) {
    if (!isAuthContextCurrent(auth)) return;
    onDeletedSessions(deletedIds);
    const visibleSessionId = visibleConversationRef.current.currentSessionId;
    if (!isCurrentScope() || !visibleSessionId || !deletedIds.includes(visibleSessionId)) {
      return;
    }
    setConversationDetail(null);
    setCurrentSessionId(null);
    setUploadingResources([]);
    setUploadedResources([]);
    setAnnotatedContexts([]);
    setAnnotationSelection(null);
    if (route !== FAVORITES_PATH) {
      navigateTo(APP_PATH);
    }
  }

  function mergeConversationSummaries(updatedSessions: ConversationSummary[]) {
    const updatedById = new Map(
      updatedSessions.map((session) => [session.session_id, session])
    );
    setConversations((current) => current
      .map((session) => updatedById.get(session.session_id) ?? session)
      .sort(compareConversationSummaries));
  }

  async function renameConversationFromSidebar(sessionId: string, title: string) {
    try {
      const response = await apiClient.updateConversation(sessionId, { title });
      mergeConversationSummaries([response.session]);
      if (sessionId === currentSessionId) {
        setConversationDetail((current) => current?.session_id === sessionId
          ? { ...current, title: response.session.title }
          : current);
      }
      setComposerError("");
      return true;
    } catch (error) {
      setComposerError(error instanceof Error ? error.message : "重命名聊天失败。");
      return false;
    }
  }

  async function setConversationPinnedFromSidebar(sessionId: string, isPinned: boolean) {
    try {
      const response = await apiClient.updateConversation(sessionId, { is_pinned: isPinned });
      mergeConversationSummaries([response.session]);
      setComposerError("");
      return true;
    } catch (error) {
      setComposerError(error instanceof Error ? error.message : "更新置顶状态失败。");
      return false;
    }
  }

  async function batchPinConversationsFromSidebar(sessionIds: string[], isPinned: boolean) {
    try {
      const response = await apiClient.batchPinConversations(sessionIds, isPinned);
      mergeConversationSummaries(response.sessions);
      setComposerError("");
      return true;
    } catch (error) {
      setComposerError(error instanceof Error ? error.message : "批量更新置顶状态失败。");
      return false;
    }
  }

  async function batchDeleteConversationsFromSidebar(sessionIds: string[]) {
    const auth = captureAuthContext();
    try {
      const response = await apiClient.batchDeleteConversations(sessionIds);
      clearDeletedCurrentConversation(response.deleted_ids, auth);
      await refreshConversations();
      const failedIds = response.failed.map((failure) => failure.session_id);
      if (response.failed.length) {
        setComposerError(response.failed.map((failure) => failure.message).join("；"));
      } else {
        setComposerError("");
        showStatusNotification({
          id: "conversation-batch-delete-success",
          message: `已删除 ${response.deleted_ids.length} 个聊天。`,
          tone: "success"
        });
      }
      return failedIds;
    } catch (error) {
      setComposerError(error instanceof Error ? error.message : "批量删除聊天失败。");
      return sessionIds;
    }
  }
  return {
    deleteConversationFromSidebar,
    renameConversationFromSidebar,
    setConversationPinnedFromSidebar,
    batchPinConversationsFromSidebar,
    batchDeleteConversationsFromSidebar
  };
}
