import {
  type ChangeEvent,
  type Dispatch,
  type SetStateAction,
  useEffect,
} from "react";

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
  setComposerError: Dispatch<SetStateAction<string>>;
  setConversationDetail: Dispatch<SetStateAction<ConversationDetail | null>>;
  setCurrentSessionId: Dispatch<SetStateAction<string | null>>;
  setUploadedResources: Dispatch<SetStateAction<UploadedResource[]>>;
  setUploadingResources: Dispatch<SetStateAction<UploadingResource[]>>;
  uploadedResourcesLength: number;
};

export function useConversationAttachments(options: ConversationAttachmentsOptions) {
  const {
    conversationDetail,
    currentSessionId,
    selectedModelId,
    selectedModelFileMimeTypes,
    setComposerError,
    setConversationDetail,
    setCurrentSessionId,
    setUploadedResources,
    setUploadingResources,
    uploadedResourcesLength
  } = options;

  useEffect(() => {
    if (!uploadedResourcesLength) {
      return;
    }
    setUploadedResources((current) =>
      filterResourcesByMimeTypes(current, selectedModelFileMimeTypes)
    );
  }, [selectedModelFileMimeTypes, setUploadedResources, uploadedResourcesLength]);

  async function handleFileUpload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    const uploadId = `${file.name}-${file.lastModified}-${Date.now()}`;
    const handleUploadProgress = (progress: number) => {
      setUploadingResources((current) =>
        current.map((resource) =>
          resource.upload_id === uploadId ? { ...resource, progress } : resource
        )
      );
    };
    setComposerError("");
    setUploadingResources((current) => [
      ...current,
      {
        upload_id: uploadId,
        name: file.name,
        progress: 1
      }
    ]);
    try {
      const result = await apiClient.uploadContextResource(currentSessionId, file, selectedModelId, handleUploadProgress);
      setCurrentSessionId(result.session_id);
      setUploadedResources((current) => [...current, result.resource]);
      if (!conversationDetail || conversationDetail.session_id !== result.session_id) {
        const detail = await apiClient.getConversation(result.session_id);
        setConversationDetail(detail);
      }
    } catch (error) {
      setComposerError(error instanceof Error ? error.message : "文件上传失败。");
    } finally {
      setUploadingResources((current) => current.filter((resource) => resource.upload_id !== uploadId));
      event.target.value = "";
    }
  }

  function removeUploadedResource(resourceId: string) {
    setUploadedResources((current) => current.filter((item) => item.resource_id !== resourceId));
  }

  return {
    handleFileUpload,
    removeUploadedResource
  };
}
