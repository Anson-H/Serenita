import {
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
  type KeyboardEvent,
  type ReactNode,
  type Ref,
  type RefObject
} from "react";

import type { UploadedResource } from "../../api/client";
import {
  ArrowUpIcon,
  PaperclipIcon,
  StopIcon
} from "../../components/icons";
import {
  isImeComposing,
  keepTextControlFocused,
  syncCommittedText
} from "../../utils/inputMethod";
import type { ComposerSubmitShortcut } from "../accountPreferences/composerSubmitShortcut";
import type { AnnotationContextResource, UploadingResource } from "./contextResources";
import { ContextWindowUsageIndicator } from "./ContextWindowUsageIndicator";
import type { ContextWindowUsage } from "./modelTokenUsage";

type ConversationComposerProps = {
  attachmentCapabilitiesError?: string;
  onRetryAttachmentCapabilities?: () => void;
  activeStreamTurnId: string | null;
  canAttachFiles: boolean;
  cancellingTurnId: string | null;
  composerRef: Ref<HTMLFormElement>;
  composerSubmitShortcut: ComposerSubmitShortcut;
  composerTextareaRef: RefObject<HTMLTextAreaElement | null>;
  composerText: string;
  contextWindowUsage: ContextWindowUsage | null;
  conversationEnabled: boolean;
  onCancelActiveGeneration: () => void;
  onComposerTextChange: (text: string) => void;
  onFileUpload: (event: ChangeEvent<HTMLInputElement>) => void | Promise<void>;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void | Promise<void>;
  annotatedContexts: AnnotationContextResource[];
  renderComposerModelControl: () => ReactNode;
  renderAnnotationContextChip: (annotations: AnnotationContextResource[]) => ReactNode;
  renderUploadedResourceChip: (resource: UploadedResource) => ReactNode;
  renderUploadingResourceChip: (resource: UploadingResource) => ReactNode;
  queuedInputPanel?: ReactNode;
  queuedInputCount?: number;
  selectedModelFileMimeTypes: string[];
  selectedScenarioPlaceholder: string;
  sending: boolean;
  uploadedResources: UploadedResource[];
  uploadingResources: UploadingResource[];
};

export function shouldSubmitComposerFromKeyDown(
  event: Pick<
    KeyboardEvent<HTMLTextAreaElement>,
    "ctrlKey" | "key" | "keyCode" | "metaKey" | "nativeEvent" | "repeat"
  >,
  shortcut: ComposerSubmitShortcut
) {
  if (event.key !== "Enter" || event.repeat || isImeComposing(event)) {
    return false;
  }
  const modifierPressed = event.metaKey || event.ctrlKey;
  return shortcut === "enter" ? !modifierPressed : modifierPressed;
}

