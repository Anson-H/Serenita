import { useRef, useState } from "react";

export function useConversationEditingState() {
  const [highlightedMessageId, setHighlightedMessageId] = useState<string | null>(null);
  const [highlightedMessageRequestId, setHighlightedMessageRequestId] = useState(0);
  const [editingMessageId, setEditingMessageId] = useState<string | null>(null);
  const [editingMessageText, setEditingMessageText] = useState("");
  const [editingMessageContextResources, setEditingMessageContextResources] = useState<Array<Record<string, unknown>>>([]);
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);
  const copySuccessTimeoutRef = useRef<number | null>(null);
  return {
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
  };
}
