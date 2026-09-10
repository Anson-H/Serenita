import type { Dispatch, RefObject, SetStateAction } from "react";
import {
  apiClient,
  type LabCategoryWriteInput,
  type LabDictionaryResponse
} from "../../api/client";
import { labDictionaryMutationAffectsReports } from "../../api/labDictionaryApi";
import type { CategoryAutoSaveJob, CategoryDraft } from "./labDictionaryDrafts";
import { categoryDraft, categoryDraftSignature } from "./labDictionaryDrafts";

type Dependencies = {
  savedCategoryTargetsRef: RefObject<Map<string, string>>;
  dictionaryRef: RefObject<LabDictionaryResponse | null>;
  selectedIdRef: RefObject<string>;
  selectionEpochRef: RefObject<number>;
  categorySaveQueueRef: RefObject<CategoryAutoSaveJob[]>;
  categoryFormRef: RefObject<CategoryDraft>;
  setCategoryForm: Dispatch<SetStateAction<CategoryDraft>>;
  categorySaveTimerRef: RefObject<number | null>;
  categorySaveRunningRef: RefObject<boolean>;
  setSaving: Dispatch<SetStateAction<boolean>>;
  setError: Dispatch<SetStateAction<string>>;
  setDictionary: Dispatch<SetStateAction<LabDictionaryResponse | null>>;
  setSelectedId: Dispatch<SetStateAction<string>>;
  onReportsChanged: () => void;
};

export function createLabCategoryEditorActions({
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
}: Dependencies) {
  function categoryInput(draft: CategoryDraft, revision: string): LabCategoryWriteInput {
    return {
      category_name: draft.category_name.trim(),
      description: draft.description.trim() || null,
      expected_dictionary_revision: revision
    };
  }

  function resolveSavedCategoryTarget(targetKey: string) {
    let resolved = savedCategoryTargetsRef.current.get(targetKey) ?? "";
    const visited = new Set<string>();
    while (resolved && !visited.has(resolved)) {
      visited.add(resolved);
      const next = savedCategoryTargetsRef.current.get(resolved);
      if (!next) break;
      resolved = next;
    }
    return resolved;
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
    categorySaveQueueRef.current = [
      ...categorySaveQueueRef.current.filter((queued) => queued.targetKey !== targetKey),
      job
    ];
    void drainCategoryAutoSaveQueue();
  }

  function scheduleCategoryDraft(
    update: (current: CategoryDraft) => CategoryDraft,
    { immediate = false }: { immediate?: boolean } = {}
  ) {
    const nextDraft = update(categoryFormRef.current);
    categoryFormRef.current = nextDraft;
    setCategoryForm(nextDraft);
    if (categorySaveTimerRef.current !== null) {
      window.clearTimeout(categorySaveTimerRef.current);
      categorySaveTimerRef.current = null;
    }
    if (!nextDraft.category_name.trim()) return;
    if (immediate) {
      enqueueCategoryAutoSave(nextDraft);
      return;
    }
    categorySaveTimerRef.current = window.setTimeout(() => {
      categorySaveTimerRef.current = null;
      enqueueCategoryAutoSave(categoryFormRef.current);
    }, 550);
  }

  function flushScheduledCategorySave() {
    if (categorySaveTimerRef.current === null) return;
    window.clearTimeout(categorySaveTimerRef.current);
    categorySaveTimerRef.current = null;
    enqueueCategoryAutoSave(categoryFormRef.current);
  }

  async function writeCategoryAutoSaveJob(
    job: CategoryAutoSaveJob,
    currentDictionary: LabDictionaryResponse
  ) {
    return apiClient.updateLabDictionaryCategory(
      resolveSavedCategoryTarget(job.targetKey) || job.targetKey,
      categoryInput(job.draft, currentDictionary.dictionary_revision)
    );
  }

  async function drainCategoryAutoSaveQueue() {
    if (categorySaveRunningRef.current) return;
    categorySaveRunningRef.current = true;
    setSaving(true);
    setError("");
    try {
      while (categorySaveQueueRef.current.length) {
        const job = categorySaveQueueRef.current.shift();
        const currentDictionary = dictionaryRef.current;
        if (!job || !currentDictionary) continue;
        let response;
        try {
          response = await writeCategoryAutoSaveJob(job, currentDictionary);
        } catch (saveError) {
          const message = saveError instanceof Error ? saveError.message : "";
          if (!message.includes("刷新")) throw saveError;
          const latestDictionary = await apiClient.fetchLabDictionary();
          dictionaryRef.current = latestDictionary;
          setDictionary(latestDictionary);
          const target = resolveSavedCategoryTarget(job.targetKey) || job.targetKey;
          if (!latestDictionary.categories.some((category) => category.category_name === target)) {
            throw new Error("该分类已被删除或重命名，当前编辑无法继续。请重新选择分类后再操作。");
          }
          response = await writeCategoryAutoSaveJob(job, latestDictionary);
        }
        const resolvedTarget = resolveSavedCategoryTarget(job.targetKey);
        const savedName = job.draft.category_name.trim();
        dictionaryRef.current = response.dictionary;
        setDictionary(response.dictionary);
        savedCategoryTargetsRef.current.set(job.targetKey, savedName);
        if (resolvedTarget && resolvedTarget !== savedName) {
          savedCategoryTargetsRef.current.set(resolvedTarget, savedName);
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
    } catch (mutationError) {
      categorySaveQueueRef.current = [];
      const message = mutationError instanceof Error
        ? mutationError.message
        : "分类自动保存失败。";
      setError(message);
    } finally {
      categorySaveRunningRef.current = false;
      setSaving(false);
      if (categorySaveQueueRef.current.length) void drainCategoryAutoSaveQueue();
    }
  }
  return {
    scheduleCategoryDraft,
    flushScheduledCategorySave
  };
}
