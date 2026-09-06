import { useRef } from "react";

export function useConversationElements() {
  const messageRefs = useRef(new Map<string, HTMLElement>());
  const messageListRef = useRef<HTMLDivElement | null>(null);
  const conversationStageRef = useRef<HTMLDivElement | null>(null);
  const conversationSurfaceRef = useRef<HTMLDivElement | null>(null);
  const editingMessageInputRef = useRef<HTMLTextAreaElement | null>(null);
  const composerTextareaRef = useRef<HTMLTextAreaElement | null>(null);
  const composerRef = useRef<HTMLFormElement | null>(null);
  const composerModelControlRef = useRef<HTMLDivElement | null>(null);
  return {
    messageRefs,
    messageListRef,
    conversationStageRef,
    conversationSurfaceRef,
    editingMessageInputRef,
    composerTextareaRef,
    composerRef,
    composerModelControlRef
  };
}
