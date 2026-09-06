import type { Dispatch, RefObject, SetStateAction } from "react";
import type { LabDictionaryCategory, LabDictionaryItem } from "../../api/client";
import { GroupedList } from "../../components/GroupedList";
import { CheckIcon, PlusIcon, TrashIcon, XIcon } from "../../components/icons";
import { MultiSelectPopover } from "../../components/MultiSelectPopover";
import { SelectAllButton } from "../../components/SelectAllButton";
import type { useListContextMenu } from "../../components/useListContextMenu";
import {
  SettingsListForwardIcon,
  SettingsListPanel
} from "./SettingsPrimitives";
import type { LabCatalog } from "./settingsTypes";

type Props = {
  selectionMode: boolean;
  catalogTitle: "检验指标目录" | "检验分类目录";
  batchBusy: boolean;
  saving: boolean;
  selectedEntryIds: Set<string>;
  requestDelete: (ids?: string[]) => Promise<void>;
  setQuery: Dispatch<SetStateAction<string>>;
  tab: LabCatalog;
  query: string;
  categoryFilterOptions: { label: string; value: string; }[];
  setCategoryFilter: Dispatch<SetStateAction<string[] | null>>;
  selectedCategoryFilters: string[];
  loading: boolean;
  cancelSelection: () => void;
  listRef: RefObject<HTMLDivElement | null>;
  sortedFilteredItems: LabDictionaryItem[];
  filteredCategories: LabDictionaryCategory[];
  setSelectedEntryIds: Dispatch<SetStateAction<Set<string>>>;
  startCreate: () => void;
  listMenu: ReturnType<typeof useListContextMenu>;
  detailOpen: boolean;
  selectedId: string;
  activateEntry: (id: string) => void;
  visibleEntityCount: number;
  listEmptyMessage: string;
};

