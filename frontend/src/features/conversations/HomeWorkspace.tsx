import type { ReactNode, RefObject } from "react";

import { QuoteIcon } from "../../components/icons";
import {
  type QuoteSelection
} from "./workspaceTypes";

type HomeWorkspaceProps = {
  branchRestoreDivider: ReactNode;
  composer: ReactNode;
  conversationStageRef: RefObject<HTMLDivElement | null>;
  conversationSurfaceRef: RefObject<HTMLDivElement | null>;
  messageItems: ReactNode;
  messageListRef: RefObject<HTMLDivElement | null>;
  messagesLength: number;
  onAddSelectedTextToConversation: () => void;
  onConversationScroll: () => void;
  quoteSelection: QuoteSelection | null;
  sidebarToggle: ReactNode;
  workspaceTitle: string;
};

export function HealthWorkspacePlaceholder() {
  return (
    <section className="workspace-panel">
      <header className="workspace-header">
        <span>原始文件</span>
        <h1>原始文件暂作为占位入口</h1>
      </header>
      <div className="empty-state">
        <strong>v0.1.0 不录入正式文件</strong>
        <p>后续报告、用药、生活指标会在这里汇总；当前不会误导为已完成能力。</p>
      </div>
    </section>
  );
}

export function HomeWorkspace({
  branchRestoreDivider,
  composer,
  conversationStageRef,
  conversationSurfaceRef,
  messageItems,
  messageListRef,
  messagesLength,
  onAddSelectedTextToConversation,
  onConversationScroll,
  quoteSelection,
  sidebarToggle,
  workspaceTitle
}: HomeWorkspaceProps) {
  return (
    <section className="workspace-panel home-workspace" data-home-empty={messagesLength ? undefined : "true"}>
      <div className="home-workspace-header">
        <header className="workspace-titlebar">
          <div className="workspace-titlebar-side">{sidebarToggle}</div>
          <h1>{workspaceTitle}</h1>
          <span className="workspace-titlebar-side" aria-hidden="true" />
        </header>
      </div>

      <div className="home-workspace-content" ref={conversationStageRef}>
        <div className="conversation-surface" ref={conversationSurfaceRef} onScroll={onConversationScroll}>
          {messagesLength ? (
            <div className="message-list" aria-label="当前对话" ref={messageListRef}>
              {messageItems}
              {branchRestoreDivider}
            </div>
          ) : (
            <div className="home-empty-center">
              <div className="empty-state">
                <strong>今天想先聊哪件健康小事？</strong>
              </div>
              {composer}
            </div>
          )}
        </div>

        {messagesLength ? composer : null}

        {quoteSelection ? (
          <button
            className="selection-quote-popover"
            onClick={onAddSelectedTextToConversation}
            onMouseDown={(event) => event.preventDefault()}
            style={{ left: quoteSelection.left, top: quoteSelection.top }}
            type="button"
          >
            <QuoteIcon />
            <span>添加到对话</span>
          </button>
        ) : null}
      </div>
    </section>
  );
}
