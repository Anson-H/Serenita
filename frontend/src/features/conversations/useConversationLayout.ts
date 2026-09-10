import {
  type MutableRefObject,
  type RefCallback,
  type RefObject,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef
} from "react";

import type { RoutePath } from "../../app/routes";
import { useConversationScrollController } from "./useConversationScrollController";
import type { AnnotatedContext, ScenarioTab } from "./workspaceTypes";

const COMPOSER_TEXTAREA_MIN_HEIGHT_PX = 40;
const COMPOSER_TEXTAREA_MAX_HEIGHT_PX = 140;
const CONVERSATION_PREFERRED_VISIBLE_HEIGHT_PX = 96;
const CONVERSATION_HARD_VISIBLE_HEIGHT_PX = 48;
const CONVERSATION_TAIL_BUTTON_HEIGHT_PX = 40;
const CONVERSATION_TAIL_BUTTON_GAP_PX = 8;
const CONVERSATION_TAIL_BUTTON_EDGE_PX = 4;
const COMPOSER_COMPACT_CHROME_HEIGHT_PX = 64;
const COMPOSER_AUXILIARY_USABLE_HEIGHT_PX = 120;

type UseConversationLayoutOptions = {
  activeScenario: ScenarioTab;
  activeStreamTurnId: string | null;
  composerError: string;
  composerRef: RefObject<HTMLFormElement | null>;
  composerText: string;
  composerTextareaRef: RefObject<HTMLTextAreaElement | null>;
  conversationEnabled: boolean;
  messageListRef: RefObject<HTMLDivElement | null>;
  conversationSessionId: string | null;
  conversationStageRef: RefObject<HTMLDivElement | null>;
  conversationSurfaceRef: RefObject<HTMLDivElement | null>;
  highlightedMessageId: string | null;
  highlightedMessageRequestId: number;
  messageRefs: MutableRefObject<Map<string, HTMLElement>>;
  onClearAnnotationSelection: () => void;
  annotatedContexts: AnnotatedContext[];
  route: RoutePath;
  queuedInputsLength?: number;
  uploadedResourcesLength: number;
  uploadingResourcesLength: number;
};

type VisibleStageGeometry = {
  bottom: number;
  height: number;
  left: number;
  right: number;
  top: number;
  width: number;
};

function visibleStageGeometry(stageRect: DOMRect): VisibleStageGeometry {
  const viewport = window.visualViewport;
  const viewportTop = viewport?.offsetTop ?? 0;
  const viewportBottom = viewport
    ? viewport.offsetTop + viewport.height
    : window.innerHeight;
  const viewportLeft = viewport?.offsetLeft ?? 0;
  const viewportRight = viewport
    ? viewport.offsetLeft + viewport.width
    : window.innerWidth;
  const top = Math.max(stageRect.top, viewportTop);
  const bottom = Math.min(stageRect.bottom, viewportBottom);
  const left = Math.max(stageRect.left, viewportLeft);
  const right = Math.min(stageRect.right, viewportRight);
  return {
    bottom,
    height: Math.max(0, bottom - top),
    left,
    right,
    top,
    width: Math.max(0, right - left)
  };
}

