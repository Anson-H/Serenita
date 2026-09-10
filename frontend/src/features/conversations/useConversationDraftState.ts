import { useRef, useSyncExternalStore } from "react";
import { ConversationDraftStore } from "./conversationDraftStore";
import {
  type UploadedResource
} from "../../api/client";
import { type UploadingResource } from "./contextResources";
import type { HomeConversationDraft } from "./useConversationPageState";
import {
  type AnnotatedContext,
  type AnnotationSelection
} from "./workspaceTypes";

export function useConversationDraftState() {
  const draftStore = useRef(new ConversationDraftStore()).current;
  const { composerText, uploadingResources, uploadedResources, annotatedContexts, annotationSelection, restoring } = useSyncExternalStore(draftStore.subscribe, draftStore.snapshot, draftStore.snapshot);
  const setComposerText: React.Dispatch<React.SetStateAction<string>> = value => draftStore.update("composerText", value);
  const setUploadingResources: React.Dispatch<React.SetStateAction<UploadingResource[]>> = value => draftStore.update("uploadingResources", value);
  const setUploadedResources: React.Dispatch<React.SetStateAction<UploadedResource[]>> = value => draftStore.update("uploadedResources", value);
  const setAnnotatedContexts: React.Dispatch<React.SetStateAction<AnnotatedContext[]>> = value => draftStore.update("annotatedContexts", value);
  const setAnnotationSelection: React.Dispatch<React.SetStateAction<AnnotationSelection | null>> = value => draftStore.update("annotationSelection", value);
  const homeConversationDraftRef = useRef<HomeConversationDraft | null>(null);
  return {
    draftStore,
    restoringQueuedInput: restoring,
    composerText,
    setComposerText,
    uploadingResources,
    setUploadingResources,
    uploadedResources,
    setUploadedResources,
    annotatedContexts,
    setAnnotatedContexts,
    annotationSelection,
    setAnnotationSelection,
    homeConversationDraftRef
  };
}
