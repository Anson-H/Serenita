import { type ReactNode, type RefObject } from "react";

import { Favorite } from "../../api/client";
import { EditIcon, PlusIcon, SidebarBackIcon } from "../../components/icons";
import { MarkdownContent } from "../../components/MarkdownContent";

type FavoriteTagCapsulesProps = {
  adding: boolean;
  containerRef?: (node: HTMLDivElement | null) => void;
  draft: string;
  editing: boolean;
  favoriteId: string;
  onCommitAdd: () => void;
  onDraftChange: (value: string) => void;
  onRemoveTag: (tag: string) => void;
  onStartAdd: () => void;
  onToggleEdit: () => void;
  tags: string[];
  title: string;
};

export type FavoritesWorkspaceProps = {
  addingFavoriteTagId: string | null;
  beginBatchTagEditing: () => void;
  beginFavoriteTagAdd: (favoriteId: string, surface: "list" | "detail") => void;
  batchDeleteFavorites: () => Promise<void>;
  closeFavoriteDetail: () => void;
  commitFavoriteTagDraft: () => void;
  editingFavoriteDetailTagId: string | null;
  editingFavoriteTagIds: string[];
  favoriteDetail: Favorite | null;
  favoriteDetailAutoSaveRef: RefObject<HTMLDivElement | null>;
  favoriteListPanelRef: RefObject<HTMLElement | null>;
  favoriteListRef: RefObject<HTMLDivElement | null>;
  favorites: Favorite[];
  favoriteSelectionMode: boolean;
  favoriteTagInput: string;
  onOpenConversation: (sessionId: string, sourceMessageId: string) => void;
  removeFavoriteTag: (favoriteId: string, tagToRemove: string) => void;
  selectedFavoriteIds: string[];
  setFavoriteTagInput: (value: string) => void;
  setSelectedFavoriteIds: (favoriteIds: string[]) => void;
  showFavorite: (favoriteId: string) => Promise<void>;
  sidebarToggle: ReactNode;
  toggleFavoriteSelection: (favoriteId: string) => void;
  toggleFavoriteSelectionMode: () => void;
  toggleFavoriteTagEditor: (favoriteId: string, surface: "list" | "detail") => void;
};

function renderMarkdownContent(content: string) {
  return <MarkdownContent content={content} />;
}

function formatDateTime(value: string) {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(date);
}

function formatFavoriteSourceType(sourceType: string) {
  return sourceType === "message" ? "AI 回答" : sourceType;
}

function FavoriteTagCapsules({
  adding,
  containerRef,
  draft,
  editing,
  favoriteId,
  onCommitAdd,
  onDraftChange,
  onRemoveTag,
  onStartAdd,
  onToggleEdit,
  tags,
  title
}: FavoriteTagCapsulesProps) {
  return (
    <div
      className="favorite-tag-capsules"
      data-editing={editing ? "true" : undefined}
      data-favorite-id={favoriteId}
      onClick={(event) => event.stopPropagation()}
      ref={containerRef}
    >
      {tags.length ? (
        tags.map((tag) => (
          <span className="favorite-tag-pill" key={`${favoriteId}-${tag}`}>
            <span>{tag}</span>
            {editing ? (
              <button
                aria-label={`删除标签：${tag}`}
                className="favorite-tag-remove-button"
                onClick={() => onRemoveTag(tag)}
                title="删除标签"
                type="button"
              >
                ×
              </button>
            ) : null}
          </span>
        ))
      ) : (
        <span className="favorite-tag-pill favorite-tag-pill-empty">未设置标签</span>
      )}
      {editing && adding ? (
        <form
          className="favorite-tag-add-form"
          onSubmit={(event) => {
            event.preventDefault();
            onCommitAdd();
          }}
        >
          <input
            aria-label={`新增标签：${title}`}
            autoFocus
            onChange={(event) => onDraftChange(event.target.value)}
            placeholder="新标签"
            value={draft}
          />
        </form>
      ) : null}
      {editing ? (
        <button
          aria-label={`新增标签：${title}`}
          className="favorite-tag-add-button"
          onClick={onStartAdd}
          title="新增标签"
          type="button"
        >
          <PlusIcon />
        </button>
      ) : null}
      <button
        aria-label={`编辑标签：${title}`}
        className="favorite-tag-edit-button"
        data-active={editing ? "true" : undefined}
        onClick={onToggleEdit}
        title={editing ? "完成编辑" : "编辑标签"}
        type="button"
      >
        <EditIcon />
      </button>
    </div>
  );
}

