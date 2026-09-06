import { useMemo, useRef, useState } from "react";
import { captureAuthContext } from "../../api/authLifecycle";
import {
  apiClient, type ConversationDetail,
  type ConversationSummary
} from "../../api/client";
import { useActiveScope } from "../../utils/useActiveScope";
import { createConversationIndex } from "./conversationIndex";
import {
  type ActiveStream
} from "./workspaceTypes";

export function useConversationDataState() {
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [conversationDetail, setConversationDetail] = useState<ConversationDetail | null>(null);
  const [conversations, publishConversations] = useState<ConversationSummary[]>([]);
  const [activeStreamTurnId, setActiveStreamTurnId] = useState<string | null>(null);
  const [cancellingTurnId, setCancellingTurnId] = useState<string | null>(null);
  const activeStreamRef = useRef<ActiveStream | null>(null);
  const conversationRequestSeqRef = useRef(0);
  const auth = captureAuthContext();
  const isCurrent = useActiveScope("conversation-index");
  const index = useMemo(() => createConversationIndex(apiClient.fetchConversations, publishConversations, isCurrent), [auth]);
  const setConversations = index.update;
  const refreshConversations = index.refresh;
  return {
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
  };
}
