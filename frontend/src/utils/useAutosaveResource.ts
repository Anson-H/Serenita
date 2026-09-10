import { useEffect, useRef, useState } from "react";
import { useActiveScope } from "./useActiveScope";
import { useResourceDraft } from "./useResourceDraft";

/** Shared persistence, composition, debounce, deletion and navigation lifecycle. */
export function useAutosaveResource<T>({ resourceKey, server, enabled, isNew = false, createMessage = "请完成创建或取消后再离开。", validate, save, remove, onRemoved }: {
  resourceKey: string; server: T; enabled: boolean; isNew?: boolean; createMessage?: string;
  validate?: (value: T) => string;
  save: (value: T) => Promise<T>;
  remove?: () => Promise<void>;
  onRemoved?: () => void;
}) {
  const current = useActiveScope(resourceKey);
  const editable = useRef(enabled); editable.current = enabled;
  const creating = useRef(false);
  const activeDeletion = useRef<Promise<boolean> | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [operationError, setOperationError] = useState("");
  const state = useResourceDraft({ resourceKey, server, validate, saveEnabled: enabled, beforeNavigate: () => activeDeletion.current ?? Promise.resolve(true), save: async value => {
    if (!current() || !editable.current) throw new Error("当前页面或权限已改变，草稿未提交。");
    if (isNew && !creating.current) throw new Error(createMessage);
    return save(value);
  } });
  const flushRef = useRef(state.flush); flushRef.current = state.flush;
  useEffect(() => {
    if (!enabled || isNew || deleting || !state.dirty || state.pending || state.error || operationError) return;
    const timer = window.setTimeout(() => { void flushRef.current(); }, 400);
    return () => window.clearTimeout(timer);
  }, [enabled, isNew, deleting, state.revision, state.pending, state.error, operationError]);
  useEffect(() => { state.controller.resume(); return () => state.controller.pause(); }, [state.controller]);
  async function flush(create = false) {
    setOperationError("");
    creating.current = create;
    try {
      if (create) return await state.controller.flush(async value => {
        if (!current() || !editable.current) throw new Error("当前页面或权限已改变，草稿未提交。");
        return save(value);
      }, validate, true);
      return await state.flush();
    } finally { creating.current = false; }
  }
  async function deleteResource() {
    if (activeDeletion.current) return activeDeletion.current;
    if (!remove || !editable.current || deleting) return false;
    state.controller.pause(); setDeleting(true); setOperationError("");
    const deletion = (async () => {
      await state.controller.settled();
      if (!current() || !editable.current) {
        state.controller.resume();
        if (current()) setDeleting(false);
        return false;
      }
      try {
        await remove();
        state.controller.cancel();
        return true;
      } catch (cause) {
        state.controller.resume();
        if (current()) setOperationError(cause instanceof Error ? cause.message : "删除失败。");
        return false;
      } finally { if (current()) setDeleting(false); }
    })();
    activeDeletion.current = deletion;
    const removed = await deletion;
    if (activeDeletion.current === deletion) activeDeletion.current = null;
    // A successful deletion's own navigation runs after its barrier settles.
    if (removed && current()) onRemoved?.();
    return removed;
  }
  return { ...state, saving: state.pending, error: operationError || state.error, deleting, flush, remove: deleteResource,
    flushOnBlur: () => state.controller.snapshot().error || operationError ? Promise.resolve(false) : state.flush(),
    change: (changes: Partial<T>, immediate = false) => { if (editable.current && !deleting) { setOperationError(""); state.update({ ...state.controller.snapshot().draft, ...changes }); if (immediate && !isNew) void flushRef.current(); } },
    compose: (value: boolean) => state.controller.composition(value),
    discard: () => { state.controller.pause(); state.controller.cancel(); },
  };
}
