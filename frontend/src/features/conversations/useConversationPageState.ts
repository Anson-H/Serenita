import { useState } from "react";
import { emptyModelCatalog } from "../modelConfiguration/modelCatalog";
import { useConversationDataState } from "./useConversationDataState";
import { useConversationDraftState } from "./useConversationDraftState";
import { useConversationEditingState } from "./useConversationEditingState";
import { useConversationElements } from "./useConversationElements";

import {
  type ConversationDetail,
  type UploadedResource
} from "../../api/client";
import { type UploadingResource } from "./contextResources";
import {
  type AnnotatedContext,
  type AnnotationSelection,
  type ScenarioTab
} from "./workspaceTypes";

export type HomeConversationDraft = {
  currentSessionId: string | null;
  conversationDetail: ConversationDetail | null;
  composerText: string;
  annotatedContexts: AnnotatedContext[];
  annotationSelection: AnnotationSelection | null;
  uploadedResources: UploadedResource[];
  uploadingResources: UploadingResource[];
};

export function useConversationPageState() {
  const {
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
  } = useConversationDraftState();
  const {
    highlightedMessageId,
    setHighlightedMessageId,
    highlightedMessageRequestId,
    setHighlightedMessageRequestId,
    editingMessageId,
    setEditingMessageId,
    editingMessageText,
    setEditingMessageText,
    editingMessageContextResources,
    setEditingMessageContextResources,
    copiedMessageId,
    setCopiedMessageId,
    copySuccessTimeoutRef
  } = useConversationEditingState();
  const {
    refreshConversations,
    currentSessionId,
    setCurrentSessionId,
    conversationDetail,
    setConversationDetail,
    conversations,
    setConversations,
    activeStreamTurnId,
    setActiveStreamTurnId,
    cancellingTurnId,
    setCancellingTurnId,
    activeStreamRef,
    conversationRequestSeqRef
  } = useConversationDataState();
  const {
    messageRefs,
    messageListRef,
    conversationStageRef,
    conversationSurfaceRef,
    editingMessageInputRef,
    composerTextareaRef,
    composerRef,
    composerModelControlRef
  } = useConversationElements();
  const [activeScenario, setActiveScenario] = useState<ScenarioTab>("home");

  const [composerError, setComposerError] = useState("");
  const [sending, setSending] = useState(false);

  const [modelCatalog, setModelCatalog] = useState(emptyModelCatalog);
  const models = modelCatalog.models;
  const visionParseModel = modelCatalog.defaults.vision_parse;

  return {
    refreshConversations,
    activeStreamRef,
    activeStreamTurnId,
    cancellingTurnId,
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
    copiedMessageId,
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
    models,
    annotatedContexts,
    annotationSelection,
    sending,
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
    modelCatalog,
    setModelCatalog,
    setAnnotatedContexts,
    setAnnotationSelection,
    setSending,
    setUploadedResources,
    setUploadingResources,
    activeScenario,
    uploadedResources,
    uploadingResources,
    visionParseModel
  };
}
