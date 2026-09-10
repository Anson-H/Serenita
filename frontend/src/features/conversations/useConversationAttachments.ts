import {
  type ChangeEvent,
  type Dispatch,
  type SetStateAction,
  useEffect,
} from "react";
import { captureAuthContext, isAuthContextCurrent } from "../../api/authLifecycle";
import type { ConversationDraftStore, DraftRecord } from "./conversationDraftStore";
import { useActiveScope } from "../../utils/useActiveScope";
import { useMembers } from "../members/MemberProvider";

import {
  type ConversationDetail,
  type UploadedResource,
  apiClient
} from "../../api/client";
import { filterResourcesByMimeTypes } from "./attachmentSupport";
import { type UploadingResource } from "./contextResources";

type ConversationAttachmentsOptions = {
  draftStore: ConversationDraftStore;
  conversationDetail: ConversationDetail | null;
  currentSessionId: string | null;
  selectedModelId: string | null;
  selectedModelFileMimeTypes: string[];
  attachmentCapabilitiesReady: boolean;
  setComposerError: Dispatch<SetStateAction<string>>;
  setConversationDetail: Dispatch<SetStateAction<ConversationDetail | null>>;
  setCurrentSessionId: Dispatch<SetStateAction<string | null>>;
  setUploadedResources: Dispatch<SetStateAction<UploadedResource[]>>;
  setUploadingResources: Dispatch<SetStateAction<UploadingResource[]>>;
  uploadedResourcesLength: number;
};

export function useConversationAttachments(options: ConversationAttachmentsOptions) {
  const { activeMemberId } = useMembers();
  const memberId = options.conversationDetail ? options.conversationDetail.member_id : activeMemberId;
  const isCurrentScope = useActiveScope(`${memberId ?? "unbound"}:${options.currentSessionId ?? ""}`);
  const {
    currentSessionId,
    selectedModelId,
    selectedModelFileMimeTypes,
    attachmentCapabilitiesReady,
    setComposerError,
    setConversationDetail,
    setCurrentSessionId,
    setUploadedResources,
    setUploadingResources,
    uploadedResourcesLength
  } = options;

  useEffect(() => {
    if (!attachmentCapabilitiesReady || !uploadedResourcesLength) {
      return;
    }
    setUploadedResources((current) =>
      filterResourcesByMimeTypes(current, selectedModelFileMimeTypes)
    );
  }, [attachmentCapabilitiesReady, selectedModelFileMimeTypes, setUploadedResources, uploadedResourcesLength]);

  async function handleFileUpload(event: ChangeEvent<HTMLInputElement>) {
    const input = event.currentTarget;
    const files = Array.from(input.files ?? []);
    input.value = "";
    const draft = options.draftStore.capture();
    if (!files.length || draft.value.restoring) return;
    try {
      const upload = await uploadFiles(files, currentSessionId, undefined, draft);
      await refreshUploadedDraft(draft, upload.sessionId);
    } catch (error) {
      if (options.draftStore.isCurrent(draft)) setComposerError(error instanceof Error ? error.message : "文件上传失败。");
    }
  }

  async function refreshUploadedDraft(draft: DraftRecord, sessionId: string) {
    let detail: ConversationDetail | null = null;
    try { detail = await apiClient.getConversation(sessionId); }
    catch { if (options.draftStore.isCurrent(draft)) setComposerError("附件已上传，聊天详情暂时无法刷新，请重试。"); }
    options.draftStore.associate(draft, sessionId);
    draft.detail = detail;
    if (!options.draftStore.isCurrent(draft)) return;
    setCurrentSessionId(sessionId);
    setConversationDetail(detail);
  }

  async function uploadFiles(files: File[], initialSessionId: string | null = null, batch?: {
    memberId: string;
    isCurrent: () => boolean;
    onUploaded: (sessionId: string, resource: UploadedResource) => void;
  }, draft = options.draftStore.capture()) {
    const auth = captureAuthContext();
    const current = () => isAuthContextCurrent(auth) && (batch ? isCurrentScope() && batch.isCurrent() : draft.valid);
    const requireScope = () => {
      if (!current()) { const error = new Error("上传所属页面已改变。"); error.name = "AbortError"; throw error; }
    };
    const progress = (next: (resources: UploadingResource[]) => UploadingResource[]) => {
      if (!current()) return;
      if (batch) setUploadingResources(next);
      else options.draftStore.patch(draft, { uploadingResources: next(draft.value.uploadingResources) });
    };
    const run = async () => {
      let sessionId = batch ? initialSessionId : draft.sessionId ?? initialSessionId;
      const resources: UploadedResource[] = [];
      requireScope();
      if (batch || options.draftStore.isCurrent(draft)) setComposerError("");
      for (const file of files) {
        requireScope();
        const progressKey = crypto.randomUUID();
        progress(items => [...items, { progress_key: progressKey, originalFilename: file.name, progress: 1 }]);
        try {
          const result = await apiClient.uploadContextResource(batch?.memberId ?? memberId, sessionId, file, selectedModelId, value => {
            progress(items => items.map(item => item.progress_key === progressKey ? { ...item, progress: value } : item));
          });
          requireScope();
          sessionId = result.session_id;
          resources.push(result.resource);
          if (batch) batch.onUploaded(sessionId, result.resource);
          else {
            options.draftStore.associate(draft, sessionId);
            options.draftStore.patch(draft, { uploadedResources: [...draft.value.uploadedResources, result.resource] });
            if (options.draftStore.isCurrent(draft)) setCurrentSessionId(sessionId);
          }
        } catch (error) {
          requireScope();
          if (!batch && sessionId) await refreshUploadedDraft(draft, sessionId);
          throw new Error(`${file.name} 上传失败，已上传 ${resources.length} 个文件，其余文件尚未上传。${error instanceof Error ? error.message : ""}`);
        } finally {
          progress(items => items.filter(item => item.progress_key !== progressKey));
        }
      }
      if (!sessionId) throw new Error("未能创建附件聊天。");
      return { sessionId, resources };
    };
    if (batch) return run();
    // Concurrent file selections share the same draft session and upload queue.
    const task = draft.uploads.then(run, run);
    draft.uploads = task;
    return task;
  }

  function removeUploadedResource(resourceId: string) {
    setUploadedResources((current) => current.filter((item) => item.resource_id !== resourceId));
  }

  return {
    handleFileUpload,
    uploadFiles,
    removeUploadedResource
  };
}
