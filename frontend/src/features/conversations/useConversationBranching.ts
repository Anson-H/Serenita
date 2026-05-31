import {
  type Dispatch,
  type SetStateAction,
  useMemo,
} from "react";

import {
  type ConversationDetail,
  type ConversationMessage,
  apiClient
} from "../../api/client";
import {
  branchParentKeyForMessage,
  buildChildrenByParent,
  pathToMessageId
} from "./branching";

type ConversationBranchingOptions = {
  allMessages: ConversationMessage[];
  conversationDetail: ConversationDetail | null;
  currentSessionId: string | null;
  messagesById: Map<string, ConversationMessage>;
  openConversation: (sessionId: string, sourceMessageId?: string | null) => Promise<boolean>;
  setComposerText: Dispatch<SetStateAction<string>>;
  setParentForNextMessage: Dispatch<SetStateAction<string | null | undefined>>;
};

export function useConversationBranching(options: ConversationBranchingOptions) {
  const {
    allMessages,
    conversationDetail,
    currentSessionId,
    messagesById,
    openConversation,
    setComposerText,
    setParentForNextMessage
  } = options;

  const childrenByParent = useMemo(
    () => buildChildrenByParent(allMessages, messagesById),
    [allMessages, messagesById]
  );

  async function switchBranch(message: ConversationMessage, direction: -1 | 1) {
    if (!currentSessionId || !conversationDetail) {
      return;
    }
    const parentKey = branchParentKey(message);
    const siblings = childrenByParent.get(parentKey) ?? [];
    const currentIndex = siblings.findIndex((sibling) => sibling.message_id === message.message_id);
    const next = siblings[currentIndex + direction];
    if (!next) {
      return;
    }
    const nextPath = pathToMessage(next.message_id);
    const focusMessageId = branchSwitchFocusMessageId(message, next);
    await apiClient.setActivePath(currentSessionId, nextPath);
    await openConversation(currentSessionId, focusMessageId);
  }

  function branchParentKey(message: ConversationMessage) {
    return branchParentKeyForMessage(message, messagesById);
  }

  function branchSwitchFocusMessageId(message: ConversationMessage, next: ConversationMessage) {
    const parentKey = branchParentKey(message);
    return parentKey !== "root" ? parentKey : next.message_id;
  }

  function pathToMessage(messageId: string) {
    return pathToMessageId(messageId, messagesById);
  }

  function branchAfter(message: ConversationMessage) {
    setParentForNextMessage(message.message_id);
    setComposerText("");
  }

  function restoreBranchPreview() {
    setParentForNextMessage(undefined);
  }

  return {
    branchAfter,
    branchParentKey,
    childrenByParent,
    restoreBranchPreview,
    switchBranch
  };
}
