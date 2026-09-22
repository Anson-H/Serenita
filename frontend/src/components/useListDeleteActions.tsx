import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { GroupedList } from "./GroupedList";
import { CheckIcon, ListChecksIcon, TrashIcon } from "./icons";
import { ListSelectionBar } from "./ListSelectionBar";
import { ListBulkActions } from "./ListBulkActions";
import { SelectAllButton } from "./SelectAllButton";
import { useListContextMenu } from "./useListContextMenu";
import { useActiveScope } from "../utils/useActiveScope";

export function useListDeleteActions({ scope, enabled, entries, label, countLabel, onDelete, insetActions = false }: {
  scope: string; enabled: boolean; entries: { id: string; name: string }[]; label: string; countLabel: string;
  onDelete: (ids: string[]) => Promise<string[]>;
  insetActions?: boolean;
}) {
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState(new Set<string>());
  const [busy, setBusy] = useState(false);
  const running = useRef(false);
  const selectionHeading = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    if (selectionMode) selectionHeading.current?.querySelector<HTMLButtonElement>('button')?.focus({ preventScroll: true });
  }, [selectionMode]);
  const isCurrent = useActiveScope(scope);
  const menu = useListContextMenu({ enabled: enabled && !selectionMode && !busy, scope });
  const contextEntry = entries.find(entry => entry.id === menu.contextMenu?.id);
  function cancelSelection() { setSelectionMode(false); setSelectedIds(new Set()); }
  useEffect(() => { cancelSelection(); }, [scope, enabled]);
  useEffect(() => {
    const ids = new Set(entries.map(entry => entry.id));
    // A pending save may hide rows temporarily and restore them after failure.
    if (!busy) setSelectedIds(current => {
      const next = new Set([...current].filter(id => ids.has(id)));
      return next.size === current.size ? current : next;
    });
    if (menu.contextMenu && !contextEntry) menu.closeContextMenu(false);
  }, [entries, contextEntry, busy, menu.contextMenu, menu.closeContextMenu]);

  async function remove(ids: string[]) {
    if (!enabled || running.current || !ids.length) return;
    running.current = true; setBusy(true); menu.closeContextMenu(false);
    try {
      const failed = await onDelete(ids);
      if (!isCurrent()) return;
      if (failed.length && selectionMode) setSelectedIds(new Set(failed));
      else if (!failed.length) cancelSelection();
    } finally {
      running.current = false;
      if (isCurrent()) setBusy(false);
    }
  }
  function toggle(id: string) {
    if (busy) return;
    setSelectedIds(current => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }
  return {
    selectionMode, busy, toggle, rowProps: menu.rowProps,
    selected: (id: string) => selectedIds.has(id),
    indicator: (id: string) => selectionMode ? <span aria-hidden="true" className="selection-check-control" data-selected={selectedIds.has(id) ? "true" : undefined}>
      {selectedIds.has(id) ? <CheckIcon className="selection-check-icon" /> : null}
    </span> : null,
    onKeyDown: (event: React.KeyboardEvent) => { if (event.key === "Escape" && selectionMode && !busy) { event.preventDefault(); event.stopPropagation(); cancelSelection(); } },
    heading: selectionMode ? <ListSelectionBar ref={selectionHeading} summary={`已选择 ${selectedIds.size} ${countLabel}`} label={`${label}多选`} cancelLabel={`退出${label}多选`} busy={busy} onCancel={cancelSelection}>
        <SelectAllButton disabled={busy} ids={entries.map(entry => entry.id)} scopeLabel={label} selectedIds={selectedIds} onChange={setSelectedIds} />
    </ListSelectionBar> : null,
    toolbar: selectionMode ? <ListBulkActions label={`${label}批量操作`} inset={insetActions}>
      <button type="button" className="control control--compact control--secondary control--danger removal-action-control" aria-busy={busy} disabled={!enabled || busy || !selectedIds.size} onClick={() => void remove([...selectedIds])}><TrashIcon /><span>删除</span></button>
    </ListBulkActions> : null,
    portal: menu.contextMenu && contextEntry && enabled ? createPortal(<GroupedList density="standard" className="context-action-menu scroll-balanced" role="menu" data-modal-focus-scope="true"
      aria-label={`${contextEntry.name} 的${label}操作`} ref={menu.menuRef} onKeyDown={menu.onMenuKeyDown} style={{ left: menu.contextMenu.x, top: menu.contextMenu.y }}>
      <button type="button" role="menuitem" onClick={() => { menu.closeContextMenu(false); setSelectionMode(true); setSelectedIds(new Set([contextEntry.id])); }}><ListChecksIcon className="context-action-menu-icon" /><span>多选</span></button>
      <button type="button" role="menuitem" className="control control--secondary control--danger context-action-menu-removal removal-action-control" onClick={() => void remove([contextEntry.id])}><TrashIcon className="context-action-menu-icon" /><span>删除</span></button>
    </GroupedList>, document.body) : null
  };
}
