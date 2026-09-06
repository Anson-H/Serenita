import {
  StrictMode,
  type RefCallback,
  useCallback,
  useEffect,
  useRef,
  useState
} from "react";
import { createRoot } from "react-dom/client";

import type { ConversationMessage } from "../../src/api/client";
import { useConversationLayout } from "../../src/features/conversations/useConversationLayout";
import "../../src/styles/index.css";
import "./conversation-scroll-controller.css";

type FixtureMessage = ConversationMessage & {
  blockHeight: number;
  containsAsyncMedia?: boolean;
  label: string;
};

const SESSION_ID = "browser-scroll-fixture";
const SOURCE_MESSAGE_ID = "fixture-message-9";
const LONG_SOURCE_MESSAGE_ID = "fixture-message-500";
const TRANSPARENT_PIXEL =
  "data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs=";

function makeMessage(index: number, blockHeight = 124): FixtureMessage {
  const messageId = `fixture-message-${index}`;
  return {
    blockHeight,
    content: `第 ${index} 条夹具消息`,
    created_at: "2026-09-04T00:00:00Z",
    kind: index % 2 ? "assistant" : "user",
    label: `消息 ${index}`,
    message_id: messageId,
    parent_message_id: index > 1 ? `fixture-message-${index - 1}` : null,
    record_id: `fixture-record-${index}`,
    role: index % 2 ? "assistant" : "user",
    turn_id: `fixture-turn-${Math.ceil(index / 2)}`
  } as FixtureMessage;
}

function initialMessages() {
  return Array.from({ length: 18 }, (_, index) => ({
    ...makeMessage(index + 1),
    containsAsyncMedia: index === 17
  }));
}

function FixtureMessageRow({
  asyncMediaHeight,
  message,
  mediaRef,
  registerMessageElement
}: {
  asyncMediaHeight: number;
  message: FixtureMessage;
  mediaRef: React.RefObject<HTMLImageElement | null>;
  registerMessageElement: (messageId: string, node: HTMLElement | null) => void;
}) {
  const register = useCallback<RefCallback<HTMLElement>>((node) => {
    registerMessageElement(message.message_id, node);
  }, [message.message_id, registerMessageElement]);

  return (
    <article
      className="message-entry fixture-message"
      data-message-id={message.message_id}
      ref={register}
      style={message.containsAsyncMedia ? undefined : { height: `${message.blockHeight}px` }}
    >
      <strong>{message.label}</strong>
      <span>{message.content}</span>
      {message.containsAsyncMedia ? (
        <img
          alt="异步内容增长夹具"
          className="fixture-async-media"
          ref={mediaRef}
          src={TRANSPARENT_PIXEL}
          style={{ height: `${asyncMediaHeight}px` }}
        />
      ) : null}
    </article>
  );
}

