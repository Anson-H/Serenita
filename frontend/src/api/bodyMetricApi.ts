import { request } from "./request";
export type Food = {
  food_id: string;
  name: string;
  amount: number | null;
  amount_unit: string;
  energy: number | null;
  carbohydrate: number | null;
  protein: number | null;
  fat: number | null;
  basis: string;
};
export type Stage = {
  stage_id: string;
  stage: string;
  starts_at: string;
  ends_at: string;
  original_stage?: string;
};
export type MetricData = {
  value?: number;
  unit?: string;
  secondary_value?: number | null;
  pulse?: number | null;
  method?: string;
  context?: string;
  basis?: string;
  meal_type?: string | null;
  estimated?: boolean;
  foods?: Food[];
  energy?: number | null;
  carbohydrate?: number | null;
  protein?: number | null;
  fat?: number | null;
  score?: number | null;
  score_max?: number | null;
  score_basis?: string;
  score_stale?: boolean;
  duration_minutes?: number | null;
  stages?: Stage[];
  activity?: string;
  distance_km?: number | null;
};
export type BodyInput = {
  kind: "measurement" | "meal" | "sleep" | "workout";
  metric: string;
  starts_at: string;
  ends_at: string | null;
  timezone: string;
  precision: "instant" | "interval" | "day";
  source: string;
  device: string;
  origin: "manual" | "apple_health" | "standard" | "image" | "demo";
  external_id?: string | null;
  notes: string;
  data: MetricData;
};
export type BodyRecord = BodyInput & {
  record_id: string;
  member_id: string;
  edited: boolean;
  import_managed: boolean;
  created_at: string;
  updated_at: string;
  files?: {
    file_id: string;
    filename: string;
    mime_type: string;
    sha256: string;
  }[];
};
export type MetricDefinition = {
  metric: string;
  label: string;
  unit: string;
  category: string;
  aggregation: string;
};
export type Catalog = {
  metrics: MetricDefinition[];
  meal_types: Record<string, string>;
  stages: Record<string, string>;
};
export type Point = {
  value: number;
  secondary_value: number | null;
  starts_at: string;
  ends_at: string | null;
  date: string;
  record_id: string;
};
export type Bucket = {
  date: string;
  value: number;
  secondary_value: number | null;
  minimum: number;
  maximum: number;
  count: number;
};
export type Series = {
  series_id: string;
  metric: string;
  label: string;
  unit: string;
  source: string;
  device: string;
  method: string;
  aggregation: string;
  latest: number;
  minimum: number;
  maximum: number;
  mean: number;
  secondary_mean: number | null;
  total: number | null;
  daily_mean: number;
  count: number;
  days: number;
  omitted_overlaps: number;
  allocated_intervals: number;
  score_max: number | null;
  preview: { date: string; value: number }[];
};
export type ChartSeries = Series & { buckets: Bucket[]; points: Point[] };
export type SeriesPage<T> = {
  items: T[];
  total: number;
  next_cursor: string | null;
};
export type Statistics = {
  series: Series[];
  sources: string[];
  total_records: number;
  coverage_dates: { first: string | null; last: string | null; recorded_days: number };
  missing_values: Record<string, number>;
  coverage_from: string | null;
  coverage_to: string | null;
  excluded_stale_scores: number;
};
export type ImportJob = {
  import_id: string;
  filename: string;
  state: "preview" | "running" | "complete" | "failed";
  valid_count: number;
  input_count: number;
  new_count: number;
  duplicates: number;
  inserted: number;
  issues: { row: number; message: string }[];
  unsupported: Record<string, number>;
  date_from: string | null;
  date_to: string | null;
  categories: string[];
  error: string | null;
  created_at: string;
};
export type Filters = {
  after?: string;
  before?: string;
  category?: string;
  source?: string;
  offset?: number;
  limit?: number;
  timezone?: string;
};
export const bodyBase = (member: string) =>
  `/members/${encodeURIComponent(member)}/body-metrics`;
