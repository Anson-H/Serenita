import { useEffect, useState } from "react";
import { dateOnly, range } from "./bodyMetricPresentation";
export function useBodyMetricFilters(memberId: string, category: string | null) {
  const [offset, setOffset] = useState(0);
  const [date, setDate] = useState(dateOnly), [customEnd, setCustomEnd] = useState(dateOnly), [period, setPeriod] = useState("week");
  const [source, setSource] = useState(""), [metric, setMetric] = useState(""), [hours, setHours] = useState(24);
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const dates = range(date, period, customEnd);
  useEffect(() => { setOffset(0); setMetric(""); }, [category, memberId]);
  useEffect(() => { setOffset(0); }, [dates.after, dates.before, source, category]);
  function shift(direction: number) {
    const d = new Date(`${date}T12:00:00Z`);
    if (period === "year") {
      d.setUTCMonth(0, 1);
      d.setUTCFullYear(d.getUTCFullYear() + direction);
    } else if (period === "month") {
      d.setUTCDate(1);
      d.setUTCMonth(d.getUTCMonth() + direction);
    } else
      d.setUTCDate(d.getUTCDate() + direction * (period === "week" ? 7 : 1));
    setDate(d.toISOString().slice(0, 10));
    setOffset(0);
  }
  return { offset, setOffset, date, setDate, customEnd, setCustomEnd, period, setPeriod, source, setSource, metric, setMetric, hours, setHours, timezone, dates, shift };
}
export type BodyMetricFiltersState = ReturnType<typeof useBodyMetricFilters>;
