import { StrictMode, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";

import type {
  ConversationMessage,
  QueuedConversationInput
} from "../../src/api/client";
import { ConversationComposer } from "../../src/features/conversations/ConversationComposer";
import { ComposerModelControl } from "../../src/features/conversations/ComposerModelControl";
import { HomeWorkspace } from "../../src/features/conversations/HomeWorkspace";
import { QueuedInputPanel } from "../../src/features/conversations/QueuedInputPanel";
import { useConversationLayout } from "../../src/features/conversations/useConversationLayout";
import "../../src/styles/index.css";
import "./conversation-overlay-geometry.css";

const QUEUED_INPUTS: QueuedConversationInput[] = Array.from(
  { length: 3 },
  (_, index) => ({
    input_id: `geometry-queued-${index + 1}`,
    content: `短屏队列操作 ${index + 1}`,
    model_id: "geometry-model",
    thinking_mode: "low",
    context_resources: [],
    created_at: "2026-09-04T00:00:00Z",
    position: index
  })
);
const EMPTY_CONVERSATION = new URLSearchParams(window.location.search).has("empty");

const REPORT_COMPOSER = new URLSearchParams(window.location.search).has("report");

function ConversationOverlayGeometryFixture() {
  const modelControlRef = useRef<HTMLDivElement>(null);
  const [modelPickerOpen, setModelPickerOpen] = useState(false);
  const [thinkingMode, setThinkingMode] = useState("low");
  const composerRef = useRef<HTMLFormElement>(null);
  const composerTextareaRef = useRef<HTMLTextAreaElement>(null);
  const conversationStageRef = useRef<HTMLDivElement>(null);
  const conversationSurfaceRef = useRef<HTMLDivElement>(null);
  const messageListRef = useRef<HTMLDivElement>(null);
  const messageRefs = useRef(new Map<string, HTMLElement>());
  const [composerText, setComposerText] = useState("");
  const [queueActionClicks, setQueueActionClicks] = useState(0);
  const [tailClicks, setTailClicks] = useState(0);
  const messages = useMemo<ConversationMessage[]>(() => EMPTY_CONVERSATION
    ? []
    : [{
        record_id: "geometry-record",
        message_id: "geometry-message",
        turn_id: "geometry-turn",
        parent_message_id: null,
        kind: "assistant",
        role: "assistant",
        content: "用于生产布局几何验收的消息。",
        status: "completed",
        created_at: "2026-09-04T00:00:00Z"
      }], []);
  const queuedInputs = EMPTY_CONVERSATION ? [] : QUEUED_INPUTS;

  const layout = useConversationLayout({
    activeScenario: "home",
    activeStreamTurnId: null,
    composerError: "",
    composerRef,
    composerText,
    composerTextareaRef,
    conversationEnabled: true,
    messageListRef,
    conversationSessionId: "geometry-session",
    conversationStageRef,
    conversationSurfaceRef,
    highlightedMessageId: null,
    highlightedMessageRequestId: 0,
    messageRefs,
    onClearAnnotationSelection: () => undefined,
    annotatedContexts: [],
    queuedInputsLength: queuedInputs.length,
    route: "/",
    uploadedResourcesLength: 0,
    uploadingResourcesLength: 0
  });

  const composer = (
    <ConversationComposer
      activeStreamTurnId={null}
      canAttachFiles
      cancellingTurnId={null}
      composerRef={layout.bindComposerElement}
      composerSubmitShortcut="enter"
      composerTextareaRef={composerTextareaRef}
      composerText={composerText}
      contextWindowUsage={{
        percent: 25,
        usedTokens: 8_000,
        contextWindowTokens: 32_000
      }}
      conversationEnabled
      onCancelActiveGeneration={() => undefined}
      onComposerTextChange={setComposerText}
      onFileUpload={() => undefined}
      onSubmit={(event) => event.preventDefault()}
      annotatedContexts={[]}
      queuedInputCount={queuedInputs.length}
      queuedInputPanel={queuedInputs.length ? (
        <QueuedInputPanel
          items={queuedInputs}
          resourceUrl={() => "#geometry-resource"}
          onDelete={() => undefined}
          onEdit={() => undefined}
          onReorder={() => undefined}
          onRunNow={() => setQueueActionClicks((current) => current + 1)}
        />
      ) : null}
      renderComposerModelControl={() => REPORT_COMPOSER ? (
        <ComposerModelControl controlRef={modelControlRef} currentModelName="测试模型"
          currentThinkingLabel={thinkingMode} modelPickerOpen={modelPickerOpen} models={[]}
          onChooseModel={() => undefined} onChooseThinkingMode={setThinkingMode}
          onSetModelPickerOpen={setModelPickerOpen} selectedModel={undefined}
          selectedThinkingModes={["low", "high"]} thinkingMode={thinkingMode}
          thinkingModeLabel={(mode) => mode} />
      ) : (
        <div className="composer-model-control">
          <button
            aria-label="测试模型与推理强度"
            className="control control--inline control--icon control--ghost composer-model-trigger"
            type="button"
          >
            <span aria-hidden="true">M</span>
          </button>
        </div>
      )}
      renderAnnotationContextChip={() => null}
      renderUploadedResourceChip={() => null}
      renderUploadingResourceChip={() => null}
      selectedModelFileMimeTypes={[]}
      selectedScenarioPlaceholder="短屏输入可用性验收"
      sending={false}
      uploadedResources={[]}
      uploadingResources={[]}
    />
  );

  if (REPORT_COMPOSER) return (
    <article className="report-detail-pane" data-composer-stage style={{height: "100dvh"}}>
      <div className="report-detail-scroll scroll-content">
        <div style={{height: 2000}}>报告内容</div><button>报告末尾</button>
      </div>
      <section className="report-detail-composer"><div className="conversation-composer-slot">{composer}</div></section>
    </article>
  );

  return (
    <div
      className="conversation-overlay-geometry-fixture"
      data-empty-conversation={EMPTY_CONVERSATION ? "true" : "false"}
      data-queue-action-clicks={queueActionClicks}
      data-tail-clicks={tailClicks}
    >
      <HomeWorkspace
        annotationSelection={null}
        composer={composer}
        conversationStageRef={conversationStageRef}
        conversationSurfaceRef={conversationSurfaceRef}
        conversationTailButtonVisible
        messageItems={(
          <div className="conversation-turn geometry-message">
            <article
              className="message-entry assistant"
              data-message-id="geometry-message"
              ref={(node) => {
                if (node) {
                  messageRefs.current.set("geometry-message", node);
                } else {
                  messageRefs.current.delete("geometry-message");
                }
              }}
            >
              <div className="message-bubble assistant">
                用于生产布局几何验收的消息。
              </div>
            </article>
          </div>
        )}
        messageListRef={messageListRef}
        messagesLength={messages.length}
        onAddSelectedTextToConversation={() => undefined}
        onConversationDisclosureAnchor={() => undefined}
        onReturnToLatest={() => {
          layout.returnToLatest();
          setTailClicks((current) => current + 1);
        }}
        sidebarToggle={null}
        workspaceTitle="短屏几何验收"
      />
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ConversationOverlayGeometryFixture />
  </StrictMode>
);
