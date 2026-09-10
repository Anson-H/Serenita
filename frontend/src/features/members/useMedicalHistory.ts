import { useEffect, useRef, useState } from "react";
import { captureAuthContext, isAuthContextCurrent } from "../../api/authLifecycle";
import { fetchMedicalHistory, updateMedicalHistory, type MedicalHistory, type MedicalHistoryChanges, type MedicalHistoryField } from "../../api/medicalHistoryApi";

export function useMedicalHistory(memberId: string, canEdit: boolean) {
  const authContext = useRef(captureAuthContext());
  const [data, setData] = useState<MedicalHistory | null>(null);
  const [draft, setDraft] = useState<MedicalHistoryChanges>({});
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const pending = useRef<MedicalHistoryChanges>({});
  const chain = useRef<Promise<boolean>>(Promise.resolve(true));
  const timer = useRef<number | null>(null);
  const active = useRef(false);
  const editable = useRef(canEdit);
  editable.current = canEdit;
  const cancelled = useRef(false);
  const composing = useRef(false);

  function stopTimer() {
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = null;
  }

  function flush(): Promise<boolean> {
    stopTimer();
    if (cancelled.current || !editable.current || !isAuthContextCurrent(authContext.current)) return chain.current;
    const task = chain.current.then(async () => {
      if (cancelled.current || !editable.current || !isAuthContextCurrent(authContext.current)) return false;
      const changes = { ...pending.current };
      if (!Object.keys(changes).length) return true;
      pending.current = {};
      if (active.current) setSaving(true);
      try {
        const saved = await updateMedicalHistory(memberId, changes);
        if (active.current) {
          setData(saved);
          setDraft(current => {
            const next = { ...current };
            for (const key of Object.keys(changes) as MedicalHistoryField[]) {
              if (next[key] === changes[key]) delete next[key];
            }
            return next;
          });
          setError("");
        }
        return true;
      } catch (cause) {
        pending.current = { ...changes, ...pending.current };
        if (active.current) setError(cause instanceof Error ? cause.message : "既往史未保存。");
        return false;
      } finally {
        if (active.current) setSaving(false);
      }
    });
    chain.current = task;
    return task;
  }

  function change(field: MedicalHistoryField, value: string) {
    if (!editable.current || cancelled.current) return;
    pending.current[field] = value;
    setDraft(current => ({ ...current, [field]: value }));
    setError("");
    stopTimer();
    if (!composing.current) timer.current = window.setTimeout(() => { void flush(); }, 400);
  }

  function startComposition() { composing.current = true; stopTimer(); }
  function endComposition(field: MedicalHistoryField, value: string) { composing.current = false; change(field, value); }

  function cancel() {
    cancelled.current = true;
    stopTimer();
    return chain.current;
  }

  function resume() {
    cancelled.current = false;
    if (Object.keys(pending.current).length) timer.current = window.setTimeout(() => { void flush(); }, 400);
  }

  useEffect(() => {
    active.current = true;
    const controller = new AbortController();
    void fetchMedicalHistory(memberId, controller.signal).then(result => {
      if (active.current) setData(result);
    }).catch(cause => {
      if (!controller.signal.aborted && active.current) setError(cause instanceof Error ? cause.message : "既往史读取失败。");
    });
    return () => {
      active.current = false;
      controller.abort();
      void flush();
    };
  }, [memberId]);

  useEffect(() => {
    if (!canEdit) stopTimer();
  }, [canEdit]);

  return { data, draft, error, saving, change, flush, cancel, resume, startComposition, endComposition };
}