export function ConversationComposer({
  activeStreamTurnId,
  canAttachFiles,
  cancellingTurnId,
  composerRef,
  composerSubmitShortcut,
  composerTextareaRef,
  composerText,
  contextWindowUsage,
  conversationEnabled,
  onCancelActiveGeneration,
  onComposerTextChange,
  onFileUpload,
  onSubmit,
  annotatedContexts,
  renderComposerModelControl,
  renderAnnotationContextChip,
  renderUploadedResourceChip,
  renderUploadingResourceChip,
  queuedInputPanel,
  queuedInputCount = 0,
  selectedModelFileMimeTypes,
  attachmentCapabilitiesError,
  onRetryAttachmentCapabilities,
  selectedScenarioPlaceholder,
  sending,
  uploadedResources,
  uploadingResources
}: ConversationComposerProps) {
  const hasDraftContent = Boolean(
    composerText.trim() || uploadedResources.length ||
    uploadingResources.length || annotatedContexts.length
  );
  const hasAuxiliaryContent = Boolean(
    queuedInputPanel || annotatedContexts.length ||
    uploadingResources.length || uploadedResources.length
  );
  const auxiliaryItemCount = queuedInputCount
    + annotatedContexts.length
    + uploadingResources.length
    + uploadedResources.length;
  const auxiliaryTrayId = useId();
  const auxiliaryDetailsRef = useRef<HTMLDetailsElement>(null);
  const auxiliarySummaryRef = useRef<HTMLElement>(null);
  const extremeHeight = useComposerExtremeHeight(
    auxiliaryDetailsRef,
    hasAuxiliaryContent
  );
  const [auxiliaryTrayOpen, setAuxiliaryTrayOpen] = useState(false);

  useLayoutEffect(() => {
    if (!extremeHeight) {
      setAuxiliaryTrayOpen(false);
      return;
    }
    const details = auxiliaryDetailsRef.current;
    const activeElement = details?.ownerDocument.activeElement;
    setAuxiliaryTrayOpen(false);
    if (
      !details ||
      !(activeElement instanceof HTMLElement) ||
      activeElement === auxiliarySummaryRef.current ||
      !details.contains(activeElement)
    ) {
      return;
    }
    const frame = window.requestAnimationFrame(() => {
      auxiliarySummaryRef.current?.focus({ preventScroll: true });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [extremeHeight]);

  const showStopButton = activeStreamTurnId && !hasDraftContent && !sending;
  return (
    <form
      className="conversation-composer"
      data-has-auxiliary-content={hasAuxiliaryContent ? "true" : undefined}
      onSubmit={onSubmit}
      ref={composerRef}
    >
      <div className="assistant-composer conversation-composer-surface" data-input-surface="secondary">
        {attachmentCapabilitiesError ? (
          <div role="alert" className="composer-error">
            {attachmentCapabilitiesError}
            <button type="button" className="control control--compact" onClick={onRetryAttachmentCapabilities}>重试附件能力</button>
          </div>
        ) : null}
        {hasAuxiliaryContent ? (
          <details
            className="conversation-composer-auxiliary"
            onKeyDown={(event) => {
              if (event.key !== "Escape" || !extremeHeight || !event.currentTarget.open) {
                return;
              }
              event.preventDefault();
              event.stopPropagation();
              setAuxiliaryTrayOpen(false);
              window.requestAnimationFrame(() => {
                auxiliarySummaryRef.current?.focus({ preventScroll: true });
              });
            }}
            onToggle={(event) => {
              if (extremeHeight) {
                setAuxiliaryTrayOpen(event.currentTarget.open);
              }
            }}
            open={!extremeHeight || auxiliaryTrayOpen}
            ref={auxiliaryDetailsRef}
          >
            <summary
              aria-controls={auxiliaryTrayId}
              aria-label={`查看队列与上下文，共 ${auxiliaryItemCount} 项`}
              className="conversation-composer-auxiliary-summary"
              ref={auxiliarySummaryRef}
              title={`查看队列与上下文（${auxiliaryItemCount}）`}
            >
              <span className="conversation-composer-auxiliary-summary-label">
                队列与上下文
              </span>
              <span aria-hidden="true" className="conversation-composer-auxiliary-count">
                +{auxiliaryItemCount}
              </span>
            </summary>
            <div
              aria-label="队列与上下文"
              className="conversation-composer-auxiliary-tray scroll-balanced"
              id={auxiliaryTrayId}
              role="region"
            >
              {queuedInputPanel}
              {annotatedContexts.length || uploadingResources.length || uploadedResources.length ? (
                <div className="conversation-composer-resources">
                  {annotatedContexts.length ? (
                    <div className="resource-list annotation-context-list">
                      {renderAnnotationContextChip(annotatedContexts)}
                    </div>
                  ) : null}
                  {uploadingResources.length || uploadedResources.length ? (
                    <div className="resource-list file-context-list">
                      {uploadingResources.map((resource) => renderUploadingResourceChip(resource))}
                      {uploadedResources.map((resource) => renderUploadedResourceChip(resource))}
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
          </details>
        ) : null}
        <div className="conversation-composer-main-row">
          <div className="composer-input-frame" data-input-area>
            <textarea
              aria-keyshortcuts={
                composerSubmitShortcut === "enter"
                  ? "Enter"
                  : "Control+Enter Meta+Enter"
              }
              aria-label="输入健康问题"
              disabled={!conversationEnabled || sending}
              name="message"
              onChange={(event) => onComposerTextChange(event.target.value)}
              onCompositionEnd={(event) => syncCommittedText(event, onComposerTextChange)}
              onKeyDown={(event) => {
                if (event.key !== "Enter" || isImeComposing(event)) return;
                event.preventDefault();
                if (event.repeat) return;
                if (shouldSubmitComposerFromKeyDown(event, composerSubmitShortcut)) {
                  event.currentTarget.form?.requestSubmit();
                  return;
                }
                const textarea = event.currentTarget;
                const selectionStart = textarea.selectionStart ?? textarea.value.length;
                const selectionEnd = textarea.selectionEnd ?? selectionStart;
                textarea.setRangeText("\n", selectionStart, selectionEnd, "end");
                onComposerTextChange(textarea.value);
              }}
              placeholder={selectedScenarioPlaceholder}
              ref={composerTextareaRef}
              rows={2}
              value={composerText}
            />
          </div>
          <div className="composer-footer">
            {canAttachFiles ? (
              <label aria-label="附加文件" className="control control--inline control--icon control--ghost file-button icon-button" title="附加文件">
                <PaperclipIcon />
                <input
                  accept={selectedModelFileMimeTypes.join(",")}
                  aria-label="附加文件"
                  multiple
                  onChange={onFileUpload}
                  type="file"
                />
              </label>
            ) : null}
            {contextWindowUsage ? (
              <ContextWindowUsageIndicator usage={contextWindowUsage} />
            ) : null}
            {renderComposerModelControl()}
            {showStopButton ? (
              <button
                aria-label="停止生成"
                className="control control--inline control--icon control--ghost command-button send-button stop-button"
                disabled={Boolean(cancellingTurnId)}
                onClick={onCancelActiveGeneration}
                title="停止生成"
                type="button"
              >
                <StopIcon />
              </button>
            ) : <button
              aria-label={sending ? "发送中..." : "发送"}
              className="control control--inline control--icon control--ghost command-button send-button"
              disabled={sending || !conversationEnabled || Boolean(uploadingResources.length)}
              onMouseDown={keepTextControlFocused}
              title={activeStreamTurnId ? "加入等候队列" : sending ? "发送中..." : "发送"}
              type="submit"
            >
              {sending ? <span aria-hidden="true">...</span> : <ArrowUpIcon />}
            </button>}
          </div>
        </div>
      </div>
    </form>
  );
}

function useComposerExtremeHeight(
  detailsRef: RefObject<HTMLDetailsElement | null>,
  active: boolean
) {
  const [extremeHeight, setExtremeHeight] = useState(false);

  useLayoutEffect(() => {
    if (!active) {
      setExtremeHeight(false);
      return;
    }

    const details = detailsRef.current;
    const composer = details?.closest<HTMLElement>(".conversation-composer");
    if (!details || !composer) {
      return;
    }

    const updateHeightMode = () => {
      let element: HTMLElement | null = details;
      while (element) {
        const value = element.getAttribute("data-height-extreme");
        if (value !== null && value !== "false") {
          setExtremeHeight(true);
          return;
        }
        element = element.parentElement;
      }
      setExtremeHeight(false);
    };

    updateHeightMode();
    const observer = new MutationObserver(updateHeightMode);
    observer.observe(composer, {
      attributeFilter: ["data-height-extreme"],
      attributes: true
    });
    return () => observer.disconnect();
  }, [active, detailsRef]);

  return extremeHeight;
}
