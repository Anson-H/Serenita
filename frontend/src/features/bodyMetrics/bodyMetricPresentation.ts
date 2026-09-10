import type { BodyRecord, Catalog, BodyInput } from "../../api/bodyMetricApi";
export const CATEGORIES = [
  ["body", "体格", "体"],
  ["nutrition", "饮食", "食"],
  ["sleep", "睡眠", "眠"],
  ["heart", "心率", "心"],
  ["blood_pressure", "血压", "压"],
  ["blood_oxygen", "血氧", "氧"],
  ["blood_glucose", "血糖", "糖"],
  ["steps", "步数", "步"],
  ["workouts", "运动记录", "动"],
  ["active_energy", "活动能量", "能"],
  ["stand_hours", "站立小时数", "立"],
  ["exercise_minutes", "锻炼时长", "练"],
  ["temperature", "体温", "温"],
] as const;
export const number = (n: number | null | undefined) =>
  n == null
    ? "—"
    : new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 }).format(n);
export const dateOnly = (d = new Date()) =>
  new Intl.DateTimeFormat("sv-SE", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(d);
export const time = (s: string) =>
  new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(s));
export function recordLabel(r: BodyInput, c: Catalog) {
  return r.kind === "measurement"
    ? c.metrics.find((m) => m.metric === r.metric)?.label || r.metric
    : r.kind === "meal"
      ? c.meal_types[r.data.meal_type || ""] || "待补充分餐"
      : r.kind === "sleep"
        ? "睡眠记录"
        : r.data.activity || "运动";
}
export function recordValue(r: BodyRecord) {
  const d = r.data;
  return r.kind === "measurement"
    ? `${number(d.value)}${d.secondary_value != null ? "/" + number(d.secondary_value) : ""} ${d.unit}`
    : r.kind === "meal"
      ? `${number(d.energy)} kcal`
      : `${number(d.duration_minutes)} min`;
}
export function newRecord(
  category: string,
  c: Catalog,
  date: string,
): BodyInput {
  const kind =
    category === "nutrition"
      ? "meal"
      : category === "sleep"
        ? "sleep"
        : category === "workouts"
          ? "workout"
          : "measurement";
  const metric = c.metrics.find((m) => m.category === category) || c.metrics[0];
  const data =
    kind === "measurement"
      ? {
          value: 0,
          unit: metric.unit,
          ...(metric.metric === "blood_pressure" ? { secondary_value: 0 } : {}),
        }
      : kind === "meal"
        ? { meal_type: "breakfast", foods: [], estimated: false }
        : kind === "sleep"
          ? { stages: [] }
          : { activity: "步行", duration_minutes: 30 };
  return {
    kind,
    metric: kind === "measurement" ? metric.metric : "",
    starts_at: new Date(`${date}T08:00:00`).toISOString(),
    ends_at:
      kind === "sleep"
        ? new Date(`${date}T09:00:00`).toISOString()
        : kind === "workout"
          ? new Date(`${date}T08:30:00`).toISOString()
          : null,
    precision: kind === "sleep" || kind === "workout" ? "interval" : "instant",
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    source: "手工记录",
    device: "",
    origin: "manual",
    notes: "",
    data,
  };
}
export function range(date: string, period: string, customEnd: string) {
  const a = new Date(`${date}T12:00:00Z`),
    b = new Date(a);
  if (period === "week") {
    a.setUTCDate(a.getUTCDate() - ((a.getUTCDay() + 6) % 7));
    b.setTime(a.getTime());
    b.setUTCDate(b.getUTCDate() + 6);
  }
  if (period === "month") {
    a.setUTCDate(1);
    b.setUTCMonth(b.getUTCMonth() + 1, 0);
  }
  if (period === "year") {
    a.setUTCMonth(0, 1);
    b.setUTCMonth(11, 31);
  }
  return {
    after: a.toISOString().slice(0, 10),
    before: period === "custom" ? customEnd : b.toISOString().slice(0, 10),
  };
}
