import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
  type RefObject
} from "react";
import { createPortal } from "react-dom";
import { GroupedList } from "../components/GroupedList";
import { SelectAllButton } from "../components/SelectAllButton";
import { useListContextMenu } from "../components/useListContextMenu";

import { AuthSession, ConversationSummary } from "../api/client";
import {
  BranchIcon,
  CheckIcon,
  EditIcon,
  FavoriteNavIcon,
  ListChecksIcon,
  PinIcon,
  PlusIcon,
  SidebarExpandedIcon,
  TrashIcon,
  WaitingIcon,
  XIcon
} from "../components/icons";
import {
  type ScenarioTab
} from "../features/conversations/workspaceTypes";
import {
  APP_PATH,
  CHAT_PATH_PREFIX,
  FAVORITES_PATH,
  SETTING_PATH,
  type RoutePath
} from "./routes";

type SidebarProps = {
  healthNavigation: ReactNode;
  activeScenario: ScenarioTab;
  conversations: ConversationSummary[];
  currentSession: Extract<AuthSession, { authenticated: true }>;
  currentSessionId: string | null;
  mobileCollapseButtonRef?: RefObject<HTMLButtonElement | null>;
  onBatchDeleteConversations: (sessionIds: string[]) => Promise<string[]>;
  onBatchPinConversations: (sessionIds: string[], isPinned: boolean) => Promise<boolean>;
  onCollapseMobileSidebar: () => void;
  onCollapseSidebar: () => void;
  onDeleteConversation: (sessionId: string) => Promise<boolean>;
  onForkConversation: (sessionId: string) => void;
  onNavigate: (path: RoutePath) => void;
  onOpenConversation: (sessionId: string) => void;
  onRenameConversation: (sessionId: string, title: string) => Promise<boolean>;
  onSetConversationPinned: (sessionId: string, isPinned: boolean) => Promise<boolean>;
  onStartConversation: () => void;
  route: RoutePath;
};

