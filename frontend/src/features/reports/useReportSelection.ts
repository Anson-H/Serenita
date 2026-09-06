import { useState, type SetStateAction } from "react";
import { useActiveScope } from "../../utils/useActiveScope";

const EMPTY_SELECTION = new Set<string>();

export function useReportSelection(memberId: string) {
  const isCurrent = useActiveScope(memberId);
  const [selection, setSelection] = useState({ memberId, ids: EMPTY_SELECTION });
  const ids = selection.memberId === memberId ? selection.ids : EMPTY_SELECTION;
  function setIds(next: SetStateAction<Set<string>>) {
    if (!isCurrent()) return;
    setSelection(current => {
      const currentIds = current.memberId === memberId ? current.ids : EMPTY_SELECTION;
      return { memberId, ids: typeof next === "function" ? next(currentIds) : next };
    });
  }
  return [ids, setIds] as const;
}
