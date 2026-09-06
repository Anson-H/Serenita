import type { Dispatch, SetStateAction } from "react";

import { areAllSelected, toggleAllSelection } from "../utils/listSelection";
import { ListChecksIcon } from "./icons";

export function SelectAllButton({
  disabled = false,
  ids,
  scopeLabel,
  selectedIds,
  onChange
}: {
  disabled?: boolean;
  ids: readonly string[];
  scopeLabel: string;
  selectedIds: ReadonlySet<string>;
  onChange: Dispatch<SetStateAction<Set<string>>>;
}) {
  const allSelected = areAllSelected(ids, selectedIds);
  const label = `${allSelected ? "取消全选" : "全选"}${scopeLabel}`;
  const unavailable = disabled || ids.length === 0;

  return (
    <button
      aria-label={label}
      aria-pressed={allSelected}
      className="control control--inline control--icon control--ghost selection-select-all standard-bar-icon-control"
      disabled={unavailable}
      onClick={() => {
        if (!unavailable) onChange((current) => toggleAllSelection(ids, current));
      }}
      title={label}
      type="button"
    >
      <ListChecksIcon />
    </button>
  );
}
