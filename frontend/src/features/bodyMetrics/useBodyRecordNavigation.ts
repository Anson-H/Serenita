import { useEffect, useRef, useState } from "react";
import { getRecord, type BodyInput, type BodyRecord } from "../../api/bodyMetricApi";
import { useActiveScope } from "../../utils/useActiveScope";
export function useBodyRecordNavigation(memberId: string, route: string, onError: (error: string) => void) {
  const [edit, updateEdit] = useState<{ input: BodyInput | BodyRecord; id?: string } | null>(null);
  const request = useRef<AbortController | null>(null);
  const current = useActiveScope(memberId);
  const setEdit: typeof updateEdit = value => { request.current?.abort(); updateEdit(value); };
  async function openRecord(id: string) {
    request.current?.abort();
    const controller = new AbortController(); request.current = controller;
    try {
      const record = await getRecord(memberId, id, controller.signal);
      if (current() && !controller.signal.aborted) updateEdit({ input: record, id });
    } catch (error) {
      if (current() && !controller.signal.aborted) onError(error instanceof Error ? error.message : "记录读取失败");
    }
  }
  useEffect(() => {
    const id = new URLSearchParams(route.split("?")[1] || "").get("record");
    if (id) void openRecord(id); else setEdit(null);
    return () => request.current?.abort();
  }, [memberId, route]);
  return { edit, setEdit, openRecord };
}
