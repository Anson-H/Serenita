import {
  MutableRefObject,
  RefObject,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef
} from "react";

import type { ConversationMessage } from "../../api/client";
import type { RoutePath } from "../../app/routes";
import type { QuotedContext, ScenarioTab, WorkspaceView } from "./workspaceTypes";

const CONVERSATION_TAIL_THRESHOLD_PX = 24;
const COMPOSER_TEXTAREA_MIN_HEIGHT_PX = 24;
const COMPOSER_TEXTAREA_MAX_HEIGHT_PX = 144;
const COMPOSER_OVERLAY_GAP_PX = 16;
const LATEST_MESSAGE_MIN_VISIBLE_PX = 96;

type UseConversationLayoutOptions = {
  activeScenario: ScenarioTab;
  activeStreamTurnId: string | null;
  activeView: WorkspaceView;
  composerError: string;
  composerRef: RefObject<HTMLFormElement | null>;
  composerText: string;
  composerTextareaRef: RefObject<HTMLTextAreaElement | null>;
  conversationSessionId: string | null;
  conversationStageRef: RefObject<HTMLDivElement | null>;
  conversationSurfaceRef: RefObject<HTMLDivElement | null>;
  highlightedMessageId: string | null;
  messageListRef: RefObject<HTMLDivElement | null>;
  messageRefs: MutableRefObject<Map<string, HTMLElement>>;
  messages: ConversationMessage[];
  onClearQuoteSelection: () => void;
  parentForNextMessage: string | null | undefined;
  quotedContext: QuotedContext | null;
  route: RoutePath;
  uploadedResourcesLength: number;
  uploadingResourcesLength: number;
};

