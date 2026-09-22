import {useEffect, useMemo, useState} from 'react';
import type {MemoryReadQuery} from "../../api/memory/memoryApi";

export type MemoryFilters = {search: string; start: string; end: string};
const emptyFilters: MemoryFilters = {search: '', start: '', end: ''};
function savedFilters(storageKey: string): MemoryFilters {
  try {
    const value = JSON.parse(localStorage.getItem(storageKey) || 'null');
    if (value && typeof value.search === 'string' && typeof value.start === 'string' && typeof value.end === 'string'
      && [value.start, value.end].every(date => !date || /^\d{4}-\d{2}-\d{2}$/.test(date))) return value;
  } catch { /* Filters remain usable when browser storage is unavailable. */ }
  return emptyFilters;
}

export function useMemoryFilters(storageKey: string) {
  const [filters, setFilters] = useState(() => savedFilters(storageKey));
  const invalid = Boolean(filters.start && filters.end && filters.start > filters.end);
  const [applied, setApplied] = useState(() => invalid ? emptyFilters : filters);
  const [saveError, setSaveError] = useState('');
  useEffect(() => {
    if (invalid) return;
    const timeout = window.setTimeout(() => setApplied(filters), 300);
    return () => window.clearTimeout(timeout);
  }, [filters, invalid]);
  const query = useMemo<MemoryReadQuery>(() => ({view: 'current', query: applied.search,
    ...((applied.start || applied.end) ? {target_time: {
      ...(applied.start ? {start: {value: applied.start, precision: 'day' as const}} : {}),
      ...(applied.end ? {end: {value: applied.end, precision: 'day' as const}} : {}), uncertainty: 'exact' as const, unknown: []
    }} : {})}), [applied]);
  function change(field: keyof MemoryFilters, value: string) {
    const next = {...filters, [field]: value};
    setFilters(next);
    try {localStorage.setItem(storageKey, JSON.stringify(next)); setSaveError('');}
    catch {setSaveError('浏览器未能保存筛选条件，离开后可能无法恢复。');}
  }
  return {filters, query, invalid, saveError, change};
}
