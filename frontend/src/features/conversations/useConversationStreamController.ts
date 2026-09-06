import {
  type Dispatch,
  type MutableRefObject,
  type SetStateAction
} from "react";

import {
  type ConversationDetail,
  type ConversationSummary,
  type StartedMessageResponse,
  apiClient
} from "../../api/client";
import { showStatusNotification } from "../../components/StatusNotificationCenter";
import {
  appendRecordDeltaToDetail,
  cancelStreamingTurnInDetail,
  completeStreamingRecordInDetail,
  completeStreamingTurnInDetail,
  startStreamingRecordInDetail
} from "./streamingMessages";
import { isAbortError, thinkingModeLabel } from "./thinking";
import { type ActiveStream } from "./workspaceTypes";

type ConversationStreamControllerOptions = {
  activeStreamRef: MutableRefObject<ActiveStream | null>;
  openConversation: (sessionId: string, sourceMessageId?: string | null) => Promise<boolean>;
  onThinkingModeChanged: (mode: string) => void;
  onTurnSettled: () => void;
  prepareConversationMutation?: (key: string) => void;
  refreshConversations: () => Promise<void>;
  setActiveStreamTurnId: Dispatch<SetStateAction<string | null>>;
  setCancellingTurnId: Dispatch<SetStateAction<string | null>>;
  setComposerError: Dispatch<SetStateAction<string>>;
  setConversationDetail: Dispatch<SetStateAction<ConversationDetail | null>>;
  setConversations: Dispatch<SetStateAction<ConversationSummary[]>>;
};