export function Sidebar({
  healthNavigation,
  activeScenario,
  conversations,
  currentSession,
  currentSessionId,
  mobileCollapseButtonRef,
  onBatchDeleteConversations,
  onBatchPinConversations,
  onCollapseMobileSidebar,
  onCollapseSidebar,
  onDeleteConversation,
  onForkConversation,
  onNavigate,
  onOpenConversation,
  onRenameConversation,
  onSetConversationPinned,
  onStartConversation,
  route
}: SidebarProps) {
  const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
  const [renameDraft, setRenameDraft] = useState("");
  const [renameSaving, setRenameSaving] = useState(false);
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedSessionIds, setSelectedSessionIds] = useState<Set<string>>(
    () => new Set()
  );
  const [batchBusy, setBatchBusy] = useState(false);
  const renameInputRef = useRef<HTMLInputElement | null>(null);
  const skipRenameBlurRef = useRef(false);

  const { contextMenu, menuRef: contextMenuRef, closeContextMenu, rowProps, onMenuKeyDown } =
    useListContextMenu({ enabled: !selectionMode, scope: route });

  const contextConversation = contextMenu
    ? conversations.find((conversation) => conversation.session_id === contextMenu.id) ?? null
    : null;
  const selectedConversations = useMemo(
    () => conversations.filter((conversation) => selectedSessionIds.has(conversation.session_id)),
    [conversations, selectedSessionIds]
  );
  const selectionAllPinned = selectedConversations.length > 0
    && selectedConversations.every((conversation) => conversation.is_pinned);
  const isConversationRoute = route === APP_PATH || route.startsWith(CHAT_PATH_PREFIX);
  const conversationWorkspaceActive = isConversationRoute
    && activeScenario === "home";

  useEffect(() => {
    setEditingSessionId(null);
    setSelectionMode(false);
    setSelectedSessionIds(new Set());
  }, [route]);

  useEffect(() => {
    const availableIds = new Set(conversations.map((conversation) => conversation.session_id));
    setSelectedSessionIds((current) => {
      const remaining = new Set([...current].filter((sessionId) => availableIds.has(sessionId)));
      if (remaining.size === current.size) {
        return current;
      }
      if (!remaining.size) {
        setSelectionMode(false);
      }
      return remaining;
    });
    if (contextMenu && !availableIds.has(contextMenu.id)) closeContextMenu(false);
  }, [conversations, contextMenu, closeContextMenu]);

  useEffect(() => {
    if (!editingSessionId) {
      return;
    }
    window.requestAnimationFrame(() => {
      renameInputRef.current?.focus();
      renameInputRef.current?.select();
    });
  }, [editingSessionId]);

  function toggleSelectedSession(sessionId: string) {
    setSelectedSessionIds((current) => {
      const next = new Set(current);
      if (next.has(sessionId)) {
        next.delete(sessionId);
      } else {
        next.add(sessionId);
      }
      return next;
    });
  }

  function beginSelection(sessionId: string) {
    closeContextMenu(false);
    setEditingSessionId(null);
    setSelectionMode(true);
    setSelectedSessionIds(new Set([sessionId]));
  }

  function cancelSelection() {
    setSelectionMode(false);
    setSelectedSessionIds(new Set());
  }

  function beginRename(conversation: ConversationSummary) {
    closeContextMenu(false);
    setRenameDraft(conversation.title);
    setEditingSessionId(conversation.session_id);
  }

  async function submitRename() {
    if (!editingSessionId || renameSaving) {
      return;
    }
    if (skipRenameBlurRef.current) {
      skipRenameBlurRef.current = false;
      return;
    }
    const title = renameDraft.trim();
    const conversation = conversations.find((item) => item.session_id === editingSessionId);
    if (!title || title === conversation?.title) {
      setEditingSessionId(null);
      return;
    }
    setRenameSaving(true);
    const saved = await onRenameConversation(editingSessionId, title);
    setRenameSaving(false);
    if (saved) {
      setEditingSessionId(null);
    } else {
      window.requestAnimationFrame(() => renameInputRef.current?.focus());
    }
  }

  async function applyBatchPin(isPinned: boolean) {
    const sessionIds = [...selectedSessionIds];
    if (!sessionIds.length || batchBusy) {
      return;
    }
    setBatchBusy(true);
    const updated = await onBatchPinConversations(sessionIds, isPinned);
    setBatchBusy(false);
    if (updated) {
      cancelSelection();
    }
  }

  async function deleteSelection() {
    const sessionIds = [...selectedSessionIds];
    if (!sessionIds.length || batchBusy) {
      return;
    }
    setBatchBusy(true);
    const failedIds = await onBatchDeleteConversations(sessionIds);
    setBatchBusy(false);
    if (!failedIds.length) {
      cancelSelection();
    } else {
      setSelectedSessionIds(new Set(failedIds));
    }
  }

  const contextMenuPortal = contextMenu && contextConversation && typeof document !== "undefined"
    ? createPortal(
        <GroupedList
          aria-label={`${contextConversation.title} 的聊天操作`}
          className="context-action-menu conversation-context-menu"
          onKeyDown={onMenuKeyDown}
          ref={contextMenuRef}
          role="menu"
          style={{ left: contextMenu.x, top: contextMenu.y }}
        density="standard"
        >
          <button onClick={() => beginSelection(contextConversation.session_id)} role="menuitem" type="button">
            <ListChecksIcon className="context-action-menu-icon" />
            <span>多选</span>
          </button>
          <button
            onClick={() => {
              closeContextMenu();
              void onSetConversationPinned(
                contextConversation.session_id,
                !contextConversation.is_pinned
              );
            }}
            role="menuitem"
            type="button"
          >
            <PinIcon className="context-action-menu-icon" />
            <span>{contextConversation.is_pinned ? "取消置顶" : "置顶"}</span>
          </button>
          <button onClick={() => beginRename(contextConversation)} role="menuitem" type="button">
            <EditIcon className="context-action-menu-icon" />
            <span>重命名</span>
          </button>
          <button
            disabled={!contextConversation.fork_available}
            onClick={() => {
              closeContextMenu(false);
              onForkConversation(contextConversation.session_id);
            }}
            role="menuitem"
            type="button"
          >
            <BranchIcon className="context-action-menu-icon" />
            <span>创建分支</span>
          </button>
          <button
            className="control control--secondary control--danger context-action-menu-removal conversation-context-delete removal-action-control"
            onClick={() => {
              closeContextMenu(false);
              void onDeleteConversation(contextConversation.session_id);
            }}
            role="menuitem"
            type="button"
          >
            <TrashIcon className="context-action-menu-icon" />
            <span>删除</span>
          </button>
        </GroupedList>,
        document.body
      )
    : null;

  return (
    <aside aria-label="主导航" className="patient-sidebar">
      <section className="sidebar-header">
        <div className="brand-row">
          <div className="brand-name"><span>Serenita</span></div>
          <button
            aria-label="折叠侧边栏"
            className="control control--titlebar control--icon control--ghost sidebar-collapse-button titlebar-icon-control"
            onClick={onCollapseSidebar}
            title="折叠侧边栏"
            type="button"
          >
            <SidebarExpandedIcon />
          </button>
          <button
            aria-label="折叠侧边栏"
            className="control control--titlebar control--icon control--ghost mobile-sidebar-collapse-button titlebar-icon-control"
            onClick={onCollapseMobileSidebar}
            ref={mobileCollapseButtonRef}
            title="折叠侧边栏"
            type="button"
          >
            <SidebarExpandedIcon />
          </button>
        </div>
      </section>

      <div className="sidebar-content">
        <nav className="global-nav">
          {healthNavigation}
          {selectionMode ? (
            <div
              aria-live="polite"
              className="list-selection-heading standard-control-bar"
              role="status"
            >
              <strong>已选择 {selectedSessionIds.size} 个聊天</strong>
              <div className="compact-control-actions">
                <SelectAllButton
                  disabled={batchBusy}
                  ids={conversations.map((conversation) => conversation.session_id)}
                  onChange={setSelectedSessionIds}
                  scopeLabel="当前列表中的聊天"
                  selectedIds={selectedSessionIds}
                />
                <button
                  aria-label="退出多选"
                  className="control control--inline control--icon control--ghost conversation-selection-cancel standard-bar-icon-control"
                  disabled={batchBusy}
                  onClick={cancelSelection}
                  title="退出多选"
                  type="button"
                >
                  <XIcon />
                </button>
              </div>
            </div>
          ) : null}
        </nav>

        <div
          className="conversation-list-stage"
          data-selection-mode={selectionMode ? "true" : undefined}
        >
          <section
            className={`conversation-list scroll-content${conversations.length ? "" : " empty"}`}
            aria-label="聊天列表"
          >
            {conversations.length ? conversations.map((conversation) => {
            const selected = selectedSessionIds.has(conversation.session_id);
            const active = !selectionMode && conversationWorkspaceActive
              && conversation.session_id === currentSessionId;
            const frameClassName = [
              "conversation-item-frame",
              active ? "active" : "",
              selectionMode ? "selection-mode" : ""
            ].filter(Boolean).join(" ");
            return (
              <div className="conversation-item-row" key={conversation.session_id}>
                <div
                  className={frameClassName}
                  data-row-surface
                  data-input-surface
                  data-selection-mode={selectionMode ? "multiple" : undefined}
                  data-pinned={conversation.is_pinned ? "true" : "false"}
                  onClick={() => {
                    if (selectionMode) {
                      toggleSelectedSession(conversation.session_id);
                    }
                  }}
                  {...rowProps<HTMLDivElement>(conversation.session_id, ".conversation-title-button")}
                >
                  {selectionMode ? (
                    <button
                      aria-label={`${selected ? "取消选择" : "选择"}聊天：${conversation.title}`}
                      aria-pressed={selected}
                      className="conversation-selection-toggle selection-check-control"
                      data-interaction-owner="row"
                      onClick={(event) => {
                        event.stopPropagation();
                        toggleSelectedSession(conversation.session_id);
                      }}
                      type="button"
                    >
                      {selected ? (
                        <CheckIcon className="conversation-selection-check selection-check-icon" />
                      ) : null}
                    </button>
                  ) : null}
                  {editingSessionId === conversation.session_id ? (
                    <input
                      aria-label={`重命名聊天：${conversation.title}`}
                      className="conversation-rename-input"
                      disabled={renameSaving}
                      maxLength={14}
                      onBlur={() => void submitRename()}
                      onChange={(event) => setRenameDraft(event.target.value)}
                      onClick={(event) => event.stopPropagation()}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") {
                          event.preventDefault();
                          event.currentTarget.blur();
                        } else if (event.key === "Escape") {
                          event.preventDefault();
                          skipRenameBlurRef.current = true;
                          setEditingSessionId(null);
                        }
                      }}
                      ref={renameInputRef}
                      value={renameDraft}
                    />
                  ) : (
                    <button
                      aria-current={active ? "page" : undefined}
                      aria-label={`${conversation.title}${conversation.member_name ? `，${conversation.member_name}` : ""}${conversation.is_pinned ? "，已置顶" : ""}`}
                      className="conversation-title-button"
                      data-interaction-owner="row"
                      data-row-trigger
                      onClick={(event) => {
                        event.stopPropagation();
                        if (selectionMode) {
                          toggleSelectedSession(conversation.session_id);
                        } else {
                          onOpenConversation(conversation.session_id);
                        }
                      }}
                      type="button"
                    >
                      <span>{conversation.title}</span>
                      {conversation.member_name ? (
                        <span className="conversation-member-label" title={conversation.member_name}>
                          {Array.from(conversation.member_name).slice(0, 3).join("")}
                        </span>
                      ) : null}
                    </button>
                  )}
                  {conversation.is_pinned || conversation.pending_turn_status || conversation.queued_input_count ? (
                    <span className="conversation-status-indicators">
                      {conversation.is_pinned ? (
                        <span
                          aria-label="已置顶"
                          className="conversation-pinned-indicator"
                          role="img"
                        >
                          <PinIcon />
                        </span>
                      ) : null}
                      {conversation.pending_turn_status ? (
                        <span
                          aria-label={conversation.pending_turn_status === "queued" ? "聊天正在排队" : "聊天正在执行"}
                          className="conversation-pending-indicator"
                          role="status"
                        >
                          <WaitingIcon />
                        </span>
                      ) : null}
                      {conversation.queued_input_count ? (
                        <span
                          aria-label={`聊天有 ${conversation.queued_input_count} 项等候输入`}
                          className="conversation-pending-indicator"
                          role="status"
                        >
                          {conversation.queued_input_count}
                        </span>
                      ) : null}
                    </span>
                  ) : null}
                </div>
              </div>
            );
            }) : (
              <span className="message-meta empty-list-status conversation-list-empty">暂无历史聊天</span>
            )}
          </section>

          {!selectionMode ? (
            <div className="list-floating-actions conversation-list-floating-actions">
              <button
                aria-label="发起新聊天"
                className="control control--primary primary-action creation-action-button control-primary"
                onClick={onStartConversation}
                title="发起新聊天"
                type="button"
              >
                <PlusIcon />
                <span className="nav-label">发起新聊天</span>
              </button>
            </div>
          ) : null}
        </div>

        {selectionMode ? (
          <section className="conversation-bulk-toolbar" aria-label="批量聊天操作">
            <div className="conversation-bulk-actions">
              <button
                className="control control--secondary"
                disabled={!selectedSessionIds.size || batchBusy}
                onClick={() => void applyBatchPin(!selectionAllPinned)}
                type="button"
              >
                <PinIcon />
                <span>{selectionAllPinned ? "取消置顶" : "置顶"}</span>
              </button>
              <button
                className="control control--secondary control--danger removal-action-control"
                disabled={!selectedSessionIds.size || batchBusy}
                onClick={() => void deleteSelection()}
                type="button"
              >
                <TrashIcon />
                <span>删除</span>
              </button>
            </div>
          </section>
        ) : null}

        <div className="sidebar-bottom">
          <nav className="secondary-nav" aria-label="辅助导航">
            <button
              aria-label="我的收藏"
              className={route === FAVORITES_PATH ? "control control--secondary nav-item control-primary active" : "control control--secondary nav-item control-primary"}
              onClick={() => onNavigate(FAVORITES_PATH)}
              title="我的收藏"
              type="button"
            >
              <FavoriteNavIcon />
              <span className="nav-label">我的收藏</span>
            </button>
          </nav>

          <section className="user-summary" aria-label="当前账号">
            <button
              aria-current={route === SETTING_PATH ? "page" : undefined}
              aria-label={`账号设置：${currentSession.account_name}`}
              className={route === SETTING_PATH ? "sidebar-identity-row account-button active" : "sidebar-identity-row account-button"}
              onClick={() => onNavigate(SETTING_PATH)}
              title={currentSession.account_name}
              type="button"
            >
              <span className="account-avatar" aria-hidden="true">
                {currentSession.account_name.slice(0, 1).toUpperCase()}
              </span>
              <span className="account-copy"><strong>{currentSession.account_name}</strong></span>
            </button>
          </section>
        </div>
      </div>
      {contextMenuPortal}
    </aside>
  );
}
