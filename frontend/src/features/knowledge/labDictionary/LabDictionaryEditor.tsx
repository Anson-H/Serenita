import { createPortal } from "react-dom";
import { GroupedList } from "../../../components/GroupedList";
import { ListChecksIcon, TrashIcon } from "../../../components/icons";
import { LabDictionaryDetail } from './LabDictionaryDetail';
import { DictionaryCreateDialog, DictionaryMergeConfirmation } from "./LabDictionaryDialogs";
import type { LabDictionaryDetailPage } from "./labDictionaryDrafts";
import { LabDictionaryList } from './LabDictionaryList';
import type { LabCatalog } from "../knowledgeTypes";

import { useLabDictionarySession } from "./useLabDictionarySession";
export function LabDictionaryEditor({
  catalog,
  detailPage,
  detailOpen,
  onChangeCatalog,
  onCloseDetail,
  onDetailTitleChange,
  onNavigate,
  onOpenDetail,
  onReportsChanged
}: {
  catalog: LabCatalog;
  detailPage: LabDictionaryDetailPage;
  detailOpen: boolean;
  onChangeCatalog: (catalog: LabCatalog) => void;
  onCloseDetail: () => void;
  onDetailTitleChange: (title: string) => void;
  onNavigate: (page: LabDictionaryDetailPage) => void;
  onOpenDetail: () => void;
  onReportsChanged: () => void;
}) {
  const { selectionMode, catalogTitle, batchBusy, saving, selectedEntryIds, requestDelete, setQuery, tab, query, categoryFilterOptions, setCategoryFilter, selectedCategoryFilters, loading, cancelSelection, listRef, sortedFilteredItems, filteredCategories, setSelectedEntryIds, startCreate, listMenu, selectedId, activateEntry, visibleEntityCount, listEmptyMessage, contextEntry, contextEntryName, beginSelection, goBackFromDetail, detailTitle, dictionary, activeItem, flushScheduledItemSave, scheduleItemDraft, itemForm, primaryCategorySummary, relatedCategorySummary, activeCategory, flushScheduledCategorySave, scheduleCategoryDraft, categoryForm, activeCategoryItems, selectEntity, createDialog, setCreateDialog, createEntry, confirmation, cancelConfirmation } = useLabDictionarySession({ catalog, detailPage, detailOpen, onChangeCatalog, onCloseDetail, onDetailTitleChange, onNavigate, onOpenDetail, onReportsChanged });
  return (
    <>
      <LabDictionaryList
        selectionMode={selectionMode}
        catalogTitle={catalogTitle}
        batchBusy={batchBusy}
        saving={saving}
        selectedEntryIds={selectedEntryIds}
        requestDelete={requestDelete}
        setQuery={setQuery}
        tab={tab}
        query={query}
        categoryFilterOptions={categoryFilterOptions}
        setCategoryFilter={setCategoryFilter}
        selectedCategoryFilters={selectedCategoryFilters}
        loading={loading}
        cancelSelection={cancelSelection}
        listRef={listRef}
        sortedFilteredItems={sortedFilteredItems}
        filteredCategories={filteredCategories}
        setSelectedEntryIds={setSelectedEntryIds}
        startCreate={startCreate}
        listMenu={listMenu}
        detailOpen={detailOpen}
        selectedId={selectedId}
        activateEntry={activateEntry}
        visibleEntityCount={visibleEntityCount}
        listEmptyMessage={listEmptyMessage}
      />

      {listMenu.contextMenu && contextEntry ? createPortal(
        <GroupedList
          aria-label={`${contextEntryName} 的目录操作`}
          className="context-action-menu scroll-balanced"
          onKeyDown={listMenu.onMenuKeyDown}
          ref={listMenu.menuRef}
          role="menu"
          style={{ left: listMenu.contextMenu.x, top: listMenu.contextMenu.y }}
          density="standard"
        >
          <button onClick={() => beginSelection(listMenu.contextMenu!.id)} role="menuitem" type="button">
            <ListChecksIcon className="context-action-menu-icon" /><span>多选</span>
          </button>
          <button className="control control--secondary control--danger context-action-menu-removal removal-action-control" onClick={() => void requestDelete([listMenu.contextMenu!.id])} role="menuitem" type="button">
            <TrashIcon className="context-action-menu-icon" /><span>删除</span>
          </button>
        </GroupedList>, document.body
      ) : null}

      <LabDictionaryDetail
        detailOpen={detailOpen}
        goBackFromDetail={goBackFromDetail}
        detailTitle={detailTitle}
        dictionary={dictionary}
        tab={tab}
        activeItem={activeItem}
        detailPage={detailPage}
        saving={saving}
        flushScheduledItemSave={flushScheduledItemSave}
        scheduleItemDraft={scheduleItemDraft}
        itemForm={itemForm}
        selectedId={selectedId}
        primaryCategorySummary={primaryCategorySummary}
        onNavigate={onNavigate}
        relatedCategorySummary={relatedCategorySummary}
        requestDelete={requestDelete}
        activeCategory={activeCategory}
        flushScheduledCategorySave={flushScheduledCategorySave}
        scheduleCategoryDraft={scheduleCategoryDraft}
        categoryForm={categoryForm}
        activeCategoryItems={activeCategoryItems}
        selectEntity={selectEntity}
      />
      {createDialog && dictionary ? (
        <DictionaryCreateDialog
          categories={dictionary.categories}
          dialog={createDialog}
          onCancel={() => setCreateDialog(null)}
          onChange={setCreateDialog}
          onSubmit={createEntry}
          saving={saving}
        />
      ) : null}
      {confirmation ? <DictionaryMergeConfirmation confirmation={confirmation} onCancel={cancelConfirmation} saving={saving} /> : null}
    </>
  );
}