function finiteCssLength(value: string, fallback = 0) {
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function setBooleanDataAttribute(
  element: HTMLElement,
  name: "heightCompact" | "heightExtreme",
  value: boolean
) {
  if (value) {
    element.dataset[name] = "true";
  } else {
    delete element.dataset[name];
  }
}

export function useConversationLayout({
  activeScenario,
  activeStreamTurnId,
  composerError,
  composerRef,
  composerText,
  composerTextareaRef,
  conversationEnabled,
  messageListRef,
  conversationSessionId,
  conversationStageRef,
  conversationSurfaceRef,
  highlightedMessageId,
  highlightedMessageRequestId,
  messageRefs,
  onClearAnnotationSelection,
  annotatedContexts,
  route,
  queuedInputsLength = 0,
  uploadedResourcesLength,
  uploadingResourcesLength
}: UseConversationLayoutOptions) {
  const composerObserverRef = useRef<ResizeObserver | null>(null);
  const observedComposerRef = useRef<HTMLFormElement | null>(null);
  const composerMeasurementFrameRef = useRef<number | null>(null);
  const measurementRunningRef = useRef(false);
  const bindingKey = `${activeScenario}:${route}:${conversationEnabled ? "on" : "off"}`;
  const scrollController = useConversationScrollController({
    bindingKey,
    conversationSessionId,
    conversationStageRef,
    conversationSurfaceRef,
    highlightedMessageId,
    highlightedMessageRequestId,
    messageListRef,
    messageRefs,
    onClearAnnotationSelection
  });
  const invalidateScrollGeometryRef = useRef(scrollController.invalidateGeometry);
  invalidateScrollGeometryRef.current = scrollController.invalidateGeometry;

  const resizeComposerTextarea = useCallback(() => {
    if (measurementRunningRef.current) {
      return;
    }
    const composer = composerRef.current;
    const textarea = composerTextareaRef.current;
    const stage = composer?.closest<HTMLElement>("[data-composer-stage]") ?? conversationStageRef.current;
    if (!composer || !stage) {
      return;
    }
    measurementRunningRef.current = true;
    try {
      const stageRect = stage.getBoundingClientRect();
      const visibleStage = visibleStageGeometry(stageRect);
      const stageStyle = window.getComputedStyle(stage);
      const contentGap = finiteCssLength(
        stageStyle.getPropertyValue("--space-content")
      );
      const relatedGap = finiteCssLength(
        stageStyle.getPropertyValue("--space-related")
      );
      const itemGap = finiteCssLength(
        stageStyle.getPropertyValue("--space-item")
      );
      const visualBottomOffset = Math.max(0, stageRect.bottom - visibleStage.bottom);
      const visualLeftOffset = Math.max(0, visibleStage.left - stageRect.left);
      const visualRightOffset = Math.max(0, stageRect.right - visibleStage.right);
      stage.style.setProperty(
        "--composer-visual-bottom-offset",
        `${Math.ceil(visualBottomOffset)}px`
      );
      stage.style.setProperty(
        "--composer-visible-left-offset",
        `${Math.floor(visualLeftOffset)}px`
      );
      stage.style.setProperty(
        "--composer-visible-right-offset",
        `${Math.floor(visualRightOffset)}px`
      );
      stage.style.setProperty(
        "--composer-visible-viewport-width",
        `${Math.floor(visibleStage.width)}px`
      );
      stage.style.setProperty(
        "--composer-visible-viewport-height",
        `${Math.floor(visibleStage.height)}px`
      );
      composer.style.setProperty(
        "--composer-visible-viewport-height",
        `${Math.floor(visibleStage.height)}px`
      );

      const previousComposerRect = composer.getBoundingClientRect();
      const currentlyExtreme =
        stage.dataset.heightExtreme === "true" ||
        composer.dataset.heightExtreme === "true";
      const visibleBottomInset = Math.max(
        0,
        visibleStage.bottom - previousComposerRect.bottom
      );
      const estimatedSafeAreaBottom = Math.max(
        0,
        visibleBottomInset - (currentlyExtreme ? itemGap : contentGap)
      );
      const stableBottomInset = contentGap + estimatedSafeAreaBottom;

      // Measure the current unconstrained content. A cached height from the first
      // layout can keep a short window compact after its content or width changes.
      for (const element of [stage, composer]) {
        setBooleanDataAttribute(element, "heightCompact", false);
        setBooleanDataAttribute(element, "heightExtreme", false);
        element.style.removeProperty("--composer-max-height");
      }

      if (textarea) {
        textarea.style.height = `${COMPOSER_TEXTAREA_MIN_HEIGHT_PX}px`;
        const borderHeight = textarea.offsetHeight - textarea.clientHeight;
        const naturalHeight = Math.min(
          COMPOSER_TEXTAREA_MAX_HEIGHT_PX,
          Math.max(
            COMPOSER_TEXTAREA_MIN_HEIGHT_PX,
            textarea.scrollHeight + borderHeight
          )
        );
        textarea.style.height = `${naturalHeight}px`;
        textarea.style.overflowY =
          textarea.scrollHeight + borderHeight > COMPOSER_TEXTAREA_MAX_HEIGHT_PX
            ? "auto"
            : "hidden";
      }

      let composerRect = composer.getBoundingClientRect();
      const desiredOverlayHeight = Math.ceil(
        Math.max(composerRect.height, composer.scrollHeight) +
        stableBottomInset +
        contentGap
      );
      const preferredComposerBudget = Math.max(
        0,
        visibleStage.height -
        CONVERSATION_PREFERRED_VISIBLE_HEIGHT_PX -
        stableBottomInset -
        contentGap
      );
      const preferredOverlayBudget = Math.max(
        0,
        visibleStage.height - CONVERSATION_PREFERRED_VISIBLE_HEIGHT_PX
      );
      const hasAuxiliaryContent = Boolean(
        queuedInputsLength ||
        annotatedContexts.length ||
        uploadedResourcesLength ||
        uploadingResourcesLength
      );
      const compact =
        desiredOverlayHeight > preferredOverlayBudget ||
        (hasAuxiliaryContent &&
          preferredComposerBudget <= COMPOSER_AUXILIARY_USABLE_HEIGHT_PX);
      const extreme = compact && preferredComposerBudget < COMPOSER_AUXILIARY_USABLE_HEIGHT_PX;
      const reservedConversationHeight = extreme
        ? CONVERSATION_HARD_VISIBLE_HEIGHT_PX
        : CONVERSATION_PREFERRED_VISIBLE_HEIGHT_PX;
      const composerHeightBudget = Math.max(
        compact ? COMPOSER_COMPACT_CHROME_HEIGHT_PX : COMPOSER_TEXTAREA_MIN_HEIGHT_PX,
        visibleStage.height - reservedConversationHeight - stableBottomInset - contentGap
      );

      setBooleanDataAttribute(stage, "heightCompact", compact);
      setBooleanDataAttribute(stage, "heightExtreme", extreme);
      setBooleanDataAttribute(composer, "heightCompact", compact);
      setBooleanDataAttribute(composer, "heightExtreme", extreme);
      if (compact) {
        const composerMaxHeight = `${Math.floor(composerHeightBudget)}px`;
        stage.style.setProperty("--composer-max-height", composerMaxHeight);
        composer.style.setProperty("--composer-max-height", composerMaxHeight);
      } else {
        stage.style.removeProperty("--composer-max-height");
        composer.style.removeProperty("--composer-max-height");
      }

      if (textarea && compact) {
        textarea.style.height = `${COMPOSER_TEXTAREA_MIN_HEIGHT_PX}px`;
        textarea.style.overflowY = "auto";
      }

      composerRect = composer.getBoundingClientRect();
      const trayMaxHeight = Math.max(
        0,
        composerRect.top - visibleStage.top - relatedGap
      );
      const trayMaxHeightValue = `${Math.floor(trayMaxHeight)}px`;
      stage.style.setProperty("--composer-tray-max-height", trayMaxHeightValue);
      composer.style.setProperty("--composer-tray-max-height", trayMaxHeightValue);
      const rawOverlayHeight = Math.ceil(
        stageRect.bottom - composerRect.top + contentGap
      );
      const maximumOverlayHeight = Math.max(
        0,
        stageRect.bottom - visibleStage.top - CONVERSATION_HARD_VISIBLE_HEIGHT_PX
      );
      const effectiveOverlayHeight = Math.max(
        0,
        Math.min(rawOverlayHeight, maximumOverlayHeight)
      );
      const previousOverlayHeight = finiteCssLength(
        stageStyle.getPropertyValue("--composer-overlay-height"),
        -1
      );
      stage.style.setProperty(
        "--composer-overlay-height",
        `${effectiveOverlayHeight}px`
      );

      const desiredButtonTop =
        composerRect.top -
        stageRect.top -
        CONVERSATION_TAIL_BUTTON_GAP_PX -
        CONVERSATION_TAIL_BUTTON_HEIGHT_PX;
      const minimumButtonTop =
        visibleStage.top - stageRect.top + CONVERSATION_TAIL_BUTTON_EDGE_PX;
      const maximumButtonTop = Math.max(
        minimumButtonTop,
        visibleStage.bottom -
        stageRect.top -
        CONVERSATION_TAIL_BUTTON_HEIGHT_PX -
        CONVERSATION_TAIL_BUTTON_EDGE_PX
      );
      const buttonTop = Math.min(
        maximumButtonTop,
        Math.max(minimumButtonTop, desiredButtonTop)
      );
      stage.style.setProperty(
        "--conversation-tail-button-top",
        `${Math.floor(buttonTop)}px`
      );

      if (Math.abs(previousOverlayHeight - effectiveOverlayHeight) > 1) {
        invalidateScrollGeometryRef.current("composer-resize");
      }
    } finally {
      measurementRunningRef.current = false;
    }
  }, [
    annotatedContexts.length,
    composerRef,
    composerTextareaRef,
    conversationStageRef,
    queuedInputsLength,
    uploadedResourcesLength,
    uploadingResourcesLength
  ]);

  const scheduleComposerMeasurement = useCallback(() => {
    if (composerMeasurementFrameRef.current !== null) {
      return;
    }
    composerMeasurementFrameRef.current = window.requestAnimationFrame(() => {
      composerMeasurementFrameRef.current = null;
      resizeComposerTextarea();
    });
  }, [resizeComposerTextarea]);

  const bindComposerElement = useCallback<RefCallback<HTMLFormElement>>((node) => {
    (composerRef as MutableRefObject<HTMLFormElement | null>).current = node;
    if (node === observedComposerRef.current) {
      if (node && !composerObserverRef.current && typeof ResizeObserver !== "undefined") {
        composerObserverRef.current = new ResizeObserver(scheduleComposerMeasurement);
        composerObserverRef.current.observe(node);
      }
      scheduleComposerMeasurement();
      return;
    }
    composerObserverRef.current?.disconnect();
    composerObserverRef.current = null;
    observedComposerRef.current = node;
    const stage = node?.closest<HTMLElement>("[data-composer-stage]") ?? conversationStageRef.current;
    if (node && stage) {
      setBooleanDataAttribute(stage, "heightCompact", false);
      setBooleanDataAttribute(stage, "heightExtreme", false);
      setBooleanDataAttribute(node, "heightCompact", false);
      setBooleanDataAttribute(node, "heightExtreme", false);
    }
    if (node && typeof ResizeObserver !== "undefined") {
      composerObserverRef.current = new ResizeObserver(scheduleComposerMeasurement);
      composerObserverRef.current.observe(node);
    }
    scheduleComposerMeasurement();
  }, [composerRef, conversationStageRef, scheduleComposerMeasurement]);

  useLayoutEffect(() => {
    bindComposerElement(composerRef.current);
  });

  useEffect(() => {
    scheduleComposerMeasurement();
  }, [
    activeScenario,
    activeStreamTurnId,
    annotatedContexts,
    composerError,
    composerText,
    route,
    scheduleComposerMeasurement,
    uploadedResourcesLength,
    uploadingResourcesLength
  ]);

  useEffect(() => {
    const handleViewportChange = () => scheduleComposerMeasurement();
    window.addEventListener("resize", handleViewportChange);
    window.visualViewport?.addEventListener("resize", handleViewportChange);
    window.visualViewport?.addEventListener("scroll", handleViewportChange);
    return () => {
      window.removeEventListener("resize", handleViewportChange);
      window.visualViewport?.removeEventListener("resize", handleViewportChange);
      window.visualViewport?.removeEventListener("scroll", handleViewportChange);
    };
  }, [scheduleComposerMeasurement]);

  useEffect(() => () => {
    composerObserverRef.current?.disconnect();
    composerObserverRef.current = null;
    if (composerMeasurementFrameRef.current !== null) {
      window.cancelAnimationFrame(composerMeasurementFrameRef.current);
      composerMeasurementFrameRef.current = null;
    }
  }, []);

  return {
    ...scrollController,
    bindComposerElement,
    resizeComposerTextarea
  };
}
