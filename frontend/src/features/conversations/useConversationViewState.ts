import { useMemo } from "react";
import { useAttachmentCapabilities } from "./useAttachmentCapabilities";

import {
  isConversationMessage,
  type AddedModel,
  type ConversationDetail
} from "../../api/client";
import { canAttachFilesForScenario } from "./attachmentSupport";
import {
  scenarioCopy,
  type ScenarioTab
} from "./workspaceTypes";

type ConversationViewStateOptions = {
  activeScenario: ScenarioTab;
  conversationDetail: ConversationDetail | null;
  selectedModel: AddedModel | undefined;
  visionParseModel: AddedModel | null;
};

export function useConversationViewState({
  activeScenario,
  conversationDetail,
  selectedModel,
  visionParseModel
}: ConversationViewStateOptions) {
  const selectedScenario = scenarioCopy[activeScenario];
  const workspaceTitle = activeScenario === "home" && conversationDetail ? conversationDetail.title : selectedScenario.title;
  const records = useMemo(
    () => conversationDetail?.records ?? [],
    [conversationDetail?.records]
  );
  const messages = useMemo(() => records.filter(isConversationMessage), [records]);
  const capabilities = useAttachmentCapabilities(selectedModel, visionParseModel);
  const { selectedModelFileMimeTypes } = capabilities;
  const canAttachFiles = canAttachFilesForScenario(
    activeScenario,
    selectedModelFileMimeTypes
  );
  return {
    ...capabilities,
    canAttachFiles,
    messages,
    selectedModelFileMimeTypes,
    selectedScenario,
    visibleMessages: records,
    workspaceTitle
  };
}