export function FavoritesWorkspace({
  addingFavoriteTagId,
  beginBatchTagEditing,
  beginFavoriteTagAdd,
  batchDeleteFavorites,
  closeFavoriteDetail,
  commitFavoriteTagDraft,
  editingFavoriteDetailTagId,
  editingFavoriteTagIds,
  favoriteDetail,
  favoriteDetailAutoSaveRef,
  favoriteListPanelRef,
  favoriteListRef,
  favorites,
  favoriteSelectionMode,
  favoriteTagInput,
  onOpenConversation,
  removeFavoriteTag,
  selectedFavoriteIds,
  setFavoriteTagInput,
  setSelectedFavoriteIds,
  showFavorite,
  sidebarToggle,
  toggleFavoriteSelection,
  toggleFavoriteSelectionMode,
  toggleFavoriteTagEditor
}: FavoritesWorkspaceProps) {
  const selectedCount = selectedFavoriteIds.length;
  const allFavoritesSelected = favorites.length > 0 && selectedCount === favorites.length;
  const favoriteBulkActions = favoriteSelectionMode ? (
    <div className="favorite-bulk-actions" aria-label="批量操作">
      <button
        aria-label={allFavoritesSelected ? "取消全选收藏" : "全选收藏"}
        className="secondary-button favorite-bulk-button"
        onClick={() =>
          setSelectedFavoriteIds(
            allFavoritesSelected ? [] : favorites.map((favorite) => favorite.favorite_id)
          )
        }
        type="button"
      >
        {allFavoritesSelected ? "取消全选" : "全选"}
      </button>
      <button
        aria-label="批量设置标签"
        className="secondary-button favorite-bulk-button"
        disabled={!selectedCount}
        onClick={beginBatchTagEditing}
        type="button"
      >
        设置标签
      </button>
      <button
        aria-label="删除选中的收藏"
        className="secondary-button favorite-bulk-button danger"
        disabled={!selectedCount}
        onClick={() => void batchDeleteFavorites()}
        type="button"
      >
        删除
      </button>
    </div>
  ) : null;
  const favoriteToolbar = (
    <div className="favorite-toolbar" data-selection-mode={favoriteSelectionMode ? "true" : undefined}>
      <div className="favorite-toolbar-leading">
        {sidebarToggle}
      </div>
      <strong className="favorite-toolbar-title">
        {favoriteSelectionMode ? `已选择 ${selectedCount} 条` : "收藏"}
      </strong>
      <div className="favorite-toolbar-controls">
        {favoriteSelectionMode ? (
          <button
            className="favorite-selection-cancel-button"
            onClick={toggleFavoriteSelectionMode}
            type="button"
          >
            取消
          </button>
        ) : null}
        {favorites.length > 0 && !favoriteSelectionMode ? (
          <button
            aria-label="多选收藏"
            className="favorite-multi-select-button"
            onClick={toggleFavoriteSelectionMode}
            title="多选收藏"
            type="button"
          >
            <span className="favorite-multi-select-icon" aria-hidden="true">
              <span />
              <span />
              <span />
            </span>
          </button>
        ) : null}
      </div>
    </div>
  );

  return (
    <section className="workspace-panel favorites-workspace" data-detail-open={favoriteDetail ? "true" : undefined}>
      <div className="favorites-workspace-header">
        {favoriteToolbar}
      </div>
      <div className="favorites-workspace-content">
        {favorites.length ? (
          <div className="favorite-layout">
            <section className="favorite-list-panel" aria-label="收藏" ref={favoriteListPanelRef}>
              <div className="favorite-list" ref={favoriteListRef}>
                {favorites.map((favorite) => {
                  const selectedForDetail = favoriteDetail?.favorite_id === favorite.favorite_id;
                  const selectedForBatch = selectedFavoriteIds.includes(favorite.favorite_id);
                  const editingTags = editingFavoriteTagIds.includes(favorite.favorite_id);
                  const cardClassName = [
                    "favorite-card",
                    selectedForDetail ? "selected" : "",
                    selectedForBatch ? "batch-selected" : ""
                  ]
                    .filter(Boolean)
                    .join(" ");
                  const rowClassName = [
                    "favorite-selection-row",
                    favoriteSelectionMode ? "selection-active" : "",
                    selectedForBatch ? "batch-selected" : ""
                  ]
                    .filter(Boolean)
                    .join(" ");

                  return (
                    <div className={rowClassName} key={favorite.favorite_id}>
                      {favoriteSelectionMode ? (
                        <label
                          className="favorite-card-check-frame"
                          onClick={(event) => event.stopPropagation()}
                          title={selectedForBatch ? "取消选择" : "选择收藏"}
                        >
                          <input
                            aria-label={`选择收藏：${favorite.title}`}
                            checked={selectedForBatch}
                            className="favorite-card-check"
                            onChange={() => toggleFavoriteSelection(favorite.favorite_id)}
                            type="checkbox"
                          />
                          <span className="favorite-card-check-mark" aria-hidden="true" />
                        </label>
                      ) : null}
                      <article
                        className={cardClassName}
                        aria-label={favoriteSelectionMode ? `选择收藏：${favorite.title}` : `查看收藏：${favorite.title}`}
                        onClick={() =>
                          favoriteSelectionMode
                            ? toggleFavoriteSelection(favorite.favorite_id)
                            : void showFavorite(favorite.favorite_id)
                        }
                        onKeyDown={(event) => {
                          if (event.target !== event.currentTarget) {
                            return;
                          }
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            if (favoriteSelectionMode) {
                              toggleFavoriteSelection(favorite.favorite_id);
                            } else {
                              void showFavorite(favorite.favorite_id);
                            }
                          }
                        }}
                        role="button"
                        tabIndex={0}
                      >
                        <div className="favorite-card-top" data-selection-mode={favoriteSelectionMode ? "true" : undefined}>
                          <span className="favorite-card-title">{favorite.title}</span>
                        </div>
                        <div className="favorite-summary">
                          {renderMarkdownContent(favorite.content_summary)}
                        </div>
                        <div className="favorite-card-meta-row">
                          <span>{formatFavoriteSourceType(favorite.source_type)}</span>
                          <span>{formatDateTime(favorite.created_at)}</span>
                        </div>
                        <div className="favorite-card-tag-row">
                          <FavoriteTagCapsules
                            adding={addingFavoriteTagId === favorite.favorite_id}
                            draft={addingFavoriteTagId === favorite.favorite_id ? favoriteTagInput : ""}
                            editing={editingTags}
                            favoriteId={favorite.favorite_id}
                            onCommitAdd={commitFavoriteTagDraft}
                            onDraftChange={setFavoriteTagInput}
                            onRemoveTag={(tag) => removeFavoriteTag(favorite.favorite_id, tag)}
                            onStartAdd={() => beginFavoriteTagAdd(favorite.favorite_id, "list")}
                            onToggleEdit={() => toggleFavoriteTagEditor(favorite.favorite_id, "list")}
                            tags={favorite.tags}
                            title={favorite.title}
                          />
                        </div>
                      </article>
                    </div>
                  );
                })}
                <p className="favorite-list-count">{`共 ${favorites.length} 条`}</p>
              </div>
              {favoriteBulkActions}
            </section>
            {favoriteDetail ? (
              <aside className="favorite-detail" aria-label="收藏详情">
                <div className="favorite-detail-header">
                  <button
                    aria-label="返回收藏列表"
                    className="favorite-detail-back-button"
                    onClick={closeFavoriteDetail}
                    type="button"
                  >
                    <SidebarBackIcon />
                  </button>
                  <h2>{favoriteDetail.title}</h2>
                  <div className="favorite-detail-meta-row">
                    <span>{formatFavoriteSourceType(favoriteDetail.source_type)}</span>
                    <span>{formatDateTime(favoriteDetail.created_at)}</span>
                  </div>
                  <div className="favorite-detail-tag-row">
                    <FavoriteTagCapsules
                      adding={addingFavoriteTagId === favoriteDetail.favorite_id}
                      containerRef={(node) => {
                        favoriteDetailAutoSaveRef.current = node;
                      }}
                      draft={addingFavoriteTagId === favoriteDetail.favorite_id ? favoriteTagInput : ""}
                      editing={editingFavoriteDetailTagId === favoriteDetail.favorite_id}
                      favoriteId={favoriteDetail.favorite_id}
                      onCommitAdd={commitFavoriteTagDraft}
                      onDraftChange={setFavoriteTagInput}
                      onRemoveTag={(tag) => removeFavoriteTag(favoriteDetail.favorite_id, tag)}
                      onStartAdd={() => beginFavoriteTagAdd(favoriteDetail.favorite_id, "detail")}
                      onToggleEdit={() => toggleFavoriteTagEditor(favoriteDetail.favorite_id, "detail")}
                      tags={favoriteDetail.tags}
                      title={favoriteDetail.title}
                    />
                  </div>
                </div>
                <div className="favorite-detail-body">
                  {renderMarkdownContent(favoriteDetail.content_snapshot ?? favoriteDetail.content_summary)}
                </div>
                {favoriteDetail.source_available ? null : (
                  <p className="favorite-source-note">原会话已不可用，当前仍保留收藏时的完整快照。</p>
                )}
                <div className="favorite-detail-actions">
                  {favoriteDetail.source_available ? (
                    <button
                      className="secondary-button"
                      onClick={() => onOpenConversation(favoriteDetail.source_session_id, favoriteDetail.source_id)}
                      type="button"
                    >
                      返回原对话
                    </button>
                  ) : null}
                </div>
              </aside>
            ) : (
              <aside className="favorite-detail favorite-detail-empty" aria-label="收藏详情预览">
                <span>详情预览</span>
                <h2>选择一条收藏查看完整快照</h2>
                <p>列表展示摘要，详情区会保留收藏时的 Markdown 内容，并允许你补充标签。</p>
              </aside>
            )}
          </div>
        ) : (
          <div className="favorite-empty-shell">
            <div className="empty-state favorite-empty-state">
              <strong>还没有收藏，遇到重要回答可以先收藏起来。</strong>
              <p>收藏有价值的回答后，会在这里看到快照。</p>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
