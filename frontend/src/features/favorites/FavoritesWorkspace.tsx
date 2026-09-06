import { useEffect, useLayoutEffect, useRef, type ReactNode, type RefObject } from "react";
import { type Favorite, type FavoriteSourceType } from "../../api/client";
import {
  CheckIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  ListChecksIcon,
  TagIcon,
  TrashIcon
} from "../../components/icons";
import { MarkdownContent } from "../../components/MarkdownContent";
import { WorkspaceToolbar } from "../../components/WorkspaceToolbar";
import {
  focusWithoutScroll
} from "../../utils/inputMethod";
import { favoritePreview, favoriteReportContent } from "./favoritePresentation";
import { FavoriteTagCapsules } from "./FavoriteTagCapsules";

type FavoritesWorkspaceProps = {
  addingFavoriteTagId: string | null;
  beginBatchTagEditing: () => void;
  beginFavoriteTagAdd: (favoriteId: string, surface: "list" | "detail") => void;
  batchDeleteFavorites: () => Promise<void>;
  closeFavoriteDetail: () => void;
  commitFavoriteTagDraft: (value?: string) => void;
  editingFavoriteDetailTagId: string | null;
  editingFavoriteTagIds: string[];
  favoriteDetail: Favorite | null;
  favoriteDetailAutoSaveRef: RefObject<HTMLDivElement | null>;
  favorites: Favorite[];
  favoriteSelectionMode: boolean;
  favoriteTagInput: string;
  onOpenConversation: (sessionId: string, sourceMessageId: string) => void;
  onOpenReport: (reportId: string, memberId: string) => void;
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

function formatFavoriteSourceType(sourceType: FavoriteSourceType) {
  return sourceType === "report" ? "报告" : "AI 回答";
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
  favorites,
  favoriteSelectionMode,
  favoriteTagInput,
  onOpenConversation,
  onOpenReport,
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
  const favoriteDetailPanelRef = useRef<HTMLElement | null>(null);
  const favoriteReturnFocusRef = useRef<HTMLElement | null>(null);
  const previousFavoriteDetailIdRef = useRef(favoriteDetail?.favorite_id ?? null);
  const selectedCount = selectedFavoriteIds.length;
  const allFavoritesSelected = favorites.length > 0 && selectedCount === favorites.length;

  useEffect(() => {
    if (favorites.length || !favoriteSelectionMode) return;
    setSelectedFavoriteIds([]);
    toggleFavoriteSelectionMode();
  }, [
    favoriteSelectionMode,
    favorites.length,
    setSelectedFavoriteIds,
    toggleFavoriteSelectionMode
  ]);

  useLayoutEffect(() => {
    const currentFavoriteDetailId = favoriteDetail?.favorite_id ?? null;
    const previousFavoriteDetailId = previousFavoriteDetailIdRef.current;
    previousFavoriteDetailIdRef.current = currentFavoriteDetailId;
    if (
      currentFavoriteDetailId === previousFavoriteDetailId
      || !window.matchMedia("(max-width: 650px)").matches
    ) {
      return;
    }

    const frame = window.requestAnimationFrame(() => {
      if (currentFavoriteDetailId) {
        focusWithoutScroll(favoriteDetailPanelRef.current);
        return;
      }
      if (favoriteReturnFocusRef.current?.isConnected) {
        focusWithoutScroll(favoriteReturnFocusRef.current);
      }
      favoriteReturnFocusRef.current = null;
    });

    return () => window.cancelAnimationFrame(frame);
  }, [favoriteDetail?.favorite_id]);

  const favoriteBulkActions = favoriteSelectionMode ? (
    <div className="favorite-bulk-actions" aria-label="批量操作">
      <button
        aria-label={allFavoritesSelected ? "取消全选收藏" : "全选收藏"}
        className="control control--secondary"
        onClick={() =>
          setSelectedFavoriteIds(
            allFavoritesSelected ? [] : favorites.map((favorite) => favorite.favorite_id)
          )
        }
        type="button"
      >
        <ListChecksIcon />
        <span>{allFavoritesSelected ? "取消全选" : "全选"}</span>
      </button>
      <button
        aria-label="批量设置标签"
        className="control control--secondary"
        disabled={!selectedCount}
        onClick={beginBatchTagEditing}
        type="button"
      >
        <TagIcon />
        <span>设置标签</span>
      </button>
      <button
        aria-label="删除选中的收藏"
        className="control control--secondary control--danger removal-action-control"
        disabled={!selectedCount}
        onClick={() => void batchDeleteFavorites()}
        type="button"
      >
        <TrashIcon />
        <span>删除</span>
      </button>
    </div>
  ) : null;
  const favoriteListToolbarAction = !favorites.length ? null : favoriteSelectionMode ? (
    <button
      className="control control--titlebar control--ghost favorite-selection-cancel-button"
      onClick={toggleFavoriteSelectionMode}
      type="button"
    >
      取消
    </button>
  ) : (
    <button
      aria-label="多选收藏"
      className="control control--titlebar control--icon control--ghost favorite-multi-select-button titlebar-icon-control"
      onClick={toggleFavoriteSelectionMode}
      title="多选收藏"
      type="button"
    >
      <ListChecksIcon />
    </button>
  );
  const detailContent = favoriteDetail ? favoriteReportContent(favoriteDetail) : null;
  const favoriteDetailToolbarTitle = favoriteDetail?.title ?? "收藏详情";

  return (
    <section className="workspace-panel favorites-workspace" data-detail-open={favoriteDetail ? "true" : "false"}>
      <div className="favorite-browser-layout">
        <div className="favorite-library-column">
          <WorkspaceToolbar
            className="favorites-list-toolbar"
            leading={sidebarToggle}
            showBack={false}
            title="全部收藏"
            trailing={favoriteListToolbarAction}
          />
          <section className="favorite-list-panel" aria-label="收藏列表">
            <div className={`favorite-list scroll-content${favorites.length ? "" : " empty"}`}>
              {favorites.length ? favorites.map((favorite) => {
                const selectedForDetail = !favoriteSelectionMode && favoriteDetail?.favorite_id === favorite.favorite_id;
                const selectedForBatch = selectedFavoriteIds.includes(favorite.favorite_id);
                const editingTags = editingFavoriteTagIds.includes(favorite.favorite_id);
                const cardClassName = [
                  "favorite-card",
                  selectedForDetail ? "selected" : ""
                ]
                  .filter(Boolean)
                  .join(" ");
                const rowClassName = [
                  "favorite-selection-row",
                  favoriteSelectionMode ? "selection-active" : ""
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
                        <span
                          aria-hidden="true"
                          className="favorite-card-check-mark selection-check-control"
                          data-selected={selectedForBatch ? "true" : undefined}
                        >
                          {selectedForBatch ? (
                            <CheckIcon className="selection-check-icon" />
                          ) : null}
                        </span>
                      </label>
                    ) : null}
                    <article
                      className={cardClassName}
                      data-current={selectedForDetail ? "true" : undefined}
                      data-row-surface
                      data-selection-mode={favoriteSelectionMode ? "multiple" : undefined}
                      aria-label={favoriteSelectionMode ? `选择收藏：${favorite.title}` : `查看收藏：${favorite.title}`}
                      onClick={(event) => {
                        if (favoriteSelectionMode) {
                          toggleFavoriteSelection(favorite.favorite_id);
                          return;
                        }
                        favoriteReturnFocusRef.current = event.currentTarget;
                        void showFavorite(favorite.favorite_id);
                      }}
                      onKeyDown={(event) => {
                        if (event.target !== event.currentTarget) {
                          return;
                        }
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          if (favoriteSelectionMode) {
                            toggleFavoriteSelection(favorite.favorite_id);
                          } else {
                            favoriteReturnFocusRef.current = event.currentTarget;
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
                      {favoritePreview(favorite) ? (
                        <p className="favorite-summary">{favoritePreview(favorite)}</p>
                      ) : null}
                      <div className="favorite-card-meta-row">
                        <span>{favorite.member_name ?? "未关联成员"} · {formatFavoriteSourceType(favorite.source_type)}</span>
                        <time dateTime={favorite.created_at}>收藏于 {formatDateTime(favorite.created_at)}</time>
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
              }) : (
                <div className="favorite-list-empty workspace-empty-state">
                  <strong>还没有收藏</strong>
                  <p>收藏报告或回答后，会显示在这里。</p>
                </div>
              )}
            </div>
            {favoriteBulkActions}
          </section>
        </div>
        <div className="favorite-detail-column">
          <WorkspaceToolbar
            className="favorites-detail-toolbar"
            onBack={favoriteDetail ? closeFavoriteDetail : undefined}
            title={favoriteDetailToolbarTitle}
          />
          {favoriteDetail ? (
            <aside
              aria-label="收藏详情"
              className="favorite-detail"
              ref={favoriteDetailPanelRef}
              tabIndex={-1}
            >
              <div className="favorite-detail-scroll scroll-content">
                <div className="favorite-detail-meta-row">
                  <span>{favoriteDetail.member_name ?? "未关联成员"} · {formatFavoriteSourceType(favoriteDetail.source_type)}</span>
                  <time dateTime={favoriteDetail.created_at}>收藏于 {formatDateTime(favoriteDetail.created_at)}</time>
                </div>
                <div className="favorite-detail-actions">
                  {favoriteDetail.source_available ? (
                    <button
                      className="control control--compact control--secondary secondary-button"
                      onClick={() => {
                        if (favoriteDetail.source_type === "report") {
                          if (favoriteDetail.member_id) onOpenReport(favoriteDetail.source_id, favoriteDetail.member_id);
                        } else if (favoriteDetail.source_session_id) {
                          onOpenConversation(favoriteDetail.source_session_id, favoriteDetail.source_id);
                        }
                      }}
                      type="button"
                    >
                      {favoriteDetail.source_type === "report" ? <ChevronRightIcon /> : <ChevronLeftIcon />}
                      <span>{favoriteDetail.source_type === "report" ? "查看原报告" : "返回原聊天"}</span>
                    </button>
                  ) : null}
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
                <div className="favorite-detail-body">
                  {detailContent?.fields.length ? (
                    <dl className="favorite-report-fields">
                      {detailContent.fields.map(field => (
                        <div key={field.label}>
                          <dt>{field.label}</dt>
                          <dd>{field.value}</dd>
                        </div>
                      ))}
                    </dl>
                  ) : null}
                  {renderMarkdownContent(detailContent?.content ?? "")}
                </div>
                {favoriteDetail.source_available ? null : (
                  <p className="favorite-source-note">
                    {favoriteDetail.source_type === "report"
                      ? "原报告已不可用，当前仍保留收藏时的完整报告快照。"
                      : "原聊天已不可用，当前仍保留收藏时的完整快照。"}
                  </p>
                )}

              </div>
            </aside>
          ) : (
            <aside className="favorite-detail favorite-detail-empty" aria-label="收藏详情预览">
              <div className="favorite-detail-empty-content workspace-empty-state">
                <h3>选择一条收藏</h3>
                <p>完整快照和标签会显示在这里。</p>
              </div>
            </aside>
          )}
        </div>
      </div>
    </section>
  );
}
