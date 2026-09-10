import { useEffect, useState } from "react";
import {
  getSeriesData,
  type Bucket,
  type Filters,
  type Point,
  type Series,
  type SeriesPage,
} from "../../api/bodyMetricApi";
import { MetricChart } from "./MetricChart";
import { number, time } from "./bodyMetricPresentation";

export function BodySeriesChart({
  memberId,
  series,
  filters,
  daily,
  hours,
  onRecord,
  revision,
}: {
  memberId: string;
  revision: number;
  series: Series;
  filters: Filters;
  daily: boolean;
  hours: number;
  onRecord: (id: string) => void;
}) {
  const [day, setDay] = useState<string>();
  const [cursors, setCursors] = useState<(string | undefined)[]>([undefined]);
  const [page, setPage] = useState<SeriesPage<Point | Bucket>>();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [retry, setRetry] = useState(0);
  const view = daily || day ? "points" : "buckets";
  const cursor = cursors.at(-1);
  const { after, before, source, category, timezone } = filters;

  useEffect(() => {
    setCursors([undefined]);
  }, [revision]);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    void getSeriesData(
      memberId,
      series.series_id,
      view,
      {
        after: day || after,
        before: day || before,
        source,
        category,
        timezone,
      },
      cursor,
      controller.signal,
    )
      .then((result) => {
        if (!controller.signal.aborted) setPage(result);
      })
      .catch((reason) => {
        if (!controller.signal.aborted) setError(reason.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [
    memberId,
    series.series_id,
    view,
    day,
    after,
    before,
    source,
    category,
    timezone,
    cursor,
    retry,
    revision,
  ]);

  function drill(date?: string) {
    setDay(date);
    setCursors([undefined]);
    setPage(undefined);
  }
  return (
    <section aria-label={`${series.label}趋势数据`} aria-busy={loading}>
      {day ? (
        <div className="bm-section-heading">
          <h3>{day} 的记录</h3>
          <button className="control" type="button" onClick={() => drill()}>
            返回趋势
          </button>
        </div>
      ) : null}
      {error ? (
        <p role="alert">
          {error}{" "}
          <button
            className="control"
            type="button"
            onClick={() => {
              setCursors([undefined]);
              setRetry((v) => v + 1);
            }}
          >
            重新读取
          </button>
        </p>
      ) : null}
      {loading ? <p role="status">正在读取趋势…</p> : null}
      {page ? (
        <>
          <MetricChart
            series={{
              ...series,
              points: view === "points" ? (page.items as Point[]) : [],
              buckets: view === "buckets" ? (page.items as Bucket[]) : [],
            }}
            daily={view === "points"}
            hours={hours}
            onRecord={onRecord}
            onBucket={drill}
          />
          <details open={!!day}>
            <summary>文字详情 · 共 {page.total} 项</summary>
            <div className="bm-record-list">
              {page.items.map((item) => {
                const point = "record_id" in item;
                return (
                  <button
                    type="button"
                    className="bm-record-row"
                    key={point ? item.record_id : item.date}
                    onClick={() =>
                      point ? onRecord(item.record_id) : drill(item.date)
                    }
                  >
                    <span>{point ? time(item.starts_at) : item.date}</span>
                    <span>
                      {number(item.value)}
                      {item.secondary_value != null
                        ? ` / ${number(item.secondary_value)}`
                        : ""}{" "}
                      {series.unit}
                      {!point ? ` · ${item.count} 条记录` : ""}
                    </span>
                  </button>
                );
              })}
            </div>
          </details>
          {cursors.length > 1 || page.next_cursor ? (
            <div className="bm-pagination">
              <button
                type="button"
                className="control"
                disabled={loading || cursors.length === 1}
                onClick={() => setCursors((v) => v.slice(0, -1))}
              >
                上一页
              </button>
              <span>第 {cursors.length} 页</span>
              <button
                type="button"
                className="control"
                disabled={loading || !page.next_cursor}
                onClick={() => setCursors((v) => [...v, page.next_cursor!])}
              >
                下一页
              </button>
            </div>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