const params = (filters: Record<string, string | number | undefined>) =>
  new URLSearchParams(
    Object.entries(filters)
      .filter(([, v]) => v !== undefined && v !== "")
      .map(([k, v]) => [k, String(v)]),
  ).toString();
export const getCatalog = (m: string, signal?: AbortSignal) =>
  request<Catalog>(`${bodyBase(m)}/catalog`, { signal });
export const getStatistics = (
  m: string,
  f: Filters = {},
  signal?: AbortSignal,
) => request<Statistics>(`${bodyBase(m)}/statistics?${params(f)}`, { signal });
export const getRecords = (m: string, f: Filters = {}, signal?: AbortSignal) =>
  request<{ items: BodyRecord[]; total: number; next_offset: number | null }>(
    `${bodyBase(m)}/records?${params(f)}`,
    { signal },
  );
export const getRecord = (m: string, id: string, signal?: AbortSignal) =>
  request<BodyRecord>(`${bodyBase(m)}/records/${id}`, { signal });
export const saveRecord = (m: string, value: BodyInput, id?: string) =>
  request<BodyRecord>(`${bodyBase(m)}/records${id ? "/" + id : ""}`, {
    method: id ? "PATCH" : "POST",
    body: JSON.stringify(
      id
        ? {
            metric: value.metric,
            starts_at: value.starts_at,
            ends_at: value.ends_at,
            timezone: value.timezone,
            precision: value.precision,
            notes: value.notes,
            data: value.data,
          }
        : value,
    ),
  });
export const deleteRecord = (m: string, id: string) =>
  request<{ deleted: boolean }>(`${bodyBase(m)}/records/${id}`, {
    method: "DELETE",
  });
export const getImports = (m: string, cursor?: string, signal?: AbortSignal) =>
  request<{ items: ImportJob[]; next_cursor: string | null; has_more: boolean }>(`${bodyBase(m)}/imports?${new URLSearchParams({ limit: "24", ...(cursor ? { cursor } : {}) })}`, { signal });
export const getImport = (m: string, id: string) =>
  request<ImportJob>(`${bodyBase(m)}/imports/${id}`);
export const previewImport = (m: string, file: File, requestId: string) => {
  const data = new FormData();
  data.append("file", file);
  return request<ImportJob>(
    `${bodyBase(m)}/imports/preview?timezone=${encodeURIComponent(Intl.DateTimeFormat().resolvedOptions().timeZone)}`,
    { method: "POST", headers: { "Idempotency-Key": requestId }, body: data },
  );
};
export const commitImport = (
  m: string,
  id: string,
  selection: { after?: string; before?: string; categories?: string[] } = {},
) =>
  request<ImportJob>(`${bodyBase(m)}/imports/${id}/commit`, {
    method: "POST",
    body: JSON.stringify(selection),
  });
export const deleteImport = (m: string, id: string) =>
  request<{
    deleted: boolean;
    records_deleted: number;
    records_retained: number;
  }>(`${bodyBase(m)}/imports/${id}`, { method: "DELETE" });
export const attachFoodFile = (m: string, id: string, file: File) => {
  const data = new FormData();
  data.append("file", file);
  return request<BodyRecord>(`${bodyBase(m)}/records/${id}/files`, {
    method: "POST",
    body: data,
  });
};
export const removeFoodFile = (m: string, id: string, fileId: string) =>
  request<BodyRecord>(`${bodyBase(m)}/records/${id}/files/${fileId}`, {
    method: "DELETE",
  });

export function getSeriesData<T extends Point | Bucket>(
  m: string,
  id: string,
  view: "points" | "buckets",
  f: Filters,
  cursor?: string,
  signal?: AbortSignal,
) {
  return request<SeriesPage<T>>(
    `${bodyBase(m)}/statistics/series/${encodeURIComponent(id)}?${params({ ...f, view, cursor, limit: 100 })}`,
    { signal },
  );
}
