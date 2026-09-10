import { useCallback, useEffect, useRef, useState } from "react";
import { getCatalog, getStatistics, getRecords, type Catalog, type Statistics, type BodyRecord } from "../../api/bodyMetricApi";
import type { BodyMetricFiltersState } from "./useBodyMetricFilters";
const EMPTY: Statistics = {
  series: [],
  sources: [],
  total_records: 0,
  coverage_dates: { first: null, last: null, recorded_days: 0 },
  missing_values: {},
  coverage_from: null,
  coverage_to: null,
  excluded_stale_scores: 0,
};
export function useBodyMetricData(memberId: string, category: string | null, filters: BodyMetricFiltersState) {
  const { dates, source, timezone, offset, setOffset } = filters;
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [statistics, setStatistics] = useState<Statistics>(EMPTY);
  const [records, setRecords] = useState<BodyRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [refresh, setRefresh] = useState(0);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const statisticsRange = useRef("");
  const recordsRange = useRef("");
  const [statisticsError, setStatisticsError] = useState(""), [recordsError, setRecordsError] = useState(""), [recordsLoading, setRecordsLoading] = useState(false);
  const refreshData = useCallback(() => setRefresh(value => value + 1), []);
  useEffect(() => {
    const c = new AbortController();
    void getCatalog(memberId, c.signal)
      .then(result => { if (!c.signal.aborted) setCatalog(result); })
      .catch((e) => {
        if (!c.signal.aborted) setError(e.message);
      });
    return () => c.abort();
  }, [memberId]);
  useEffect(() => { setStatistics(EMPTY); setRecords([]); setTotal(0); }, [memberId]);
  useEffect(() => {
    const c = new AbortController();
    setLoading(true);
    setStatisticsError("");
    const rangeKey = JSON.stringify([
      memberId,
      dates,
      source,
      timezone,
    ]);
    if (statisticsRange.current !== rangeKey) {
      setStatistics((current) => ({ ...EMPTY, sources: current.sources }));
      statisticsRange.current = rangeKey;
    }
    void getStatistics(
      memberId,
      { ...dates, source, timezone },
      c.signal,
    )
      .then((result) => {
        if (!c.signal.aborted) setStatistics(result);
      })
      .catch((e) => {
        if (!c.signal.aborted) setStatisticsError(e.message);
      })
      .finally(() => {
        if (!c.signal.aborted) setLoading(false);
      });
    return () => c.abort();
  }, [memberId, dates.after, dates.before, source, timezone, refresh]);
  useEffect(() => {
    const c = new AbortController();
    setRecordsLoading(true);
    setRecordsError("");
    const rangeKey = JSON.stringify([
      memberId,
      dates,
      source,
      timezone,
      category,
      offset,
    ]);
    if (recordsRange.current !== rangeKey) {
      setRecords([]);
      recordsRange.current = rangeKey;
    }
    void getRecords(
      memberId,
      {
        ...dates,
        category: category || undefined,
        source,
        timezone,
        offset,
        limit: 100,
      },
      c.signal,
    )
      .then((result) => {
        if (c.signal.aborted) return;
        setRecords(result.items);
        setTotal(result.total);
        if (offset >= result.total && offset > 0)
          setOffset(Math.max(0, Math.ceil(result.total / 100) - 1) * 100);
      })
      .catch((e) => {
        if (!c.signal.aborted) setRecordsError(e.message);
      })
      .finally(() => {
        if (!c.signal.aborted) setRecordsLoading(false);
      });
    return () => c.abort();
  }, [
    memberId,
    dates.after,
    dates.before,
    source,
    timezone,
    category,
    refresh,
    offset,
  ]);
  useEffect(() => {
    window.addEventListener("focus", refreshData);
    return () => window.removeEventListener("focus", refreshData);
  }, [refreshData]);
  return { catalog, statistics, records, total, refresh, error, setError, loading, statisticsError, recordsError, recordsLoading, refreshData };
}
