import { EmptyState } from "../../components/EmptyState";
import { useId, useState } from "react";
import type { ChartSeries } from "../../api/bodyMetricApi";
import { number, time } from "./bodyMetricPresentation";
export function MetricChart({
  series,
  daily,
  hours = 24,
  onRecord,
  onBucket,
}: {
  series: ChartSeries;
  daily: boolean;
  hours?: number;
  onRecord: (id: string) => void;
  onBucket?: (date: string) => void;
}) {
  const [active, setActive] = useState<number | null>(null);
  const plotId = useId();
  let values = daily
    ? series.points.map((p) => ({
        x: new Date(p.starts_at).getTime(),
        value: p.value,
        secondary: p.secondary_value,
        minimum: Math.min(p.value, p.secondary_value ?? p.value),
        maximum: p.value,
        id: p.record_id,
        label: time(p.starts_at),
      }))
    : series.buckets.map((p) => ({
        x: new Date(p.date).getTime(),
        value: p.value,
        secondary: p.secondary_value,
        minimum: Math.min(p.minimum, p.secondary_value ?? p.minimum),
        maximum: p.maximum,
        id: p.date,
        label: p.date.slice(5),
      }));
  if (daily && hours < 24 && values.length) {
    const end = values[values.length - 1].x;
    values = values.filter((v) => v.x >= end - hours * 3600000);
  }
  if (!values.length) return <EmptyState layout="inline" title="该时间范围暂无数据" />;
  // Bucket extrema describe individual records; the plotted daily total can be larger.
  const low =
    series.aggregation === "sum"
      ? 0
      : Math.min(
          ...values.map((p) =>
            Math.min(p.minimum, p.value, p.secondary ?? p.value),
          ),
        );
  const high = Math.max(
    ...values.map((p) => Math.max(p.maximum, p.value, p.secondary ?? p.value)),
  );
  const span = Math.max(high - low, 1);
  const min = low === 0 ? 0 : low - span * 0.15;
  const max = high + span * 0.15;
  const left = 60,
    right = 650,
    top = 20,
    bottom = 202;
  const start = values[0].x,
    end = values[values.length - 1].x;
  const x = (v: (typeof values)[number]) =>
    start === end
      ? (left + right) / 2
      : left + ((v.x - start) / (end - start)) * (right - left);
  const y = (v: number) => bottom - ((v - min) / (max - min)) * (bottom - top);
  const paths = values.reduce<string[]>((arr, p, i) => {
    if (!i || (daily && p.x - values[i - 1].x > 3600000))
      arr.push(`M ${x(p)} ${y(p.value)}`);
    else arr[arr.length - 1] += ` L ${x(p)} ${y(p.value)}`;
    return arr;
  }, []);
  const secondaryPath = values
    .filter((p) => p.secondary != null)
    .map((p, i) => `${i ? "L" : "M"} ${x(p)} ${y(p.secondary!)}`)
    .join(" ");
  const chosen = active === null ? null : values[active];
  const focusIndex = Math.min(active ?? 0, values.length - 1);
  return (
    <div className="bm-chart">
      <svg
        viewBox="0 0 680 242"
        role="group"
        aria-label={`${series.label}趋势，${values.length}个数据点`}
        aria-describedby={`${plotId}-help`}
      >
        <desc id={`${plotId}-help`}>
          使用方向键浏览数据点，Home 或 End 跳至首末项，Enter
          或空格查看记录，Tab 离开图表。
        </desc>
        <defs>
          <clipPath id={plotId}>
            <rect
              x={left - 14}
              y={top - 6}
              width={right - left + 28}
              height={bottom - top + 12}
            />
          </clipPath>
        </defs>
        {[0, 1, 2, 3].map((i) => {
          const v = min + ((max - min) * i) / 3;
          return (
            <g key={i}>
              <line
                x1={left}
                y1={y(v)}
                x2={right}
                y2={y(v)}
                className="bm-gridline"
              />
              <text x={left - 10} y={y(v) + 4} textAnchor="end">
                {number(v)}
              </text>
            </g>
          );
        })}
        <g clipPath={`url(#${plotId})`}>
          {series.aggregation === "sum"
            ? values.map((p, i) => (
                <rect
                  key={i}
                  x={x(p) - Math.min(12, 200 / values.length)}
                  y={y(p.value)}
                  width={Math.min(24, 400 / values.length)}
                  height={bottom - y(p.value)}
                  rx="3"
                  className="bm-bar"
                />
              ))
            : paths.map((path, i) => (
                <path key={i} d={path} fill="none" className="bm-line" />
              ))}
          {secondaryPath ? (
            <path
              d={secondaryPath}
              fill="none"
              className="bm-line bm-line-secondary"
            />
          ) : null}
          {values.map((p, i) => (
            <circle
              key={i}
              cx={x(p)}
              cy={y(p.value)}
              r={active === i ? 8 : 6}
              className="bm-point"
              tabIndex={focusIndex === i ? 0 : -1}
              role="button"
              aria-label={`${p.label} ${number(p.value)} ${series.unit}，查看记录`}
              onMouseEnter={() => setActive(i)}
              onFocus={() => setActive(i)}
              onClick={() => (daily ? onRecord(p.id) : onBucket?.(p.id))}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  daily ? onRecord(p.id) : onBucket?.(p.id);
                  return;
                }
                const targetIndex =
                  e.key === "Home"
                    ? 0
                    : e.key === "End"
                      ? values.length - 1
                      : e.key === "ArrowRight" || e.key === "ArrowDown"
                        ? Math.min(i + 1, values.length - 1)
                        : e.key === "ArrowLeft" || e.key === "ArrowUp"
                          ? Math.max(i - 1, 0)
                          : null;
                if (targetIndex !== null) {
                  e.preventDefault();
                  e.currentTarget.ownerSVGElement
                    ?.querySelectorAll<SVGCircleElement>(".bm-point")
                    [targetIndex]?.focus();
                }
              }}
            >
              <title>{`${p.label} · ${number(p.value)}${p.secondary != null ? `/${number(p.secondary)}` : ""} ${series.unit}`}</title>
            </circle>
          ))}
        </g>
        {[0, Math.floor((values.length - 1) / 2), values.length - 1]
          .filter((v, i, a) => a.indexOf(v) === i)
          .map((i) => (
            <text
              key={i}
              x={x(values[i])}
              y="230"
              textAnchor={
                i === 0 ? "start" : i === values.length - 1 ? "end" : "middle"
              }
            >
              {values[i].label}
            </text>
          ))}
      </svg>
      {secondaryPath ? (
        <p className="bm-chart-legend">
          <span>
            <svg viewBox="0 0 30 8" aria-hidden="true">
              <path d="M 0 4 L 30 4" className="bm-line" />
            </svg>
            收缩压
          </span>
          <span>
            <svg viewBox="0 0 30 8" aria-hidden="true">
              <path d="M 0 4 L 30 4" className="bm-line bm-line-secondary" />
            </svg>
            舒张压
          </span>
        </p>
      ) : null}
      <p className="bm-chart-caption" aria-live="polite">
        {chosen
          ? `${chosen.label} · ${number(chosen.value)}${chosen.secondary != null ? "/" + number(chosen.secondary) : ""} ${series.unit}`
          : daily
            ? "点按数据点查看记录"
            : "点按日期查看对应记录列表"}{" "}
        · {series.source}
        {series.method ? ` · ${series.method}` : ""}
      </p>
    </div>
  );
}