export function useConversationLayout({
  activeScenario,
  activeStreamTurnId,
  activeView,
  composerError,
  composerRef,
  composerText,
  composerTextareaRef,
  conversationSessionId,
  conversationStageRef,
  conversationSurfaceRef,
  highlightedMessageId,
  messageListRef,
  messageRefs,
  messages,
  onClearQuoteSelection,
  parentForNextMessage,
  quotedContext,
  route,
  uploadedResourcesLength,
  uploadingResourcesLength
}: UseConversationLayoutOptions) {
  const lastRenderedConversationSessionRef = useRef<string | null>(null);
  const autoScrollConversationSessionRef = useRef<string | null>(null);
  const shouldFollowConversationTailRef = useRef(true);
  const conversationTailKey = useMemo(
    () => messages.map((message) => `${message.message_id}:${message.status ?? ""}:${message.content.length}`).join("|"),
    [messages]
  );

  useLayoutEffect(() => {
    const sessionId = conversationSessionId ?? null;
    if (lastRenderedConversationSessionRef.current === sessionId) {
      return;
    }
    lastRenderedConversationSessionRef.current = sessionId;
    shouldFollowConversationTailRef.current = true;
    if (messages.length) {
      scrollConversationToLatest("auto");
      return;
    }
    conversationSurfaceRef.current?.scrollTo({ top: 0, behavior: "auto" });
  }, [conversationSessionId, messages.length]);

  useEffect(() => {
    const sessionChanged = autoScrollConversationSessionRef.current !== conversationSessionId;
    autoScrollConversationSessionRef.current = conversationSessionId ?? null;
    if (activeView !== "home" || activeScenario !== "home" || !messages.length || highlightedMessageId) {
      return;
    }
    if (sessionChanged && !activeStreamTurnId) {
      return;
    }
    if (activeStreamTurnId && !shouldFollowConversationTailRef.current) {
      return;
    }
    const frameHandle = window.requestAnimationFrame(() => {
      if (activeStreamTurnId && !shouldFollowConversationTailRef.current) {
        return;
      }
      scrollConversationToLatest(activeStreamTurnId ? "auto" : "smooth");
    });
    return () => window.cancelAnimationFrame(frameHandle);
  }, [activeScenario, activeStreamTurnId, activeView, conversationSessionId, conversationTailKey, highlightedMessageId, messages.length]);

  useEffect(() => {
    if (!highlightedMessageId) {
      return;
    }
    const scrollHandle = window.setTimeout(() => {
      messageRefs.current.get(highlightedMessageId)?.scrollIntoView({
        block: "center",
        behavior: "smooth"
      });
    }, 50);
    return () => window.clearTimeout(scrollHandle);
  }, [conversationSessionId, highlightedMessageId, messageRefs, messages.length]);

  useEffect(() => {
    const frameHandle = window.requestAnimationFrame(resizeComposerTextarea);
    return () => window.cancelAnimationFrame(frameHandle);
  }, [
    activeScenario,
    activeStreamTurnId,
    composerError,
    composerText,
    conversationTailKey,
    parentForNextMessage,
    quotedContext,
    uploadingResourcesLength,
    uploadedResourcesLength
  ]);

  useEffect(() => {
    window.addEventListener("resize", resizeComposerTextarea);
    return () => window.removeEventListener("resize", resizeComposerTextarea);
  }, []);

  useEffect(() => {
    const composer = composerRef.current;
    if (!composer || typeof ResizeObserver === "undefined") {
      return;
    }

    let frameHandle: number | null = null;
    const scheduleComposerMeasurement = () => {
      if (frameHandle !== null) {
        return;
      }
      frameHandle = window.requestAnimationFrame(() => {
        frameHandle = null;
        resizeComposerTextarea();
      });
    };

    const observer = new ResizeObserver(scheduleComposerMeasurement);
    observer.observe(composer);
    scheduleComposerMeasurement();

    return () => {
      if (frameHandle !== null) {
        window.cancelAnimationFrame(frameHandle);
      }
      observer.disconnect();
    };
  }, [activeView, route]);

  function resizeComposerTextarea() {
    const textarea = composerTextareaRef.current;
    if (textarea) {
      textarea.style.height = `${COMPOSER_TEXTAREA_MIN_HEIGHT_PX}px`;
      const textareaBorderHeight = textarea.offsetHeight - textarea.clientHeight;
      const nextHeight = Math.min(
        COMPOSER_TEXTAREA_MAX_HEIGHT_PX,
        Math.max(COMPOSER_TEXTAREA_MIN_HEIGHT_PX, textarea.scrollHeight + textareaBorderHeight)
      );
      textarea.style.height = `${nextHeight}px`;
      textarea.style.overflowY = textarea.scrollHeight + textareaBorderHeight > COMPOSER_TEXTAREA_MAX_HEIGHT_PX ? "auto" : "hidden";
    }

    const composerRect = composerRef.current?.getBoundingClientRect();
    const stage = conversationStageRef.current;
    const surface = conversationSurfaceRef.current;
    if (stage && surface) {
      const surfaceStyle = window.getComputedStyle(surface);
      const surfaceHorizontalBorderWidth =
        Number.parseFloat(surfaceStyle.borderLeftWidth) + Number.parseFloat(surfaceStyle.borderRightWidth);
      const actualScrollbarGutter = Math.max(
        0,
        surface.offsetWidth - surface.clientWidth - surfaceHorizontalBorderWidth
      );
      stage.style.setProperty("--chat-scrollbar-axis-offset", `${actualScrollbarGutter / 2}px`);
    }
    if (composerRect && composerRect.height > 0 && stage) {
      const measuredOverlayHeight = Math.ceil(composerRect.height + COMPOSER_OVERLAY_GAP_PX);
      const cappedOverlayHeight = stage.clientHeight > LATEST_MESSAGE_MIN_VISIBLE_PX
        ? Math.min(measuredOverlayHeight, stage.clientHeight - LATEST_MESSAGE_MIN_VISIBLE_PX)
        : measuredOverlayHeight;
      stage.style.setProperty("--composer-overlay-height", `${cappedOverlayHeight}px`);
    }
  }

  function currentComposerOverlayHeight(surface: HTMLDivElement) {
    const composerHeight = composerRef.current?.getBoundingClientRect().height ?? 0;
    const overlayHeight = composerHeight > 0
      ? composerHeight + COMPOSER_OVERLAY_GAP_PX
      : Number.parseFloat(
          window.getComputedStyle(conversationStageRef.current ?? surface).getPropertyValue("--composer-overlay-height")
        );
    const normalizedOverlayHeight = Number.isFinite(overlayHeight) ? Math.max(0, overlayHeight) : 0;
    return Math.min(
      normalizedOverlayHeight,
      Math.max(0, surface.clientHeight - LATEST_MESSAGE_MIN_VISIBLE_PX)
    );
  }

  function scrollLatestMessageIntoView(surface: HTMLDivElement, behavior: ScrollBehavior) {
    const latestMessage = messageListRef.current?.lastElementChild;
    if (!(latestMessage instanceof HTMLElement)) {
      return false;
    }
    const surfaceRect = surface.getBoundingClientRect();
    const latestMessageRect = latestMessage.getBoundingClientRect();
    const latestMessageBottom = latestMessageRect.bottom - surfaceRect.top + surface.scrollTop;
    const maxScrollTop = Math.max(0, surface.scrollHeight - surface.clientHeight);
    const targetTop = Math.min(
      maxScrollTop,
      Math.max(0, latestMessageBottom - surface.clientHeight + currentComposerOverlayHeight(surface))
    );
    surface.scrollTo({
      top: targetTop,
      behavior
    });
    return true;
  }

  function scrollConversationToLatest(behavior: ScrollBehavior = "smooth") {
    const surface = conversationSurfaceRef.current;
    if (!surface) {
      return;
    }
    shouldFollowConversationTailRef.current = true;
    if (!scrollLatestMessageIntoView(surface, behavior)) {
      surface.scrollTo({
        top: Math.max(0, surface.scrollHeight - surface.clientHeight),
        behavior
      });
    }
    window.requestAnimationFrame(() => {
      const latestSurface = conversationSurfaceRef.current;
      if (!latestSurface) {
        return;
      }
      if (!scrollLatestMessageIntoView(latestSurface, "auto")) {
        latestSurface.scrollTo({
          top: Math.max(0, latestSurface.scrollHeight - latestSurface.clientHeight),
          behavior: "auto"
        });
      }
    });
  }

  function isConversationNearTail(surface: HTMLDivElement) {
    return surface.scrollHeight - surface.scrollTop - surface.clientHeight <= CONVERSATION_TAIL_THRESHOLD_PX;
  }

  function updateConversationScrollState() {
    const surface = conversationSurfaceRef.current;
    if (!surface) {
      return;
    }
    shouldFollowConversationTailRef.current = isConversationNearTail(surface);
    onClearQuoteSelection();
  }

  function markConversationTailShouldFollow() {
    shouldFollowConversationTailRef.current = true;
  }

  return {
    markConversationTailShouldFollow,
    resizeComposerTextarea,
    scrollConversationToLatest,
    updateConversationScrollState
  };
}
