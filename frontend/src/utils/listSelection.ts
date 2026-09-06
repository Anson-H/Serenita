export function areAllSelected(ids: readonly string[], selectedIds: ReadonlySet<string>) {
  return ids.length > 0 && ids.every((id) => selectedIds.has(id));
}

export function toggleAllSelection(ids: readonly string[], selectedIds: ReadonlySet<string>) {
  const next = new Set(selectedIds);
  const remove = areAllSelected(ids, selectedIds);
  for (const id of ids) {
    if (remove) next.delete(id);
    else next.add(id);
  }
  return next;
}
