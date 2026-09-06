import type { Dispatch, RefObject, SetStateAction } from "react";
import {
  apiClient,
  type LabDictionaryResponse,
  type LabItemWriteInput
} from "../../api/client";
import { labDictionaryMutationAffectsReports } from "../../api/labDictionaryApi";
import { ApiRequestError } from "../../api/request";
import type { ItemAutoSaveJob, ItemDraft, PendingMergeConfirmation } from "./labDictionaryDrafts";
import { cloneItemDraft, itemDraft, itemDraftSignature } from "./labDictionaryDrafts";

type Dependencies = {
  savedItemTargetsRef: RefObject<Map<string, string>>;
  dictionaryRef: RefObject<LabDictionaryResponse | null>;
  selectionEpochRef: RefObject<number>;
  selectedIdRef: RefObject<string>;
  itemSaveQueueRef: RefObject<ItemAutoSaveJob[]>;
  itemFormRef: RefObject<ItemDraft>;
  setItemForm: Dispatch<SetStateAction<ItemDraft>>;
  itemSaveTimerRef: RefObject<number | null>;
  setError: Dispatch<SetStateAction<string>>;
  setConfirmation: Dispatch<SetStateAction<PendingMergeConfirmation | null>>;
  setSaving: Dispatch<SetStateAction<boolean>>;
  setDictionary: Dispatch<SetStateAction<LabDictionaryResponse | null>>;
  setSelectedId: Dispatch<SetStateAction<string>>;
  onReportsChanged: () => void;
  loadDictionary: () => Promise<void>;
  confirmation: PendingMergeConfirmation | null;
  itemSaveRunningRef: RefObject<boolean>;
};

export function createLabItemEditorActions({
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
}: Dependencies) {
  function itemInput(draft: ItemDraft, revision: string): LabItemWriteInput {
    return {
      item_name_zh: draft.item_name_zh.trim(),
      aliases: draft.aliases,
      description: draft.description.trim() || null,
      primary_category_name: draft.primary_category_name,
      related_category_names: draft.related_category_names,
      expected_dictionary_revision: revision
    };
  }

  function resolveSavedItemTarget(targetKey: string) {
    let resolved = savedItemTargetsRef.current.get(targetKey) ?? "";
    const visited = new Set<string>();
    while (resolved && !visited.has(resolved)) {
      visited.add(resolved);
      const next = savedItemTargetsRef.current.get(resolved);
      if (!next) break;
      resolved = next;
    }
    return resolved;
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
    itemSaveQueueRef.current = [
      ...itemSaveQueueRef.current.filter((queued) => queued.targetKey !== targetKey),
      job
    ];
    void drainItemAutoSaveQueue();
  }

  function scheduleItemDraft(
    update: (current: ItemDraft) => ItemDraft,
    { immediate = false }: { immediate?: boolean } = {}
  ) {
    const nextDraft = update(itemFormRef.current);
    itemFormRef.current = nextDraft;
    setItemForm(nextDraft);
    if (itemSaveTimerRef.current !== null) {
      window.clearTimeout(itemSaveTimerRef.current);
      itemSaveTimerRef.current = null;
    }
    if (!nextDraft.item_name_zh.trim() || !nextDraft.primary_category_name) {
      return;
    }
    if (immediate) {
      enqueueItemAutoSave(nextDraft);
      return;
    }
    itemSaveTimerRef.current = window.setTimeout(() => {
      itemSaveTimerRef.current = null;
      enqueueItemAutoSave(itemFormRef.current);
    }, 550);
  }

  function flushScheduledItemSave() {
    if (itemSaveTimerRef.current === null) return;
    window.clearTimeout(itemSaveTimerRef.current);
    itemSaveTimerRef.current = null;
    enqueueItemAutoSave(itemFormRef.current);
  }

  async function writeItemAutoSaveJob(
    job: ItemAutoSaveJob,
    currentDictionary: LabDictionaryResponse
  ) {
    const resolvedTarget = resolveSavedItemTarget(job.targetKey);
    return apiClient.updateLabDictionaryItem(
      resolvedTarget || job.targetKey,
      itemInput(job.draft, currentDictionary.dictionary_revision)
    );
  }

  function itemJobCanRebase(job: ItemAutoSaveJob, latestDictionary: LabDictionaryResponse) {
    const resolvedTarget = resolveSavedItemTarget(job.targetKey);
    const latestItem = latestDictionary.items.find(
      (item) => item.item_id === (resolvedTarget || job.targetKey)
    );
    return Boolean(
      latestItem
      && job.baseDraftSignature
      && itemDraftSignature(itemDraft(latestItem)) === job.baseDraftSignature
    );
  }

  function openItemMergeConfirmation(job: ItemAutoSaveJob, targetItemId: string) {
    const sourceItemId = resolveSavedItemTarget(job.targetKey) || job.targetKey;
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
      const response = await apiClient.mergeLabDictionaryItems(
        sourceItemId,
        targetItemId,
        currentDictionary.dictionary_revision
      );
      dictionaryRef.current = response.dictionary;
      setDictionary(response.dictionary);
      savedItemTargetsRef.current.set(sourceItemId, targetItemId);
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

  async function drainItemAutoSaveQueue() {
    if (itemSaveRunningRef.current) return;
    itemSaveRunningRef.current = true;
    setSaving(true);
    setError("");
    try {
      while (itemSaveQueueRef.current.length) {
        const job = itemSaveQueueRef.current.shift();
        const currentDictionary = dictionaryRef.current;
        if (!job || !currentDictionary) continue;
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
            itemSaveQueueRef.current = [];
            if (openItemMergeConfirmation(job, conflictingItemId)) return;
          }
          const message = saveError instanceof Error ? saveError.message : "";
          if (!message.includes("刷新")) throw saveError;
          const latestDictionary = await apiClient.fetchLabDictionary();
          dictionaryRef.current = latestDictionary;
          setDictionary(latestDictionary);
          if (!itemJobCanRebase(job, latestDictionary)) {
            throw new Error("该指标已在其他页面发生修改。当前编辑内容已保留，请核对后再修改一次。");
          }
          response = await writeItemAutoSaveJob(job, latestDictionary);
        }
        const resolvedTarget = resolveSavedItemTarget(job.targetKey);
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
    } catch (mutationError) {
      itemSaveQueueRef.current = [];
      const message = mutationError instanceof Error ? mutationError.message : "指标自动保存失败。";
      setError(message);
    } finally {
      itemSaveRunningRef.current = false;
      setSaving(false);
      if (itemSaveQueueRef.current.length) void drainItemAutoSaveQueue();
    }
  }
  return {
    scheduleItemDraft,
    flushScheduledItemSave,
    cancelConfirmation
  };
}
