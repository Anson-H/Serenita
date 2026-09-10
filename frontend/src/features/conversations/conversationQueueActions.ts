import type { ConversationDraftStore } from "./conversationDraftStore";
import {
  type Dispatch,
  type SetStateAction
} from "react";
import {
  apiClient,
  type ConversationDetail,
  type ConversationSummary,
  type QueuedConversationInput,
  type UploadedResource
} from "../../api/client";
import { partitionContextResources, type UploadingResource } from "./contextResources";
import {
  type AnnotatedContext
} from "./workspaceTypes";

type Dependencies = {
  draftStore: ConversationDraftStore;
  prepareConversationMutation: (key: string) => void;
  setConversationDetail: Dispatch<SetStateAction<ConversationDetail | null>>;
  currentSessionId: string | null;
  setConversations: Dispatch<SetStateAction<ConversationSummary[]>>;
  conversationDetail: ConversationDetail | null;
  isCurrentScope: () => boolean;
  openConversation: (sessionId: string, sourceMessageId?: string | null) => Promise<boolean>;
  setComposerError: Dispatch<SetStateAction<string>>;
  refreshConversations: () => Promise<void>;
  composerText: string;
  uploadedResources: UploadedResource[];
  uploadingResources: UploadingResource[];
  annotatedContexts: AnnotatedContext[];
  setComposerText: Dispatch<SetStateAction<string>>;
  setUploadedResources: Dispatch<SetStateAction<UploadedResource[]>>;
  setAnnotatedContexts: Dispatch<SetStateAction<AnnotatedContext[]>>;
  onRestoreQueuedInputPreferences: ((modelId: string, thinkingMode: string) => void | Promise<void>) | undefined;
  clearHighlightedMessage: () => void;
};

export function createConversationQueueActions({
  draftStore,
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
  onRestoreQueuedInputPreferences,
  clearHighlightedMessage
}: Dependencies) {
  function applyQueuedInputs(queuedInputs: QueuedConversationInput[]) {
    prepareConversationMutation(
      `queue-update:${queuedInputs.map((item) => item.input_id).join(",")}`
    );
    setConversationDetail((current) =>
      current?.session_id === currentSessionId
        ? { ...current, queued_inputs: queuedInputs }
        : current
    );
    if (currentSessionId) {
      setConversations((current) => current.map((conversation) =>
        conversation.session_id === currentSessionId
          ? { ...conversation, queued_input_count: queuedInputs.length }
          : conversation
      ));
    }
  }

  async function reorderQueuedInputs(inputIds: string[]) {
    if (!currentSessionId || !conversationDetail) {
      return;
    }
    const previous = conversationDetail.queued_inputs;
    const byId = new Map(previous.map((item) => [item.input_id, item]));
    applyQueuedInputs(inputIds.map((inputId, position) => ({
      ...byId.get(inputId)!,
      position
    })));
    try {
      const response = await apiClient.reorderQueuedInputs(currentSessionId, inputIds);
      applyQueuedInputs(response.queued_inputs);
    } catch (error) {
      if (!isCurrentScope()) return;
      await openConversation(currentSessionId);
      setComposerError(error instanceof Error ? error.message : "调整等候顺序失败。");
    }
  }

  async function deleteQueuedInput(inputId: string) {
    if (!currentSessionId) {
      return;
    }
    try {
      const response = await apiClient.deleteQueuedInput(currentSessionId, inputId);
      applyQueuedInputs(response.queued_inputs);
      await refreshConversations();
    } catch (error) {
      if (!isCurrentScope()) return;
      await openConversation(currentSessionId);
      setComposerError(error instanceof Error ? error.message : "删除等候输入失败。");
    }
  }

  async function restoreQueuedInputToDraft(inputId: string) {
    if (!currentSessionId) {
      return;
    }
    if (
      composerText.length > 0 ||
      uploadedResources.length > 0 ||
      uploadingResources.length > 0 ||
      annotatedContexts.length > 0 ||
      draftStore.snapshot().contextResources.length > 0
    ) {
      setComposerError("输入框或附件区已有草稿，请先发送或清空后再编辑等候输入。");
      return;
    }
    const draft = draftStore.beginRestore();
    if (!draft) return;
    draftStore.remember(currentSessionId);
    try {
      const response = await apiClient.restoreQueuedInputToDraft(currentSessionId, inputId);
      const item = response.queued_input;
      const partition = partitionContextResources(item.context_resources, item.input_id);
      const files = partition.files.map((file) => {
        const original = item.context_resources.find(
          (resource) => resource.resource_type === "file" && resource.resource_id === file.resource_id
        ) ?? {};
        return {
          resource_id: file.resource_id,
          original_filename: file.original_filename,
          mime_type: file.mime_type ?? "application/octet-stream",
          size_bytes: typeof original.size_bytes === "number" ? original.size_bytes : 0,
          storage_status: "ready" as const,
          lifecycle_status: "attached" as const
        };
      });
      draftStore.patch(draft, { composerText: item.content, uploadedResources: files, annotatedContexts: partition.annotations.map((annotation) => ({
        ...annotation,
        preview: annotation.annotation_text
      })), contextResources: item.context_resources.filter(
        resource => !["file", "record_annotation"].includes(String(resource.resource_type ?? ""))
      ) });
      if (!isCurrentScope()) return;
      await onRestoreQueuedInputPreferences?.(item.model_id, item.thinking_mode);
      if (!isCurrentScope()) return;
      applyQueuedInputs(response.queued_inputs);
      setComposerError("");
      await refreshConversations();
    } catch (error) {
      if (!isCurrentScope()) return;
      await openConversation(currentSessionId);
      setComposerError(error instanceof Error ? error.message : "取回等候输入失败。");
    } finally {
      draftStore.endRestore(draft);
    }
  }

  async function runQueuedInputNow(inputId: string) {
    if (!currentSessionId) {
      return;
    }
    clearHighlightedMessage();
    try {
      await apiClient.runQueuedInputNow(currentSessionId, inputId);
      if (!isCurrentScope()) return;
      prepareConversationMutation(`queue-run-now:${inputId}`);
      await openConversation(currentSessionId);
      await refreshConversations();
    } catch (error) {
      if (!isCurrentScope()) return;
      await openConversation(currentSessionId);
      setComposerError(error instanceof Error ? error.message : "立即执行失败。");
    }
  }
  return {
    reorderQueuedInputs,
    deleteQueuedInput,
    restoreQueuedInputToDraft,
    runQueuedInputNow
  };
}
