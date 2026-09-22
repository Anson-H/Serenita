import { isLabDictionaryRevisionConflict } from "./labDictionaryErrors";
import { navigationLabels } from "../../../components/navigationLabels";
import {
  useEffect,
  useMemo,
  useRef,
  useState
} from "react";
import * as labDictionaryApi from "../../../api/knowledge/labDictionaryApi";
import type { LabDictionaryMutationResponse, LabDictionaryResponse } from "../../../api/knowledge/labDictionaryApi";

import { labDictionaryMutationAffectsReports } from "../../../api/knowledge/labDictionaryApi";
import { showStatusNotification, useStatusNotification } from "../../../components/StatusNotificationCenter";
import { useListContextMenu } from "../../../components/useListContextMenu";
import { catalogDeletionMessage, deleteLabCatalogEntries } from "./labCatalogDeletion";
import type { CategoryAutoSaveJob, CategoryDraft, CreateDialogState, DictionaryTab, ItemAutoSaveJob, ItemDraft, LabDictionaryDetailPage, PendingMergeConfirmation } from "./labDictionaryDrafts";
import { categoryDraft, categoryDraftSignature, itemDraft, itemDraftSignature } from "./labDictionaryDrafts";
import type { LabCatalog } from "../knowledgeTypes";
import { registerNavigationSave } from "../../../utils/pendingNavigation";

