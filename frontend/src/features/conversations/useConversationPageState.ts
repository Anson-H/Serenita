import { isModelAvailable } from "../modelConfiguration/modelEligibility";
import { isGenerationModel } from "../modelConfiguration/generationModels";
import { useState } from "react";
import { useModelCatalog } from "../modelConfiguration/useModelCatalog";
import { useConversationDataState } from "./useConversationDataState";
import { useConversationDraftState } from "./useConversationDraftState";
import { useConversationEditingState } from "./useConversationEditingState";
import { useConversationElements } from "./useConversationElements";

import {
  type ScenarioTab
} from "./workspaceTypes";


export function useConversationPageState() {
  const {
    draftStore,
    restoringQueuedInput,
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
    conversationPagination,
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

  const { modelCatalog, setModelCatalog, refreshModelCatalog } = useModelCatalog();
  const models = modelCatalog.models.filter(isGenerationModel).filter(isModelAvailable);
  const visionParseModel = modelCatalog.defaults.vision_parse;

  return {
    draftStore,
    restoringQueuedInput,
    conversationPagination,
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
    refreshModelCatalog,
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
