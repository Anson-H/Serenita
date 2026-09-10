import type { Dispatch, RefObject, SetStateAction } from "react";
import type {
  ModelUpdatePayload
} from "../../api/client";
import type { ModelAutoSaveJob, ModelSettingsDraft } from "./modelSettingsDraft";
import { modelSettingsPatch, modelSettingsPayload, modelSettingsSignature } from "./modelSettingsDraft";
import {
  settingsAutoSaveDelayMs
} from "./settingsTypes";

type Dependencies = {
  saveRunningRef: RefObject<boolean>;
  saveQueueRef: RefObject<ModelAutoSaveJob[]>;
  lastSavedSignatureRef: RefObject<string>;
  lastSavedPayloadRef: RefObject<ModelUpdatePayload>;
  onSaveRef: RefObject<(patch: ModelUpdatePayload) => void | Promise<void>>;
  mountedRef: RefObject<boolean>;
  setValidationError: Dispatch<SetStateAction<string>>;
  draftRef: RefObject<ModelSettingsDraft>;
  setDraft: Dispatch<SetStateAction<ModelSettingsDraft>>;
  saveTimerRef: RefObject<number | null>;
  deletingRef: RefObject<boolean>;
  setDeleting: Dispatch<SetStateAction<boolean>>;
  onDelete: () => Promise<boolean>;
  probing: boolean;
  onProbe: () => void | Promise<void>;
};

export function createModelEditorActions({
  saveRunningRef,
  saveQueueRef,
  lastSavedSignatureRef,
  lastSavedPayloadRef,
  onSaveRef,
  mountedRef,
  setValidationError,
  draftRef,
  setDraft,
  saveTimerRef,
  deletingRef,
  setDeleting,
  onDelete,
  probing,
  onProbe
}: Dependencies) {
  async function drainModelAutoSaveQueue() {
    if (saveRunningRef.current) return;
    saveRunningRef.current = true;
    try {
      while (saveQueueRef.current.length) {
        const job = saveQueueRef.current.shift();
        if (!job || job.signature === lastSavedSignatureRef.current) continue;
        const patch = modelSettingsPatch(job.target, lastSavedPayloadRef.current);
        if (!Object.keys(patch).length) {
          lastSavedSignatureRef.current = job.signature;
          continue;
        }
        try {
          await onSaveRef.current(patch);
          lastSavedPayloadRef.current = job.target;
          lastSavedSignatureRef.current = job.signature;
          if (mountedRef.current) setValidationError("");
        } catch (error) {
          saveQueueRef.current = [];
          if (mountedRef.current) {
            setValidationError(
              error instanceof Error ? error.message : "模型设置自动保存失败。"
            );
          }
          return;
        }
      }
    } finally {
      saveRunningRef.current = false;
      if (saveQueueRef.current.length) void drainModelAutoSaveQueue();
    }
  }

  function enqueueModelAutoSave(nextDraft: ModelSettingsDraft) {
    let target: ModelUpdatePayload;
    try {
      target = modelSettingsPayload(nextDraft);
      if (mountedRef.current) setValidationError("");
    } catch (error) {
      if (mountedRef.current) {
        setValidationError(error instanceof Error ? error.message : "模型设置无法保存。");
      }
      return;
    }
    const signature = modelSettingsSignature(target);
    if (
      !saveRunningRef.current
      && !saveQueueRef.current.length
      && signature === lastSavedSignatureRef.current
    ) return;
    saveQueueRef.current = [{ signature, target }];
    void drainModelAutoSaveQueue();
  }

  function scheduleModelDraft(
    update: (current: ModelSettingsDraft) => ModelSettingsDraft,
    { immediate = false }: { immediate?: boolean } = {}
  ) {
    const nextDraft = update(draftRef.current);
    draftRef.current = nextDraft;
    setDraft(nextDraft);
    if (saveTimerRef.current !== null) {
      window.clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
    }
    try {
      modelSettingsPayload(nextDraft);
      setValidationError("");
    } catch (error) {
      setValidationError(error instanceof Error ? error.message : "模型设置无法保存。");
      return;
    }
    if (immediate) {
      enqueueModelAutoSave(nextDraft);
      return;
    }
    saveTimerRef.current = window.setTimeout(() => {
      saveTimerRef.current = null;
      enqueueModelAutoSave(draftRef.current);
    }, settingsAutoSaveDelayMs);
  }

  function flushScheduledModelSave() {
    if (saveTimerRef.current === null) return;
    window.clearTimeout(saveTimerRef.current);
    saveTimerRef.current = null;
    enqueueModelAutoSave(draftRef.current);
  }

  async function deleteModel() {
    if (deletingRef.current) return;
    setDeleting(true);
    flushScheduledModelSave();
    while (saveRunningRef.current || saveQueueRef.current.length) {
      await new Promise<void>((resolve) => window.setTimeout(resolve, 20));
    }
    deletingRef.current = true;
    const deleted = await onDelete();
    if (!deleted) {
      deletingRef.current = false;
      if (mountedRef.current) setDeleting(false);
    }
  }

  async function probeModel() {
    if (deletingRef.current) return;
    if (probing) { await onProbe(); return; }
    flushScheduledModelSave();
    while (saveRunningRef.current || saveQueueRef.current.length) {
      await new Promise<void>((resolve) => window.setTimeout(resolve, 20));
    }
    await onProbe();
  }
  return {
    enqueueModelAutoSave,
    scheduleModelDraft,
    flushScheduledModelSave,
    deleteModel,
    probeModel
  };
}