function ConversationScrollFixture() {
  const [messages, setMessages] = useState<FixtureMessage[]>(initialMessages);
  const [asyncMediaHeight, setAsyncMediaHeight] = useState(24);
  const [mediaRevision, setMediaRevision] = useState(0);
  const [phase, setPhase] = useState("ready");
  const [shrinkHeight, setShrinkHeight] = useState(0);
  const [prependCount, setPrependCount] = useState(0);
  const [appendCount, setAppendCount] = useState(0);
  const [highlightedMessageId, setHighlightedMessageId] = useState<string | null>(null);
  const [highlightedMessageRequestId, setHighlightedMessageRequestId] = useState(0);
  const conversationStageRef = useRef<HTMLDivElement>(null);
  const conversationSurfaceRef = useRef<HTMLDivElement>(null);
  const messageListRef = useRef<HTMLDivElement>(null);
  const composerRef = useRef<HTMLFormElement>(null);
  const composerTextareaRef = useRef<HTMLTextAreaElement>(null);
  const mediaRef = useRef<HTMLImageElement>(null);
  const messageRefs = useRef(new Map<string, HTMLElement>());
  const mutationSequenceRef = useRef(0);

  const clearAnnotationSelection = useCallback(() => undefined, []);
  const layout = useConversationLayout({
    activeScenario: "home",
    activeStreamTurnId: phase.startsWith("second-round") ? "fixture-active-turn" : null,
    annotatedContexts: [],
    composerError: "",
    composerRef,
    composerText: "",
    composerTextareaRef,
    conversationEnabled: true,
    conversationSessionId: SESSION_ID,
    conversationStageRef,
    conversationSurfaceRef,
    highlightedMessageId,
    highlightedMessageRequestId,
    messageListRef,
    messageRefs,
    onClearAnnotationSelection: clearAnnotationSelection,
    route: "/chat/browser-scroll-fixture",
    uploadedResourcesLength: 0,
    uploadingResourcesLength: 0
  });

  useEffect(() => {
    if (!mediaRevision) {
      return;
    }
    const frame = window.requestAnimationFrame(() => {
      mediaRef.current?.dispatchEvent(new Event("load"));
    });
    return () => window.cancelAnimationFrame(frame);
  }, [mediaRevision]);

  const beginSecondRound = () => {
    layout.forceLatest("fixture-second-round");
    setPhase("second-round-shrinking");
    setMessages(current => current.slice(0, 8));
    window.requestAnimationFrame(() => {
      setShrinkHeight(conversationSurfaceRef.current?.scrollHeight ?? 0);
      window.requestAnimationFrame(() => {
        setMessages(current => [
          ...current,
          ...Array.from({ length: 14 }, (_, index) =>
            makeMessage(100 + index, 148 + (index % 3) * 24))
        ]);
        setPhase("second-round-grown");
      });
    });
  };

  const growAsyncMedia = () => {
    mutationSequenceRef.current += 1;
    layout.prepareMutation(`fixture-media:${mutationSequenceRef.current}`);
    setAsyncMediaHeight(360);
    setMediaRevision(current => current + 1);
    setPhase("async-media-grown");
  };

  const prependMessage = () => {
    mutationSequenceRef.current += 1;
    layout.prepareMutation(`fixture-prepend:${mutationSequenceRef.current}`);
    const nextCount = prependCount + 1;
    setPrependCount(nextCount);
    setMessages(current => [
      {
        ...makeMessage(-nextCount, 220),
        content: `在当前阅读位置上方新增的第 ${nextCount} 条消息`,
        label: `上方新增 ${nextCount}`,
        message_id: `fixture-prepended-${nextCount}`,
        record_id: `fixture-prepended-record-${nextCount}`,
        turn_id: `fixture-prepended-turn-${nextCount}`
      },
      ...current
    ]);
  };

  const appendMessage = () => {
    mutationSequenceRef.current += 1;
    layout.prepareMutation(`fixture-append:${mutationSequenceRef.current}`);
    const nextCount = appendCount + 1;
    setAppendCount(nextCount);
    setMessages(current => [
      ...current,
      {
        ...makeMessage(200 + nextCount, 180),
        content: `来源定位后追加的第 ${nextCount} 条消息`,
        label: `尾部追加 ${nextCount}`,
        message_id: `fixture-appended-${nextCount}`,
        record_id: `fixture-appended-record-${nextCount}`,
        turn_id: `fixture-appended-turn-${nextCount}`
      }
    ]);
  };

  const locateSource = () => {
    setHighlightedMessageId(SOURCE_MESSAGE_ID);
    setHighlightedMessageRequestId(current => current + 1);
  };

  const loadLongConversation = () => {
    layout.forceLatest("fixture-long-conversation");
    setHighlightedMessageId(null);
    setMessages(Array.from({ length: 1000 }, (_, index) => ({
      ...makeMessage(index + 1, 72 + (index % 3) * 8),
      turn_id: `fixture-long-turn-${index + 1}`
    })));
    setPhase("long-conversation");
  };

  const locateLongSource = () => {
    setHighlightedMessageId(LONG_SOURCE_MESSAGE_ID);
    setHighlightedMessageRequestId(current => current + 1);
  };

  return (
    <main
      className="conversation-scroll-fixture"
      data-append-count={appendCount}
      data-at-tail={layout.atTail ? "true" : "false"}
      data-follow-intent={layout.followIntent}
      data-media-height={asyncMediaHeight}
      data-message-count={messages.length}
      data-operation={layout.operation}
      data-phase={phase}
      data-prepend-count={prependCount}
      data-shrink-height={shrinkHeight}
      data-testid="conversation-scroll-fixture"
    >
      <div aria-label="夹具操作" className="fixture-scroll-actions">
        <button onClick={beginSecondRound} type="button">开始第二轮</button>
        <button onClick={growAsyncMedia} type="button">异步内容增长</button>
        <button onClick={prependMessage} type="button">在上方增加内容</button>
        <button onClick={locateSource} type="button">定位来源</button>
        <button onClick={appendMessage} type="button">保持来源请求并追加消息</button>
        <button onClick={loadLongConversation} type="button">加载1000轮</button>
        <button onClick={locateLongSource} type="button">定位长对话来源</button>
        <button onClick={() => layout.forceLatest("fixture-force-latest")} type="button">
          强制跟随
        </button>
      </div>

      <output
        aria-label="生产滚动控制器状态"
        className="fixture-controller-state"
      >
        {`${layout.followIntent}:${layout.operation}:${layout.atTail}`}
      </output>

      <div className="home-workspace-content fixture-conversation-stage" ref={conversationStageRef}>
        <div
          aria-label="当前聊天内容"
          className="conversation-surface"
          ref={conversationSurfaceRef}
          role="region"
          tabIndex={0}
        >
          <div className="message-list" ref={messageListRef}>
            <div className="conversation-message-flow">
              {messages.map(message => (
                <FixtureMessageRow
                  asyncMediaHeight={asyncMediaHeight}
                  key={message.message_id}
                  mediaRef={mediaRef}
                  message={message}
                  registerMessageElement={layout.registerMessageElement}
                />
              ))}
            </div>
            <div aria-hidden="true" className="conversation-tail-anchor" />
            <div aria-hidden="true" className="conversation-tail-sentinel" />
          </div>
        </div>

        <form
          className="conversation-composer fixture-composer"
          onSubmit={event => event.preventDefault()}
          ref={composerRef}
        >
          <div className="assistant-composer conversation-composer-surface fixture-composer-surface">
            <div className="conversation-composer-main-row fixture-composer-main-row">
              <div className="composer-input-frame" data-input-area>
                <textarea aria-label="夹具输入框" readOnly ref={composerTextareaRef} rows={2} value="" />
              </div>
              <div className="composer-footer fixture-composer-footer">
                <button aria-label="夹具发送" type="submit">↑</button>
              </div>
            </div>
          </div>
        </form>

        {layout.conversationTailButtonVisible ? (
          <button
            aria-label="回到聊天最新内容并恢复自动跟随"
            className="conversation-tail-button"
            onClick={layout.returnToLatest}
            type="button"
          >
            <span>回到最新</span>
          </button>
        ) : null}
      </div>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ConversationScrollFixture />
  </StrictMode>
);
