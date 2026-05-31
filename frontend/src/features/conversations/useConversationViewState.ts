import { useMemo } from "react";

import type { AddedModel, ConversationDetail } from "../../api/client";
import { canAttachFilesForScenario, mergeModelFileMimeTypes } from "./attachmentSupport";
import { createMessageIndex } from "./branching";
import {
  scenarioCopy,
  type ScenarioTab
} from "./workspaceTypes";

type ConversationViewStateOptions = {
  activeScenario: ScenarioTab;
  conversationDetail: ConversationDetail | null;
  parentForNextMessage: string | null | undefined;
  selectedModel: AddedModel | undefined;
  visionParseModel: AddedModel | null;
};

export function useConversationViewState({
  activeScenario,
  conversationDetail,
  parentForNextMessage,
  selectedModel,
  visionParseModel
}: ConversationViewStateOptions) {
  const selectedScenario = scenarioCopy[activeScenario];
  const workspaceTitle = activeScenario === "home" && conversationDetail ? conversationDetail.title : selectedScenario.title;
  const messages = conversationDetail?.messages ?? [];
  const allMessages = conversationDetail?.all_messages ?? messages;
  const selectedModelFileMimeTypes = mergeModelFileMimeTypes(selectedModel, visionParseModel);
  const canAttachFiles = canAttachFilesForScenario(activeScenario, selectedModelFileMimeTypes);
  const messagesById = useMemo(() => createMessageIndex(allMessages), [allMessages]);
  const branchPreviewMessageIndex = parentForNextMessage !== undefined
    ? messages.findIndex((message) => message.message_id === parentForNextMessage)
    : -1;
  const visibleMessages = branchPreviewMessageIndex >= 0
    ? messages.slice(0, branchPreviewMessageIndex + 1)
    : messages;
  const showBranchRestoreDivider = branchPreviewMessageIndex >= 0;

  return {
    allMessages,
    canAttachFiles,
    messages,
    messagesById,
    selectedModelFileMimeTypes,
    selectedScenario,
    showBranchRestoreDivider,
    visibleMessages,
    workspaceTitle
  };
}