export function LabDictionaryList({
  selectionMode,
  catalogTitle,
  batchBusy,
  saving,
  selectedEntryIds,
  requestDelete,
  setQuery,
  tab,
  query,
  categoryFilterOptions,
  setCategoryFilter,
  selectedCategoryFilters,
  loading,
  cancelSelection,
  listRef,
  sortedFilteredItems,
  filteredCategories,
  setSelectedEntryIds,
  startCreate,
  listMenu,
  detailOpen,
  selectedId,
  activateEntry,
  visibleEntityCount,
  listEmptyMessage
}: Props) {
  return (<SettingsListPanel
    bodyClassName="dictionary-list-body"
    className={selectionMode ? "dictionary-list-column has-bulk-actions" : "dictionary-list-column"}
    footer={selectionMode ? (
      <footer aria-label={`${catalogTitle}批量操作`} className="dictionary-bulk-toolbar">
        <button
          className="control control--secondary control--danger removal-action-control"
          disabled={batchBusy || saving || selectedEntryIds.size === 0}
          onClick={() => void requestDelete([...selectedEntryIds])}
          type="button"
        >
          <TrashIcon className="message-action-icon" />
          <span>{batchBusy ? "正在删除…" : "删除"}</span>
        </button>
      </footer>
    ) : undefined}
    title={catalogTitle}
    titleId="dictionary-list-title"
  >
    <div className="dictionary-list-tools">
      <input
        aria-label={`搜索${catalogTitle}`}
        disabled={batchBusy}
        onChange={(event) => setQuery(event.target.value)}
        placeholder={tab === "items" ? "搜索指标名称" : "搜索分类名称"}
        type="search"
        value={query}
      />
      {tab === "items" ? (
        <MultiSelectPopover
          allSelectedLabel="全部分类"
          ariaLabel="按分类筛选"
          className="dictionary-filter-picker multi-select-filter-picker"
          disabled={batchBusy || !categoryFilterOptions.length}
          emptySelectedLabel="未选择分类"
          menuWidth="trigger" menuAlign="start" interactionOwner="self"
          onChange={(values) => {
            setCategoryFilter(
              values.length === categoryFilterOptions.length ? null : values
            );
          }}
          options={categoryFilterOptions}
          selectedCountLabel={(count) => `已选 ${count} 个分类`}
          values={selectedCategoryFilters}
        />
      ) : null}
    </div>
    <div className="dictionary-entity-list" aria-busy={loading || batchBusy ? "true" : "false"} onKeyDown={(event) => {
      if (selectionMode && event.key === "Escape") cancelSelection();
    }} ref={listRef}>
      {loading ? <p className="status-message">正在加载{catalogTitle}...</p> : null}
      {!loading ? (
        <>
          {selectionMode ? (
            <div aria-live="polite" className="list-selection-heading standard-control-bar" role="status">
              <strong>已选择 {selectedEntryIds.size} {tab === "items" ? "条指标" : "个分类"}</strong>
              <div className="compact-control-actions">
                <SelectAllButton
                  disabled={batchBusy || saving}
                  ids={tab === "items"
                    ? sortedFilteredItems.map((item) => item.item_id)
                    : filteredCategories.map((category) => category.category_name)}
                  onChange={setSelectedEntryIds}
                  scopeLabel={`当前筛选结果中的${tab === "items" ? "指标" : "分类"}`}
                  selectedIds={selectedEntryIds}
                />
                <button
                  aria-label={`退出${catalogTitle}多选`}
                  className="control control--inline control--icon control--ghost dictionary-selection-cancel standard-bar-icon-control"
                  disabled={batchBusy}
                  onClick={cancelSelection}
                  title="退出多选"
                  type="button"
                ><XIcon /></button>
              </div>
            </div>
          ) : null}
          <GroupedList className="dictionary-grouped-list" density="standard">
            {!selectionMode ? <button
              className="control control--row dictionary-create-button grouped-list-create-button"
              disabled={batchBusy || saving}
              onClick={startCreate}
              type="button"
            >
              <PlusIcon className="settings-action-icon" />
              <span>新增{tab === "items" ? "指标" : "分类"}</span>
            </button> : null}
            {tab === "items" ? sortedFilteredItems.map((item) => (
              <button
                {...listMenu.rowProps(item.item_id)}
                aria-current={!selectionMode && detailOpen && selectedId === item.item_id ? "page" : undefined}
                aria-checked={selectionMode ? selectedEntryIds.has(item.item_id) : undefined}
                aria-label={selectionMode ? `${selectedEntryIds.has(item.item_id) ? "取消选择" : "选择"}指标：${item.item_name_zh}` : undefined}
                aria-haspopup={!selectionMode ? "menu" : undefined}
                className={`dictionary-entity-row dictionary-item-row${selectionMode ? " selection-mode" : ""}`}
                disabled={batchBusy}
                key={item.item_id}
                onClick={() => activateEntry(item.item_id)}
                role={selectionMode ? "checkbox" : undefined}
                type="button"
              >
                {selectionMode ? <span aria-hidden="true" className="selection-check-control" data-selected={selectedEntryIds.has(item.item_id) ? "true" : undefined}>
                  {selectedEntryIds.has(item.item_id) ? <CheckIcon className="selection-check-icon" /> : null}
                </span> : null}
                <span><strong>{item.item_name_zh}</strong></span>
                <small>{item.primary_category_name} · {item.report_count} 份报告</small>
                {!selectionMode ? <SettingsListForwardIcon className="dictionary-row-chevron" /> : null}
              </button>
            )) : filteredCategories.map((category) => (
              <button
                {...listMenu.rowProps(category.category_name)}
                aria-current={!selectionMode && detailOpen && selectedId === category.category_name ? "page" : undefined}
                aria-checked={selectionMode ? selectedEntryIds.has(category.category_name) : undefined}
                aria-label={selectionMode ? `${selectedEntryIds.has(category.category_name) ? "取消选择" : "选择"}分类：${category.category_name}` : undefined}
                aria-haspopup={!selectionMode ? "menu" : undefined}
                className={`dictionary-entity-row dictionary-category-row${selectionMode ? " selection-mode" : ""}`}
                disabled={batchBusy}
                key={category.category_name}
                onClick={() => activateEntry(category.category_name)}
                role={selectionMode ? "checkbox" : undefined}
                type="button"
              >
                {selectionMode ? <span aria-hidden="true" className="selection-check-control" data-selected={selectedEntryIds.has(category.category_name) ? "true" : undefined}>
                  {selectedEntryIds.has(category.category_name) ? <CheckIcon className="selection-check-icon" /> : null}
                </span> : null}
                <span><strong>{category.category_name}</strong></span>
                <small>{category.item_count} 项指标 · {category.report_count} 份报告</small>
                {!selectionMode ? <SettingsListForwardIcon className="dictionary-row-chevron" /> : null}
              </button>
            ))}
          </GroupedList>
          {visibleEntityCount === 0 ? (
            <p className="dictionary-empty-state workspace-empty-state" role="status">
              {listEmptyMessage}
            </p>
          ) : null}
        </>
      ) : null}
    </div>
    {!loading && visibleEntityCount > 0 ? (
      <p className="object-list-count">
        {tab === "items" ? `共 ${visibleEntityCount} 条指标` : `共 ${visibleEntityCount} 条分类`}
      </p>
    ) : null}
  </SettingsListPanel>);
}
