import { useState } from "react";
import { createRoot } from "react-dom/client";
import type { ChartSeries } from "../../src/api/bodyMetricApi";
import { MetricChart } from "../../src/features/bodyMetrics/MetricChart";
import "../../src/styles/index.css";

const series: ChartSeries = {
  series_id: "test",
  metric: "energy",
  source: "测试",
  device: "",
  method: "",
  unit: "kcal",
  label: "摄入能量",
  aggregation: "sum",
  score_max: null,
  latest: 199,
  minimum: 100,
  maximum: 199,
  mean: 149.5,
  secondary_mean: null,
  total: 14950,
  daily_mean: 149.5,
  count: 100,
  days: 100,
  omitted_overlaps: 0,
  allocated_intervals: 0,
  preview: [],
  points: [],
  buckets: Array.from({ length: 100 }, (_, index) => ({
    date: new Date(Date.UTC(2026, 0, index + 1)).toISOString().slice(0, 10),
    value: 100 + index,
    minimum: 100 + index,
    maximum: 100 + index,
    secondary_value: null,
    count: 1,
  })),
};

function Fixture() {
  const [selected, setSelected] = useState("");
  return (
    <>
      <button>图表之前</button>
      <MetricChart
        series={series}
        daily={false}
        onRecord={() => {
          throw new Error("汇总不能直接编辑记录");
        }}
        onBucket={setSelected}
      />
      <button>图表之后</button>
      <output aria-label="已选日期">{selected}</output>
    </>
  );
}
createRoot(document.getElementById("root")!).render(<Fixture />);
