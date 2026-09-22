import { useEffect, useState } from "react";
import { dateOnly, range } from "./bodyMetricPresentation";
export function useBodyMetricFilters(memberId: string, category: string | null) {
  const [offset, setOffset] = useState(0);
  const [date, setDate] = useState(dateOnly), [customEnd, setCustomEnd] = useState(dateOnly), [period, setPeriod] = useState("week");
  const [source, setSource] = useState(""), [metric, setMetric] = useState(""), [hours, setHours] = useState(24);
  const dates = range(date, period, customEnd);
  useEffect(() => { setOffset(0); setMetric(""); }, [category, memberId]);
  useEffect(() => { setOffset(0); }, [dates.after, dates.before, source, category]);
  function shift(direction: number) {
    const d = new Date(`${date}T12:00:00`);
    if (period === "year") {
      d.setMonth(0, 1);
      d.setFullYear(d.getFullYear() + direction);
    } else if (period === "month") {
      d.setDate(1);
      d.setMonth(d.getMonth() + direction);
    } else
      d.setDate(d.getDate() + direction * (period === "week" ? 7 : 1));
    setDate(dateOnly(d));
    setOffset(0);
  }
  return { offset, setOffset, date, setDate, customEnd, setCustomEnd, period, setPeriod, source, setSource, metric, setMetric, hours, setHours, dates, shift };
}
export type BodyMetricFiltersState = ReturnType<typeof useBodyMetricFilters>;
