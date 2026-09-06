import { type ReactNode, type RefObject } from "react";

import { ArrowDownIcon, QuoteIcon } from "../../components/icons";
import { WorkspaceToolbar } from "../../components/WorkspaceToolbar";
import {
  type AnnotationSelection
} from "./workspaceTypes";

type HomeWorkspaceProps = {
  composer: ReactNode;
  memberControl?: ReactNode;
  emptyPrompt?: string;
  conversationStageRef: RefObject<HTMLDivElement | null>;
  conversationSurfaceRef: RefObject<HTMLDivElement | null>;
  conversationTailButtonVisible: boolean;
  messageItems: ReactNode;
  messageListRef: RefObject<HTMLDivElement | null>;
  messagesLength: number;
  onAddSelectedTextToConversation: () => void;
  onConversationDisclosureAnchor: (anchor: HTMLElement) => void;
  onReturnToLatest: () => void;
  annotationSelection: AnnotationSelection | null;
  sidebarToggle: ReactNode;
  workspaceTitle: string;
};

export function HomeWorkspace({
  composer,
  memberControl,
  emptyPrompt = "今天想先聊哪件健康小事？",
  conversationStageRef,
  conversationSurfaceRef,
  conversationTailButtonVisible,
  messageItems,
  messageListRef,
  messagesLength,
  onAddSelectedTextToConversation,
  onConversationDisclosureAnchor,
  onReturnToLatest,
  annotationSelection,
  sidebarToggle,
  workspaceTitle
}: HomeWorkspaceProps) {
  return (
    <section className="workspace-panel home-workspace" data-home-empty={messagesLength ? undefined : "true"}>
      <div className="home-workspace-header">
        <WorkspaceToolbar
          className="workspace-titlebar"
          leading={<>{sidebarToggle}<div className="chat-member-control">{memberControl}</div></>}
          showBack={false}
          title={workspaceTitle}
        />
      </div>

      <div className="home-workspace-content" ref={conversationStageRef} onClickCapture={(event) => {
        const target = event.target;
        if (!(target instanceof Element)) {
          return;
        }
        const summary = target.closest("summary");
        const details = summary?.parentElement;
        if (
          summary instanceof HTMLElement &&
          details instanceof HTMLDetailsElement &&
          details.dataset.active !== "true" &&
          summary.getAttribute("aria-disabled") !== "true" &&
          messageListRef.current?.contains(summary)
        ) {
          onConversationDisclosureAnchor(summary);
        }
      }}>
        <div
          aria-label="当前聊天内容"
          className="conversation-surface"
          ref={conversationSurfaceRef}
          role="region"
          tabIndex={0}
        >
          {messagesLength ? (
            <div className="message-list" ref={messageListRef}>
              <div className="conversation-message-flow">
                {messageItems}
              </div>
              <div aria-hidden="true" className="conversation-tail-anchor" />
              <div aria-hidden="true" className="conversation-tail-sentinel" />
            </div>
          ) : (
            <div className="home-empty-center">
              <div className="empty-state">
                <strong>{emptyPrompt}</strong>
              </div>
            </div>
          )}
        </div>

        {composer}

        {messagesLength && conversationTailButtonVisible ? (
          <button
            aria-label="回到聊天最新内容并恢复自动跟随"
            className="conversation-tail-button"
            onClick={onReturnToLatest}
            type="button"
          >
            <ArrowDownIcon />
            <span>回到最新</span>
          </button>
        ) : null}

        {annotationSelection ? (
          <button
            className="selection-annotation-popover"
            onClick={onAddSelectedTextToConversation}
            onMouseDown={(event) => event.preventDefault()}
            style={{ left: annotationSelection.left, top: annotationSelection.top }}
            type="button"
          >
            <QuoteIcon />
            <span>添加到聊天</span>
          </button>
        ) : null}
      </div>
    </section>
  );
}
