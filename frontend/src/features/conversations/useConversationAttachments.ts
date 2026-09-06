import {
  type ChangeEvent,
  type Dispatch,
  type SetStateAction,
  useEffect,
} from "react";
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
    if (!files.length) return;
    try {
      const upload = await uploadFiles(files, currentSessionId);
      if (!isCurrentScope()) return;
      let detail: ConversationDetail | null = null;
      try { detail = await apiClient.getConversation(upload.sessionId); }
      catch { if (isCurrentScope()) setComposerError("附件已上传，聊天详情暂时无法刷新，请重试。"); }
      if (!isCurrentScope()) return;
      setCurrentSessionId(upload.sessionId);
      setConversationDetail(detail);
    } catch (error) {
      if (isCurrentScope()) setComposerError(error instanceof Error ? error.message : "文件上传失败。");
    }
  }

  async function uploadFiles(files: File[], initialSessionId: string | null = null, batch?: {
    memberId: string;
    isCurrent: () => boolean;
    onUploaded: (sessionId: string, resource: UploadedResource) => void;
  }) {
    let sessionId = initialSessionId;
    const resources: UploadedResource[] = [];
    const current = () => isCurrentScope() && (!batch || batch.isCurrent());
    const requireScope = () => {
      if (!current()) { const error = new Error("上传所属页面已改变。"); error.name = "AbortError"; throw error; }
    };
    requireScope();
    setComposerError("");
    for (const [index, file] of files.entries()) {
      requireScope();
      const progressKey = `${file.name}-${Date.now()}-${index}`;
      setUploadingResources(current => [...current, { progress_key: progressKey, originalFilename: file.name, progress: 1 }]);
      try {
        const result = await apiClient.uploadContextResource(batch?.memberId ?? memberId, sessionId, file, selectedModelId, progress => {
          if (current()) setUploadingResources(current => current.map(resource => resource.progress_key === progressKey ? { ...resource, progress } : resource));
        });
        requireScope();
        sessionId = result.session_id;
        resources.push(result.resource);
        if (batch) batch.onUploaded(sessionId, result.resource);
        else setUploadedResources(current => [...current, result.resource]);
      } catch (error) {
        requireScope();
        const message = `${file.name} 上传失败，已上传 ${resources.length} 个文件，其余文件尚未上传。${error instanceof Error ? error.message : ""}`;
        if (!batch) setComposerError(message);
        if (!batch && sessionId) {
          let detail: ConversationDetail | null = null;
          try { detail = await apiClient.getConversation(sessionId); } catch { /* Preserve the upload error and the confirmed resource ownership. */ }
          requireScope();
          setCurrentSessionId(sessionId);
          setConversationDetail(detail);
        }
        throw new Error(message);
      } finally {
        if (current()) setUploadingResources(current => current.filter(resource => resource.progress_key !== progressKey));
      }
    }
    if (!sessionId) throw new Error("未能创建附件聊天。");
    return { sessionId, resources };
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