import { ApiRequestError } from "../../../api/transport/request";
import { LabAutosaveQueue } from "./labAutosaveQueue";
import { itemInput, itemJobCanRebase } from "./labItemEditingPolicy";
import { categoryInput } from "./labCategoryEditingPolicy";
import { cloneItemDraft } from "./labDictionaryDrafts";
export function useLabDictionarySession({
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
  const [mutationSaving, setSaving] = useState(false);
  const [, queueChanged] = useState(0);
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
  const [itemForm, setItemForm] = useState<ItemDraft>(itemDraft());
  const [categoryForm, setCategoryForm] = useState<CategoryDraft>(categoryDraft());
  const [createDialog, setCreateDialog] = useState<CreateDialogState | null>(null);
  const [confirmation, setConfirmation] = useState<PendingMergeConfirmation | null>(null);
  const dictionaryRef = useRef<LabDictionaryResponse | null>(null);
  const selectedIdRef = useRef("");
  const itemFormRef = useRef<ItemDraft>(itemDraft());
  const categoryFormRef = useRef<CategoryDraft>(categoryDraft());
  const selectionEpochRef = useRef(0);
  const navigationWaiters = useRef<Array<(saved: boolean) => void>>([]);
  const navigationSave = useRef<() => Promise<boolean>>(async () => true);
  const saveCommands = useRef({ item: saveItemJob, category: saveCategoryJob });
  saveCommands.current = { item: saveItemJob, category: saveCategoryJob };
  const itemSaves = useRef(new LabAutosaveQueue<ItemAutoSaveJob>(job => saveCommands.current.item(job), () => queueChanged(value => value + 1), error => setError(error instanceof Error ? error.message : "指标自动保存失败。"))).current;
  const categorySaves = useRef(new LabAutosaveQueue<CategoryAutoSaveJob>(job => saveCommands.current.category(job), () => queueChanged(value => value + 1), error => setError(error instanceof Error ? error.message : "分类自动保存失败。"))).current;
  const saving = mutationSaving || itemSaves.running || categorySaves.running;
  const listMenu = useListContextMenu({
    enabled: !selectionMode && !saving && !batchBusy && !loading && !detailOpen,
    scope: catalog
  });
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

  useEffect(() => () => { itemSaves.dispose(); categorySaves.dispose(); }, []);

  async function loadDictionary() {
    setLoading(true);
    setError("");
    try {
      const response = await labDictionaryApi.fetchLabDictionary();
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
        ? await labDictionaryApi.createLabDictionaryItem({
          item_name_zh: name,
          aliases: [],
          description: null,
          primary_category_name: createDialog.primaryCategoryName,
          related_category_names: [],
          expected_dictionary_revision: currentDictionary.dictionary_revision
        })
        : await labDictionaryApi.createLabDictionaryCategory({
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
      if (isLabDictionaryRevisionConflict(createError)) {
        const latestDictionary = await labDictionaryApi.fetchLabDictionary();
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
      || itemSaves.running || categorySaves.running) return;
    const targets = new Set(ids);
    (tab === "items" ? itemSaves : categorySaves).cancelTargets(targets, selectedIdRef.current);
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
        client: labDictionaryApi,
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
  function enqueueItemAutoSave(draft: ItemDraft) {
    if (!draft.item_name_zh.trim() || !draft.primary_category_name || !dictionaryRef.current) {
      return;
    }
    const selectionEpoch = selectionEpochRef.current;
    const targetKey = selectedIdRef.current;
    const baseItem = dictionaryRef.current.items.find(
      (item) => item.item_id === selectedIdRef.current
    );
    if (!targetKey || !baseItem) return;
    const job: ItemAutoSaveJob = {
      draft: cloneItemDraft(draft),
      baseDraftSignature: itemDraftSignature(itemDraft(baseItem)),
      targetKey,
      selectionEpoch
    };
    itemSaves.enqueue(job);
  }

  function scheduleItemDraft(
    update: (current: ItemDraft) => ItemDraft,
    { immediate = false }: { immediate?: boolean } = {}
  ) {
    const nextDraft = update(itemFormRef.current);
    itemFormRef.current = nextDraft;
    setItemForm(nextDraft);
    itemSaves.schedule(nextDraft.item_name_zh.trim() && nextDraft.primary_category_name ? () => enqueueItemAutoSave(itemFormRef.current) : null, immediate);
  }

  function flushScheduledItemSave() { itemSaves.flushScheduled(); }

  async function writeItemAutoSaveJob(
    job: ItemAutoSaveJob,
    currentDictionary: LabDictionaryResponse
  ) {
    const resolvedTarget = itemSaves.resolve(job.targetKey);
    return labDictionaryApi.updateLabDictionaryItem(
      resolvedTarget || job.targetKey,
      itemInput(job.draft, currentDictionary.dictionary_revision)
    );
  }

  function openItemMergeConfirmation(job: ItemAutoSaveJob, targetItemId: string) {
    const sourceItemId = itemSaves.resolve(job.targetKey) || job.targetKey;
    const currentDictionary = dictionaryRef.current;
    const source = currentDictionary?.items.find((item) => item.item_id === sourceItemId);
    const target = currentDictionary?.items.find((item) => item.item_id === targetItemId);
    if (!source || !target || sourceItemId === targetItemId) return false;
    setError("");
    setConfirmation({
      kind: "merge-item",
      sourceItemId,
      targetItemId,
      sourceItemNameZh: source.item_name_zh,
      targetItemNameZh: target.item_name_zh,
      sourceResultCount: source.result_count,
      targetResultCount: target.result_count,
      run: () => mergeConflictingItems(sourceItemId, targetItemId)
    });
    return true;
  }

  async function mergeConflictingItems(sourceItemId: string, targetItemId: string) {
    const currentDictionary = dictionaryRef.current;
    if (!currentDictionary) return;
    setSaving(true);
    setError("");
    try {
      const response = await labDictionaryApi.mergeLabDictionaryItems(
        sourceItemId,
        targetItemId,
        currentDictionary.dictionary_revision
      );
      dictionaryRef.current = response.dictionary;
      setDictionary(response.dictionary);
      itemSaves.remember(sourceItemId, targetItemId);
      if (selectedIdRef.current === sourceItemId) {
        selectionEpochRef.current += 1;
        const target = response.dictionary.items.find(
          (item) => item.item_id === targetItemId
        );
        const nextDraft = itemDraft(target);
        selectedIdRef.current = targetItemId;
        itemFormRef.current = nextDraft;
        setSelectedId(targetItemId);
        setItemForm(nextDraft);
      }
      setConfirmation(null);
      if (labDictionaryMutationAffectsReports(response.effects)) onReportsChanged();
    } catch (mergeError) {
      const message = mergeError instanceof Error ? mergeError.message : "指标合并失败。";
      setError(message);
      if (
        mergeError instanceof ApiRequestError
        && mergeError.detail?.code === "LAB_DICTIONARY_REVISION_CONFLICT"
      ) {
        setConfirmation(null);
        await loadDictionary();
      }
    } finally {
      setSaving(false);
    }
  }

  function cancelConfirmation() {
    if (confirmation) {
      const source = dictionaryRef.current?.items.find(
        (item) => item.item_id === confirmation.sourceItemId
      );
      if (source && selectedIdRef.current === confirmation.sourceItemId) {
        selectionEpochRef.current += 1;
        const restoredDraft = itemDraft(source);
        itemFormRef.current = restoredDraft;
        setItemForm(restoredDraft);
      }
      setError("");
    }
    setConfirmation(null);
  }

  async function saveItemJob(job: ItemAutoSaveJob) {
    setError("");
    const currentDictionary = dictionaryRef.current;
    if (!currentDictionary) return;
    let response;
    try {
      response = await writeItemAutoSaveJob(job, currentDictionary);
    } catch (saveError) {
      const conflictingItemId = saveError instanceof ApiRequestError
        && saveError.detail?.code === "LAB_DICTIONARY_NAME_CONFLICT"
        && typeof saveError.detail.conflicting_item_id === "string"
        ? saveError.detail.conflicting_item_id
        : "";
      if (conflictingItemId) {
        itemSaves.discard();
        if (openItemMergeConfirmation(job, conflictingItemId)) return;
      }
      if (!isLabDictionaryRevisionConflict(saveError)) throw saveError;
      const latestDictionary = await labDictionaryApi.fetchLabDictionary();
      dictionaryRef.current = latestDictionary;
      setDictionary(latestDictionary);
      if (!itemJobCanRebase(job, latestDictionary, itemSaves.resolve(job.targetKey))) {
        throw new Error("该指标已在其他页面发生更新。当前编辑内容已保留，请核对后重新编辑。");
      }
      response = await writeItemAutoSaveJob(job, latestDictionary);
    }
    const resolvedTarget = itemSaves.resolve(job.targetKey);
    dictionaryRef.current = response.dictionary;
    setDictionary(response.dictionary);
    const savedItemId = resolvedTarget || job.targetKey;
    if (job.selectionEpoch === selectionEpochRef.current) {
      selectedIdRef.current = savedItemId;
      setSelectedId(savedItemId);
      if (itemDraftSignature(itemFormRef.current) === itemDraftSignature(job.draft)) {
        const savedItem = response.dictionary.items.find(
          (candidate) => candidate.item_id === savedItemId
        );
        const savedDraft = itemDraft(savedItem);
        itemFormRef.current = savedDraft;
        setItemForm(savedDraft);
      }
    }
    if (labDictionaryMutationAffectsReports(response.effects)) onReportsChanged();
  }
  function enqueueCategoryAutoSave(draft: CategoryDraft) {
    const currentDictionary = dictionaryRef.current;
    const targetKey = selectedIdRef.current;
    if (!draft.category_name.trim() || !currentDictionary || !targetKey) return;
    if (!currentDictionary.categories.some((category) => category.category_name === targetKey)) return;
    const job: CategoryAutoSaveJob = {
      draft: { ...draft },
      targetKey,
      selectionEpoch: selectionEpochRef.current
    };
    categorySaves.enqueue(job);
  }

  function scheduleCategoryDraft(
    update: (current: CategoryDraft) => CategoryDraft,
    { immediate = false }: { immediate?: boolean } = {}
  ) {
    const nextDraft = update(categoryFormRef.current);
    categoryFormRef.current = nextDraft;
    setCategoryForm(nextDraft);
    categorySaves.schedule(nextDraft.category_name.trim() ? () => enqueueCategoryAutoSave(categoryFormRef.current) : null, immediate);
  }

  function flushScheduledCategorySave() { categorySaves.flushScheduled(); }

  async function writeCategoryAutoSaveJob(
    job: CategoryAutoSaveJob,
    currentDictionary: LabDictionaryResponse
  ) {
    return labDictionaryApi.updateLabDictionaryCategory(
      categorySaves.resolve(job.targetKey) || job.targetKey,
      categoryInput(job.draft, currentDictionary.dictionary_revision)
    );
  }

  async function saveCategoryJob(job: CategoryAutoSaveJob) {
    setError("");
    const currentDictionary = dictionaryRef.current;
    if (!currentDictionary) return;
    let response;
    try {
      response = await writeCategoryAutoSaveJob(job, currentDictionary);
    } catch (saveError) {
      if (!isLabDictionaryRevisionConflict(saveError)) throw saveError;
      const latestDictionary = await labDictionaryApi.fetchLabDictionary();
      dictionaryRef.current = latestDictionary;
      setDictionary(latestDictionary);
      const target = categorySaves.resolve(job.targetKey) || job.targetKey;
      if (!latestDictionary.categories.some((category) => category.category_name === target)) {
        throw new Error("该分类已被删除或重命名，当前编辑无法继续。请重新选择分类后再操作。");
      }
      response = await writeCategoryAutoSaveJob(job, latestDictionary);
    }
    const resolvedTarget = categorySaves.resolve(job.targetKey);
    const savedName = job.draft.category_name.trim();
    dictionaryRef.current = response.dictionary;
    setDictionary(response.dictionary);
    categorySaves.remember(job.targetKey, savedName);
    if (resolvedTarget && resolvedTarget !== savedName) {
      categorySaves.remember(resolvedTarget, savedName);
    }
    if (job.selectionEpoch === selectionEpochRef.current) {
      selectedIdRef.current = savedName;
      setSelectedId(savedName);
      if (
        categoryDraftSignature(categoryFormRef.current)
        === categoryDraftSignature(job.draft)
      ) {
        const savedCategory = response.dictionary.categories.find(
          (candidate) => candidate.category_name === savedName
        );
        const savedDraft = categoryDraft(savedCategory);
        categoryFormRef.current = savedDraft;
        setCategoryForm(savedDraft);
      }
    }
    if (labDictionaryMutationAffectsReports(response.effects)) onReportsChanged();
  }

  function canLeave() {
    const changed = tab === "items"
      ? itemDraftSignature(itemFormRef.current) !== itemDraftSignature(itemDraft(activeItem))
      : categoryDraftSignature(categoryFormRef.current) !== categoryDraftSignature(categoryDraft(activeCategory));
    return !confirmation && !(error && changed && selectedIdRef.current);
  }

  navigationSave.current = async () => {
    flushScheduledItemSave();
    flushScheduledCategorySave();
    if (!itemSaves.running && !categorySaves.running) return Boolean(canLeave());
    return new Promise<boolean>(resolve => navigationWaiters.current.push(resolve));
  };
  useEffect(() => registerNavigationSave(() => navigationSave.current()), []);
  useEffect(() => {
    if (itemSaves.running || categorySaves.running) return;
    const waiters = navigationWaiters.current.splice(0);
    for (const resolve of waiters) resolve(Boolean(canLeave()));
  }, [saving, error, dictionary, confirmation]);
  useEffect(() => () => {
    for (const resolve of navigationWaiters.current.splice(0)) resolve(false);
  }, []);

  return { selectionMode, catalogTitle, batchBusy, saving, selectedEntryIds, requestDelete, setQuery, tab, query, categoryFilterOptions, setCategoryFilter, selectedCategoryFilters, loading, cancelSelection, listRef, sortedFilteredItems, filteredCategories, setSelectedEntryIds, startCreate, listMenu, selectedId, activateEntry, visibleEntityCount, listEmptyMessage, contextEntry, contextEntryName, beginSelection, goBackFromDetail, detailTitle, dictionary, activeItem, flushScheduledItemSave, scheduleItemDraft, itemForm, primaryCategorySummary, relatedCategorySummary, activeCategory, flushScheduledCategorySave, scheduleCategoryDraft, categoryForm, activeCategoryItems, selectEntity, createDialog, setCreateDialog, createEntry, confirmation, cancelConfirmation };
}