export function useConversationStreamController({
  activeStreamRef,
  openConversation,
  onThinkingModeChanged,
  onTurnSettled,
  prepareConversationMutation = () => undefined,
  refreshConversations,
  setActiveStreamTurnId,
  setCancellingTurnId,
  setComposerError,
  setConversationDetail,
  setConversations
}: ConversationStreamControllerOptions) {
  function markStreamingTurnCompleted(response: StartedMessageResponse) {
    prepareConversationMutation(`stream-completed:${response.turn_id}`);
    setConversationDetail((current) => {
      if (current?.session_id !== response.session_id) {
        return current;
      }
      const completed = completeStreamingTurnInDetail(current, response.final_assistant_message_id);
      return completed
        ? {
          ...completed,
          pending_turns: completed.pending_turns.filter(
            (turn) => turn.turn_id !== response.turn_id
          )
        }
        : completed;
    });
  }

  function markStreamingTurnCancelled(turnId: string) {
    prepareConversationMutation(`stream-cancelled:${turnId}`);
    setConversationDetail((current) =>
      current?.session_id === activeStreamRef.current?.sessionId
        ? cancelStreamingTurnInDetail(current, turnId)
        : current
    );
  }

  async function cancelActiveGeneration({
    preservePartial,
    refreshAfterCancel = true,
  }: {
    preservePartial: boolean;
    refreshAfterCancel?: boolean;
  }) {
    const activeStream = activeStreamRef.current;
    if (!activeStream) {
      return false;
    }
    setCancellingTurnId(activeStream.turnId);
    setComposerError("");
    try {
      await apiClient.cancelTurn(activeStream.sessionId, activeStream.turnId, {
        preservePartial
      });
      const stillVisible = activeStreamRef.current === activeStream;
      if (stillVisible) {
        if (preservePartial) {
          markStreamingTurnCancelled(activeStream.turnId);
        }
        activeStreamRef.current = null;
        setActiveStreamTurnId(null);
        onTurnSettled();
      }
      activeStream.abortController.abort();
      if (refreshAfterCancel && stillVisible) {
        await openConversation(activeStream.sessionId);
        await refreshConversations();
      }
      return true;
    } catch (error) {
      if (activeStreamRef.current === activeStream) {
        setComposerError(error instanceof Error ? error.message : "取消生成失败。");
      }
      return false;
    } finally {
      setCancellingTurnId(current => current === activeStream.turnId ? null : current);
    }
  }

  async function startResponseStream(response: StartedMessageResponse): Promise<"completed" | "failed" | "cancelled" | "detached"> {
    const previous = activeStreamRef.current;
    if (previous?.streamId === response.stream_id && !previous.abortController.signal.aborted) {
      return "detached";
    }
    if (previous) {
      activeStreamRef.current = null;
      previous.abortController.abort();
    }
    const abortController = new AbortController();
    const subscription: ActiveStream = {
      sessionId: response.session_id,
      turnId: response.turn_id,
      streamId: response.stream_id,
      finalAssistantMessageId: response.final_assistant_message_id,
      abortController
    };
    activeStreamRef.current = subscription;
    const isCurrent = () => activeStreamRef.current === subscription;
    prepareConversationMutation(`stream-start:${response.turn_id}:${response.stream_id}`);
    setActiveStreamTurnId(response.turn_id);
    setConversations((current) => current.map((conversation) =>
      conversation.session_id === response.session_id
        ? {
          ...conversation,
          pending_turn_status: response.message_status === "queued" ? "queued" : "streaming"
        }
        : conversation
    ));
    const terminalState: { result: "completed" | "failed" | "cancelled" | null } = {
      result: null
    };
    try {
      let retryDelay = 250;
      while (
        isCurrent() &&
        terminalState.result === null
      ) {
        try {
          await apiClient.streamConversation(response.session_id, response.stream_id, {
            signal: abortController.signal,
            onEvent: (event) => {
              if (!isCurrent()) {
                return;
              }
              if (event.event === "thinking_mode_changed") {
                onThinkingModeChanged(event.data.effective_mode);
                const reason = event.data.reasons.includes("tool_calling")
                  ? "使用原生工具"
                  : "处理当前附件";
                showStatusNotification({
                  id: `thinking-mode-changed-${event.data.turn_id}`,
                  message: `本轮为${reason}，已临时切换为${thinkingModeLabel(event.data.effective_mode)}`,
                  tone: "info"
                });
              }
              if (event.event === "session_title_updated") {
                setConversations((current) => current.map((conversation) =>
                  conversation.session_id === event.data.session_id
                    ? { ...conversation, title: event.data.title }
                    : conversation
                ));
                setConversationDetail((current) =>
                  current?.session_id === event.data.session_id
                    ? { ...current, title: event.data.title }
                    : current
                );
              }
              if (event.event === "record_started") {
                prepareConversationMutation(`record-started:${event.data.record_id}`);
                setConversationDetail((current) =>
                  current?.session_id === response.session_id
                    ? startStreamingRecordInDetail(current, event.data)
                    : current
                );
              }
              if (event.event === "record_delta") {
                prepareConversationMutation(
                  `record-delta:${event.data.record_id}:${event.data.channel}:${event.data.offset}`
                );
                setConversationDetail((current) =>
                  current?.session_id === response.session_id
                    ? appendRecordDeltaToDetail(
                      current,
                      event.data.record_id,
                      event.data.delta,
                      event.data.offset,
                      event.data.channel
                    )
                    : current
                );
              }
              if (event.event === "record_completed") {
                prepareConversationMutation(`record-completed:${event.data.record_id}`);
                setConversationDetail((current) =>
                  current?.session_id === response.session_id
                    ? completeStreamingRecordInDetail(current, event.data)
                    : current
                );
              }
              if (event.event === "turn_completed") {
                terminalState.result = "completed";
                markStreamingTurnCompleted(response);
              }
              if (event.event === "turn_cancelled") {
                terminalState.result = "cancelled";
                markStreamingTurnCancelled(response.turn_id);
              }
              if (event.event === "turn_failed") {
                terminalState.result = "failed";
              }
              if (terminalState.result !== null) {
                setConversations((current) => current.map((conversation) =>
                  conversation.session_id === response.session_id
                    ? { ...conversation, pending_turn_status: null }
                    : conversation
                ));
              }
            }
          });
          if (terminalState.result === null) {
            throw new Error("流式连接在轮次结束前断开。");
          }
        } catch (error) {
          if (
            !isCurrent() ||
            isAbortError(error)
          ) {
            return "detached";
          }
          await waitForReconnect(retryDelay, abortController.signal);
          retryDelay = Math.min(5000, retryDelay * 2);
        }
      }
      if (
        terminalState.result !== null &&
        isCurrent()
      ) {
        prepareConversationMutation(`stream-terminal:${response.turn_id}:${terminalState.result}`);
        activeStreamRef.current = null;
        setActiveStreamTurnId(null);
        onTurnSettled();
        await openConversation(response.session_id);
      }
    } catch (error) {
      if (
        !isCurrent() ||
        isAbortError(error)
      ) {
        return "detached";
      }
      throw error;
    } finally {
      if (isCurrent()) {
        activeStreamRef.current = null;
        setActiveStreamTurnId(null);
        onTurnSettled();
      }
      await refreshConversations().catch(() => undefined);
    }
    return terminalState.result ?? "detached";
  }

  return {
    cancelActiveGeneration,
    startResponseStream
  };
}

function waitForReconnect(delay: number, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const onAbort = () => {
      window.clearTimeout(timeout);
      reject(new DOMException("Aborted", "AbortError"));
    };
    const timeout = window.setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolve();
    }, delay);
    signal.addEventListener("abort", onAbort, { once: true });
    if (signal.aborted) onAbort();
  });
}
