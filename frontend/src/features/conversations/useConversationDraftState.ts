import { useRef, useState } from "react";
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
  const [composerText, setComposerText] = useState("");
  const [uploadingResources, setUploadingResources] = useState<UploadingResource[]>([]);
  const [uploadedResources, setUploadedResources] = useState<UploadedResource[]>([]);
  const [annotatedContexts, setAnnotatedContexts] = useState<AnnotatedContext[]>([]);
  const [annotationSelection, setAnnotationSelection] = useState<AnnotationSelection | null>(null);
  const homeConversationDraftRef = useRef<HomeConversationDraft | null>(null);
  return {
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
