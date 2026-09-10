import { navigationLabels } from "../../components/navigationLabels";
import {
  useEffect,
  useMemo,
  useRef,
  useState
} from "react";
import { createPortal } from "react-dom";
import {
  apiClient,
  type LabDictionaryMutationResponse,
  type LabDictionaryResponse
} from "../../api/client";
import { labDictionaryMutationAffectsReports } from "../../api/labDictionaryApi";
import { GroupedList } from "../../components/GroupedList";
import { ListChecksIcon, TrashIcon } from "../../components/icons";
import { showStatusNotification, useStatusNotification } from "../../components/StatusNotificationCenter";
import { useListContextMenu } from "../../components/useListContextMenu";
import { catalogDeletionMessage, deleteLabCatalogEntries } from "./labCatalogDeletion";
import { createLabCategoryEditorActions } from './labCategoryEditorActions';
import { LabDictionaryDetail } from './LabDictionaryDetail';
import { DictionaryCreateDialog, DictionaryMergeConfirmation } from "./LabDictionaryDialogs";
import type { CategoryAutoSaveJob, CategoryDraft, CreateDialogState, DictionaryTab, ItemAutoSaveJob, ItemDraft, LabDictionaryDetailPage, PendingMergeConfirmation } from "./labDictionaryDrafts";
import { categoryDraft, itemDraft } from "./labDictionaryDrafts";
import { LabDictionaryList } from './LabDictionaryList';
import { createLabItemEditorActions } from './labItemEditorActions';
import type { LabCatalog } from "./settingsTypes";

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
  const [dictionary, setDictionary] = useState<LabDictionaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<DictionaryTab>(catalog);
  const [query, setQuery] = useState("");
  const [categoryFilter, setCategoryFilter] = useState<string[] | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedEntryIds, setSelectedEntryIds] = useState<Set<string>>(() => new Set());
  const [batchBusy, setBatchBusy] = useState(false);
  const batchBusyRef = useRef(false);
  const catalogRef = useRef(catalog);
  catalogRef.current = catalog;
  const listRef = useRef<HTMLDivElement | null>(null);
  const listMenu = useListContextMenu({
    enabled: !selectionMode && !saving && !batchBusy && !loading && !detailOpen,
    scope: catalog
  });
  const [itemForm, setItemForm] = useState<ItemDraft>(itemDraft());
  const [categoryForm, setCategoryForm] = useState<CategoryDraft>(categoryDraft());
  const [createDialog, setCreateDialog] = useState<CreateDialogState | null>(null);
  const [confirmation, setConfirmation] = useState<PendingMergeConfirmation | null>(null);
  const dictionaryRef = useRef<LabDictionaryResponse | null>(null);
  const selectedIdRef = useRef("");
  const itemFormRef = useRef<ItemDraft>(itemDraft());
  const categoryFormRef = useRef<CategoryDraft>(categoryDraft());
  const selectionEpochRef = useRef(0);
  const itemSaveTimerRef = useRef<number | null>(null);
  const itemSaveQueueRef = useRef<ItemAutoSaveJob[]>([]);
  const itemSaveRunningRef = useRef(false);
  const savedItemTargetsRef = useRef(new Map<string, string>());
  const categorySaveTimerRef = useRef<number | null>(null);
  const categorySaveQueueRef = useRef<CategoryAutoSaveJob[]>([]);
  const categorySaveRunningRef = useRef(false);
  const savedCategoryTargetsRef = useRef(new Map<string, string>());
  const catalogTitle = tab === "items" ? navigationLabels.labItems : navigationLabels.labCategories;

  useStatusNotification(error, {
    id: "lab-dictionary-error",
    title: `${catalogTitle}操作未完成`,
    tone: "error"
  });

  useEffect(() => {
    void loadDictionary();
  }, []);

  useEffect(() => {
    if (catalog !== tab) selectTab(catalog);
  }, [catalog, tab]);

  useEffect(() => {
    setSelectionMode(false);
    setSelectedEntryIds(new Set());
  }, [catalog, detailOpen]);

  useEffect(() => {
    if (!dictionary || batchBusy) return;
    const available = new Set(tab === "items"
      ? dictionary.items.map((item) => item.item_id)
      : dictionary.categories.map((category) => category.category_name));
    setSelectedEntryIds((current) => {
      const remaining = new Set([...current].filter((id) => available.has(id)));
      return remaining.size === current.size ? current : remaining;
    });
  }, [dictionary, tab, batchBusy]);

  useEffect(() => () => {
    if (itemSaveTimerRef.current !== null) window.clearTimeout(itemSaveTimerRef.current);
    if (categorySaveTimerRef.current !== null) window.clearTimeout(categorySaveTimerRef.current);
  }, []);

  async function loadDictionary() {
    setLoading(true);
    setError("");
    try {
      const response = await apiClient.fetchLabDictionary();
      dictionaryRef.current = response;
      setDictionary(response);
      if (tab === "items") {
        const item = response.items.find((candidate) => candidate.item_id === selectedId)
          ?? response.items[0];
        const nextId = item?.item_id ?? "";
        const nextDraft = itemDraft(item);
        selectedIdRef.current = nextId;
        itemFormRef.current = nextDraft;
        setSelectedId(nextId);
        setItemForm(nextDraft);
      } else {
        const category = response.categories.find((candidate) => candidate.category_name === selectedId)
          ?? response.categories[0];
        const nextId = category?.category_name ?? "";
        const nextDraft = categoryDraft(category);
        selectedIdRef.current = nextId;
        categoryFormRef.current = nextDraft;
        setSelectedId(nextId);
        setCategoryForm(nextDraft);
      }
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : `${catalogTitle}加载失败。请重试。`);
    } finally {
      setLoading(false);
    }
  }

  function selectEntity(nextTab: DictionaryTab, id: string, source = dictionary) {
    if (tab === "items") flushScheduledItemSave();
    else flushScheduledCategorySave();
    selectionEpochRef.current += 1;
    setTab(nextTab);
    onNavigate("root");
    if (nextTab !== tab) onChangeCatalog(nextTab);
    selectedIdRef.current = id;
    setSelectedId(id);
    if (nextTab === "items") {
      const nextDraft = itemDraft(source?.items.find((item) => item.item_id === id));
      itemFormRef.current = nextDraft;
      setItemForm(nextDraft);
    } else {
      const nextDraft = categoryDraft(
        source?.categories.find((category) => category.category_name === id)
      );
      categoryFormRef.current = nextDraft;
      setCategoryForm(nextDraft);
    }
    onOpenDetail();
  }

  function selectTab(nextTab: DictionaryTab) {
    if (tab === "items") flushScheduledItemSave();
    else flushScheduledCategorySave();
    selectionEpochRef.current += 1;
    setTab(nextTab);
    onNavigate("root");
    setQuery("");
    setCategoryFilter(null);
    if (nextTab === "items") {
      const item = dictionary?.items[0];
      const nextId = item?.item_id ?? "";
      const nextDraft = itemDraft(item);
      selectedIdRef.current = nextId;
      itemFormRef.current = nextDraft;
      setSelectedId(nextId);
      setItemForm(nextDraft);
    } else {
      const category = dictionary?.categories[0];
      const nextId = category?.category_name ?? "";
      const nextDraft = categoryDraft(category);
      selectedIdRef.current = nextId;
      categoryFormRef.current = nextDraft;
      setSelectedId(nextId);
      setCategoryForm(nextDraft);
    }
  }

  function startCreate() {
    if (tab === "items") flushScheduledItemSave();
    else flushScheduledCategorySave();
    if (tab === "items" && !dictionary?.categories.length) {
      setError("请先创建一个分类，再添加指标。");
      return;
    }
    setError("");
    setCreateDialog({
      kind: tab === "items" ? "item" : "category",
      name: "",
      primaryCategoryName: ""
    });
  }

  function applyMutation(
    response: LabDictionaryMutationResponse,
    targetTab: DictionaryTab = tab
  ) {
    dictionaryRef.current = response.dictionary;
    setDictionary(response.dictionary);
    setTab(targetTab);
    if (targetTab !== tab) onChangeCatalog(targetTab);
    const nextItemId = typeof response.effects.merged_target_item_id === "string"
      ? response.effects.merged_target_item_id
      : typeof response.effects.created_item_id === "string"
        ? response.effects.created_item_id
        : undefined;
    const nextCategoryName = typeof response.effects.created_category_name === "string"
      ? response.effects.created_category_name
      : undefined;
    if (targetTab === "items") {
      const id = nextItemId ?? selectedId;
      const item = response.dictionary.items.find((candidate) => candidate.item_id === id);
      const nextId = item?.item_id ?? response.dictionary.items[0]?.item_id ?? "";
      const nextDraft = itemDraft(item ?? response.dictionary.items[0]);
      selectedIdRef.current = nextId;
      itemFormRef.current = nextDraft;
      setSelectedId(nextId);
      setItemForm(nextDraft);
    } else {
      const id = nextCategoryName ?? categoryForm.category_name ?? selectedId;
      const category = response.dictionary.categories.find((candidate) => candidate.category_name === id);
      const nextCategory = category ?? response.dictionary.categories[0];
      const nextId = nextCategory?.category_name ?? "";
      const nextDraft = categoryDraft(nextCategory);
      selectedIdRef.current = nextId;
      categoryFormRef.current = nextDraft;
      setSelectedId(nextId);
      setCategoryForm(nextDraft);
    }
    setConfirmation(null);
  }

  async function createEntry(submittedName?: string) {
    const currentDictionary = dictionaryRef.current;
    if (!createDialog || !currentDictionary) return;
    const name = (submittedName ?? createDialog.name).trim();
    if (!name || (createDialog.kind === "item" && !createDialog.primaryCategoryName)) return;
    setSaving(true);
    setError("");
    try {
      const targetTab: DictionaryTab = createDialog.kind === "item" ? "items" : "categories";
      const response = createDialog.kind === "item"
        ? await apiClient.createLabDictionaryItem({
          item_name_zh: name,
          aliases: [],
          description: null,
          primary_category_name: createDialog.primaryCategoryName,
          related_category_names: [],
          expected_dictionary_revision: currentDictionary.dictionary_revision
        })
        : await apiClient.createLabDictionaryCategory({
          category_name: name,
          description: null,
          expected_dictionary_revision: currentDictionary.dictionary_revision
        });
      applyMutation(response, targetTab);
      setCreateDialog(null);
      setQuery("");
      setCategoryFilter(null);
      onOpenDetail();
    } catch (createError) {
      const message = createError instanceof Error ? createError.message : "目录创建失败。";
      setError(message);
      if (message.includes("刷新")) {
        const latestDictionary = await apiClient.fetchLabDictionary();
        dictionaryRef.current = latestDictionary;
        setDictionary(latestDictionary);
      }
    } finally {
      setSaving(false);
    }
  }

  async function requestDelete(ids = [selectedIdRef.current]) {
    const currentDictionary = dictionaryRef.current;
    if (!currentDictionary || !ids.length || batchBusyRef.current || saving
      || itemSaveRunningRef.current || categorySaveRunningRef.current) return;
    const targets = new Set(ids);
    if (tab === "items") {
      if (targets.has(selectedIdRef.current) && itemSaveTimerRef.current !== null) {
        window.clearTimeout(itemSaveTimerRef.current);
        itemSaveTimerRef.current = null;
      }
      itemSaveQueueRef.current = itemSaveQueueRef.current.filter(
        (job) => !targets.has(job.targetKey)
      );
    } else {
      if (targets.has(selectedIdRef.current) && categorySaveTimerRef.current !== null) {
        window.clearTimeout(categorySaveTimerRef.current);
        categorySaveTimerRef.current = null;
      }
      categorySaveQueueRef.current = categorySaveQueueRef.current.filter(
        (job) => !targets.has(job.targetKey)
      );
    }
    const operationCatalog = tab;
    const operationEpoch = selectionEpochRef.current;
    const wasSelecting = selectionMode;
    let reportsAffected = false;
    batchBusyRef.current = true;
    setBatchBusy(true);
    setSaving(true);
    setError("");
    listMenu.closeContextMenu(false);
    try {
      const result = await deleteLabCatalogEntries({
        catalog: operationCatalog,
        ids,
        dictionary: currentDictionary,
        client: apiClient,
        onDeleted: (response) => {
          reportsAffected ||= labDictionaryMutationAffectsReports(response.effects);
        }
      });
      dictionaryRef.current = result.dictionary;
      setDictionary(result.dictionary);
      if (catalogRef.current === operationCatalog && selectionEpochRef.current === operationEpoch) {
        const deletedCurrent = result.deletedIds.includes(selectedIdRef.current);
        applyMutation({ dictionary: result.dictionary, effects: {} }, operationCatalog);
        if (deletedCurrent) onCloseDetail();
        if (wasSelecting) {
          const remainingIds = new Set(operationCatalog === "items"
            ? result.dictionary.items.map((item) => item.item_id)
            : result.dictionary.categories.map((category) => category.category_name));
          const failedIds = result.failures.map(({ id }) => id).filter((id) => remainingIds.has(id));
          setSelectedEntryIds(new Set(failedIds));
          setSelectionMode(failedIds.length > 0);
        }
        window.requestAnimationFrame(() => listRef.current?.querySelector<HTMLButtonElement>(
          '.dictionary-entity-row:not(:disabled), .dictionary-create-button:not(:disabled)'
        )?.focus({ preventScroll: true }));
      }
      showStatusNotification({
        id: `lab-catalog-delete-${operationCatalog}`,
        title: `${operationCatalog === "items" ? navigationLabels.labItems : navigationLabels.labCategories}删除结果`,
        message: catalogDeletionMessage(operationCatalog, result.deletedIds.length, result.failures),
        tone: result.failures.some((failure) => !failure.skipped) ? "error"
          : result.failures.length ? "warning" : "success"
      });
    } finally {
      if (reportsAffected) onReportsChanged();
      batchBusyRef.current = false;
      setBatchBusy(false);
      setSaving(false);
    }
  }

  function cancelSelection() {
    if (batchBusyRef.current) return;
    setSelectionMode(false);
    setSelectedEntryIds(new Set());
  }

  function beginSelection(id: string) {
    listMenu.closeContextMenu();
    setSelectionMode(true);
    setSelectedEntryIds(new Set([id]));
  }

  function activateEntry(id: string) {
    if (batchBusyRef.current) return;
    if (!selectionMode) {
      selectEntity(tab, id);
      return;
    }
    setSelectedEntryIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const categoryFilterOptions = useMemo(
    () => (dictionary?.categories ?? []).map((category) => ({
      label: category.category_name,
      value: category.category_name
    })),
    [dictionary?.categories]
  );
  const selectedCategoryFilters = useMemo(() => {
    if (categoryFilter === null) return categoryFilterOptions.map((option) => option.value);
    const availableCategories = new Set(categoryFilterOptions.map((option) => option.value));
    return categoryFilter.filter((categoryName) => availableCategories.has(categoryName));
  }, [categoryFilter, categoryFilterOptions]);
  const selectedCategoryFilterSet = useMemo(
    () => new Set(selectedCategoryFilters),
    [selectedCategoryFilters]
  );

  const filteredItems = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase();
    return (dictionary?.items ?? []).filter((item) => {
      const matchesQuery = !normalizedQuery || [item.item_name_zh, ...item.aliases]
        .some((value) => value.toLocaleLowerCase().includes(normalizedQuery));
      const matchesCategory = selectedCategoryFilterSet.has(item.primary_category_name)
        || item.related_category_names.some((categoryName) => (
          selectedCategoryFilterSet.has(categoryName)
        ));
      return matchesQuery && matchesCategory;
    });
  }, [dictionary?.items, query, selectedCategoryFilterSet]);

  const sortedFilteredItems = useMemo(() => {
    return [...filteredItems].sort((left, right) => (
      left.item_name_zh.localeCompare(right.item_name_zh, "zh-CN")
    ));
  }, [filteredItems]);

  const filteredCategories = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase();
    return (dictionary?.categories ?? []).filter((category) => (
      !normalizedQuery || category.category_name.toLocaleLowerCase().includes(normalizedQuery)
    ));
  }, [dictionary?.categories, query]);
  const visibleEntityCount = tab === "items"
    ? filteredItems.length
    : filteredCategories.length;
  const sourceEntityCount = tab === "items"
    ? dictionary?.items.length ?? 0
    : dictionary?.categories.length ?? 0;
  const listEmptyMessage = sourceEntityCount === 0
    ? `暂无${tab === "items" ? "检验指标" : "检验分类"}`
    : `没有符合条件的${tab === "items" ? "指标" : "分类"}`;
  const contextEntry = listMenu.contextMenu
    ? tab === "items"
      ? sortedFilteredItems.find((item) => item.item_id === listMenu.contextMenu!.id)
      : filteredCategories.find((category) => category.category_name === listMenu.contextMenu!.id)
    : undefined;
  const contextEntryName = contextEntry && "item_name_zh" in contextEntry ? contextEntry.item_name_zh : contextEntry?.category_name;

  const activeItem = tab === "items"
    ? dictionary?.items.find((item) => item.item_id === selectedId)
    : undefined;
  const activeCategory = tab === "categories"
    ? dictionary?.categories.find((category) => category.category_name === selectedId)
    : undefined;
  const activeCategoryItems = activeCategory
    ? (dictionary?.items ?? [])
      .filter((item) => (dictionary?.relations ?? []).some((relation) => (
        relation.category_name === activeCategory.category_name
        && relation.item_id === item.item_id
      )))
      .sort((left, right) => left.item_name_zh.localeCompare(right.item_name_zh, "zh-CN"))
    : [];
  const detailTitle = detailPage === "primary-category"
    ? navigationLabels.primaryCategory
    : detailPage === "related-categories"
      ? navigationLabels.relatedCategories
      : activeItem?.item_name_zh ?? activeCategory?.category_name ?? catalogTitle;
  const primaryCategorySummary = itemForm.primary_category_name || "未设置";
  const relatedCategorySummary = itemForm.related_category_names.length
    ? itemForm.related_category_names.join("、")
    : "未设置";

  useEffect(() => {
    onDetailTitleChange(detailTitle);
  }, [detailTitle, onDetailTitleChange]);

  function goBackFromDetail() {
    if (detailPage !== "root") {
      onNavigate("root");
      return;
    }
    onCloseDetail();
  }
  const { scheduleItemDraft, flushScheduledItemSave, cancelConfirmation } = createLabItemEditorActions({
    savedItemTargetsRef,
    dictionaryRef,
    selectionEpochRef,
    selectedIdRef,
    itemSaveQueueRef,
    itemFormRef,
    setItemForm,
    itemSaveTimerRef,
    setError,
    setConfirmation,
    setSaving,
    setDictionary,
    setSelectedId,
    onReportsChanged,
    loadDictionary,
    confirmation,
    itemSaveRunningRef
  });
  const { scheduleCategoryDraft, flushScheduledCategorySave } = createLabCategoryEditorActions({
    savedCategoryTargetsRef,
    dictionaryRef,
    selectedIdRef,
    selectionEpochRef,
    categorySaveQueueRef,
    categoryFormRef,
    setCategoryForm,
    categorySaveTimerRef,
    categorySaveRunningRef,
    setSaving,
    setError,
    setDictionary,
    setSelectedId,
    onReportsChanged
  });

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
