import {
  type Dispatch,
  type MutableRefObject,
  type SetStateAction
} from "react";

import {
  type ConversationDetail,
  type SendMessageResponse,
  apiClient
} from "../../api/client";
import {
  appendStreamDeltaToDetail,
  cancelStreamingTurnInDetail,
  completeStreamingThinkingInDetail,
  completeStreamingTurnInDetail,
  currentStreamingContentForDetail
} from "./streamingMessages";
import {
  MIN_THINKING_DURATION_MS,
  isAbortError
} from "./thinking";
import { type ActiveStream } from "./workspaceTypes";

type ConversationStreamControllerOptions = {
  activeStreamRef: MutableRefObject<ActiveStream | null>;
  conversationDetail: ConversationDetail | null;
  openConversation: (sessionId: string, sourceMessageId?: string | null) => Promise<boolean>;
  refreshConversations: () => Promise<void>;
  setActiveStreamTurnId: Dispatch<SetStateAction<string | null>>;
  setActivelyThinkingTurnId: Dispatch<SetStateAction<string | null>>;
  setCancellingTurnId: Dispatch<SetStateAction<string | null>>;
  setComposerError: Dispatch<SetStateAction<string>>;
  setConversationDetail: Dispatch<SetStateAction<ConversationDetail | null>>;
  setSending: Dispatch<SetStateAction<boolean>>;
};

export function useConversationStreamController({
  activeStreamRef,
  conversationDetail,
  openConversation,
  refreshConversations,
  setActiveStreamTurnId,
  setActivelyThinkingTurnId,
  setCancellingTurnId,
  setComposerError,
  setConversationDetail,
  setSending
}: ConversationStreamControllerOptions) {
  function applyStreamDelta(messageId: string | null | undefined, delta: string) {
    setConversationDetail((current) => appendStreamDeltaToDetail(current, messageId, delta));
  }

  function markStreamingTurnCompleted(response: SendMessageResponse) {
    setConversationDetail((current) => completeStreamingTurnInDetail(current, response.assistant_message_id));
  }

  function markStreamingThinkingCompleted(turnId: string, durationMs: number) {
    setActivelyThinkingTurnId((current) => (current === turnId ? null : current));
    setConversationDetail((current) =>
      completeStreamingThinkingInDetail(current, turnId, durationMs, MIN_THINKING_DURATION_MS)
    );
  }

  function markStreamingTurnCancelled(turnId: string) {
    setConversationDetail((current) => cancelStreamingTurnInDetail(current, turnId));
  }

  function currentStreamingContent(turnId: string) {
    return currentStreamingContentForDetail(conversationDetail, turnId);
  }

  async function cancelActiveGeneration({
    preservePartial,
    refreshAfterCancel = true,
    keepSending = false
  }: {
    preservePartial: boolean;
    refreshAfterCancel?: boolean;
    keepSending?: boolean;
  }) {
    const activeStream = activeStreamRef.current;
    if (!activeStream) {
      return false;
    }
    const { partialContent, partialThinking } = currentStreamingContent(activeStream.turnId);
    setCancellingTurnId(activeStream.turnId);
    setComposerError("");
    try {
      await apiClient.cancelTurn(activeStream.sessionId, activeStream.turnId, {
        preservePartial,
        partialContent,
        partialThinking
      });
      if (preservePartial) {
        markStreamingTurnCancelled(activeStream.turnId);
      }
      activeStream.abortController.abort();
      if (refreshAfterCancel) {
        await openConversation(activeStream.sessionId);
        await refreshConversations();
      }
      return true;
    } catch (error) {
      setComposerError(error instanceof Error ? error.message : "取消生成失败。");
      return false;
    } finally {
      if (activeStreamRef.current?.turnId === activeStream.turnId) {
        activeStreamRef.current = null;
        setActiveStreamTurnId(null);
      }
      setCancellingTurnId(null);
      if (!keepSending) {
        setSending(false);
      }
    }
  }

  async function startResponseStream(response: SendMessageResponse): Promise<"completed" | "cancelled"> {
    const streamingAssistant = response.assistant_message_id;
    const streamingThinking = response.thinking_message_id ?? null;
    const abortController = new AbortController();
    activeStreamRef.current = {
      sessionId: response.session_id,
      turnId: response.turn_id,
      streamId: response.stream_id,
      assistantMessageId: response.assistant_message_id,
      thinkingMessageId: streamingThinking,
      abortController
    };
    setActiveStreamTurnId(response.turn_id);
    setActivelyThinkingTurnId(streamingThinking ? response.turn_id : null);
    const thinkingStartedAt = performance.now();
    let thinkingCompleted = false;
    let streamResult: "completed" | "cancelled" = "completed";
    try {
      await apiClient.streamConversation(response.stream_id, {
        signal: abortController.signal,
        onEvent: (event) => {
          if (event.event === "thinking_delta") {
            applyStreamDelta(event.data.message_id ?? streamingThinking, event.data.delta);
          }
          if (event.event === "content_delta") {
            if (streamingThinking && !thinkingCompleted) {
              thinkingCompleted = true;
              markStreamingThinkingCompleted(response.turn_id, performance.now() - thinkingStartedAt);
            }
            applyStreamDelta(event.data.message_id ?? streamingAssistant, event.data.delta);
          }
          if (event.event === "completed") {
            markStreamingTurnCompleted(response);
            finishActiveStream(response.stream_id);
          }
          if (event.event === "cancelled") {
            streamResult = "cancelled";
            markStreamingTurnCancelled(response.turn_id);
            finishActiveStream(response.stream_id);
          }
          if (event.event === "failed") {
            finishActiveStream(response.stream_id);
            throw new Error(event.data.message || event.data.code || "生成失败。");
          }
        }
      });
    } catch (error) {
      if (!isAbortError(error)) {
        throw error;
      }
      streamResult = "cancelled";
    } finally {
      if (activeStreamRef.current?.streamId === response.stream_id) {
        activeStreamRef.current = null;
        setActiveStreamTurnId(null);
        setActivelyThinkingTurnId(null);
      }
    }
    return streamResult;
  }

  function finishActiveStream(streamId: string) {
    if (activeStreamRef.current?.streamId !== streamId) {
      return;
    }
    activeStreamRef.current = null;
    setActiveStreamTurnId(null);
    setActivelyThinkingTurnId(null);
    setSending(false);
  }

  return {
    cancelActiveGeneration,
    startResponseStream
  };
}
