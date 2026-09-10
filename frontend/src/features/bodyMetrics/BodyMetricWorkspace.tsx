import { useBodyMetricFilters } from "./useBodyMetricFilters";
import { useBodyMetricData } from "./useBodyMetricData";
import { useBodyRecordNavigation } from "./useBodyRecordNavigation";
import { navigationLabels } from "../../components/navigationLabels";
import { EmptyState } from "../../components/EmptyState";
import {
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type { Member } from "../../api/memberApi";
import {
  type BodyRecord,
  type Catalog,
  type Series,
} from "../../api/bodyMetricApi";
import {
  bodyMetricPath,
  bodyMetricCategory,
  healthPathForMember,
  medicalLogPath,
  medicationPath,
  type RoutePath,
} from "../../app/routes";
import { WorkspaceToolbar } from "../../components/WorkspaceToolbar";
import { DateField } from "../../components/DateField";
import { HealthMemberOverview } from "../members/HealthMemberOverview";
import { MemberInformationPanel } from "../members/MemberInformationPanel";
import { BodyRecordEditor } from "./BodyRecordEditor";
import { BodyImportDialog } from "./BodyImportDialog";
import { BodySeriesChart } from "./BodySeriesChart";
import { SelectPopover } from "../../components/SelectPopover";
import {
  CATEGORIES,
  dateOnly,
  number,
  recordLabel,
  recordValue,
  newRecord,
  time,
} from "./bodyMetricPresentation";
import "../../styles/body-metrics.css";
function mainMetric(category: string) {
  return (
    (
      {
        body: "weight",
        nutrition: "energy",
        sleep: "sleep_minutes",
        heart: "heart_rate",
        workouts: "workout_minutes",
      } as Record<string, string>
    )[category] || category
  );
}
function categoryOf(s: Series, c: Catalog) {
  return (
    c.metrics.find((m) => m.metric === s.metric)?.category ||
    (
      {
        energy: "nutrition",
        carbohydrate: "nutrition",
        protein: "nutrition",
        fat: "nutrition",
        sleep_minutes: "sleep",
        sleep_score: "sleep",
        workout_minutes: "workouts",
      } as Record<string, string>
    )[s.metric]
  );
}
function valueOf(s?: Series) {
  if (!s) return "—";
  if (s.metric === "blood_pressure")
    return `${number(s.mean)}/${number(s.secondary_mean)}`;
  return number(
    s.aggregation === "sum"
      ? s.total
      : s.aggregation === "range"
        ? s.latest
        : s.aggregation === "latest"
          ? s.latest
          : s.mean,
  );
}
export function BodyMetricWorkspace({
  member,
  route,
  navigate,
  sidebarToggle,
  onRecognize,
  onAsk,
}: {
  member: Member;
  route: RoutePath;
  navigate: (r: RoutePath) => void;
  sidebarToggle: ReactNode;
  onRecognize: (files: File[]) => Promise<void>;
  onAsk: (text: string) => Promise<void>;
}) {
  const category = bodyMetricCategory(route);
  const filters = useBodyMetricFilters(member.member_id, category);
  const { offset, setOffset, date, setDate, customEnd, setCustomEnd, period, setPeriod, source, setSource, metric, setMetric, hours, setHours, timezone, dates, shift } = filters;
  const { catalog, statistics, records, total, refresh, error, setError, loading, statisticsError, recordsError, recordsLoading, refreshData } = useBodyMetricData(member.member_id, category, filters);
  const { edit, setEdit, openRecord } = useBodyRecordNavigation(member.member_id, route, setError);
  const [importing, setImporting] = useState(false),
    [information, setInformation] = useState(false),
    [recognizing, setRecognizing] = useState(false);
  const [recognitionFiles, setRecognitionFiles] = useState<File[]>([]);
  const recognitionEpoch = useRef(0);
  useEffect(() => {
    setRecognitionFiles([]);
    setRecognizing(false);
    return () => {
      recognitionEpoch.current++;
    };
  }, [member.member_id]);
  async function recognize(files: File[]) {
    const epoch = recognitionEpoch.current;
    setRecognitionFiles(files);
    setRecognizing(true);
    setError("");
    try {
      await onRecognize(files);
      if (epoch === recognitionEpoch.current) setRecognitionFiles([]);
    } catch (cause) {
      if (epoch === recognitionEpoch.current)
        setError(
          cause instanceof Error ? cause.message : "识别任务发送失败，请重试。",
        );
    } finally {
      if (epoch === recognitionEpoch.current) setRecognizing(false);
    }
  }
  const panel = useRef<HTMLElement | null>(null);
  const photo = useRef<HTMLInputElement>(null);
  useEffect(() => { setInformation(false); }, [category, member.member_id]);
  const filtered = catalog
    ? statistics.series
        .filter((s) => categoryOf(s, catalog) === category)
        .sort(
          (a, b) =>
            catalog.metrics.findIndex((m) => m.metric === a.metric) -
            catalog.metrics.findIndex((m) => m.metric === b.metric),
        )
    : [];
  const selected =
    filtered.find((s) => s.series_id === metric) ||
    filtered.find((s) => s.metric === mainMetric(category || "body")) ||
    filtered[0];
  const title = CATEGORIES.find((c) => c[0] === category)?.[1] || "身体指标";
  const overview = (
    <div className="bm-overview scroll-content">
      <div className="bm-overview-heading">
        <div>
          <h2>身体指标</h2>
          <p>
            {statistics.coverage_to
              ? `数据覆盖至 ${dateOnly(new Date(statistics.coverage_to))}`
              : "记录身体与生活的变化"}
          </p>
        </div>
        {member.can_edit ? (
          <button
            type="button"
            className="control"
            onClick={() => setImporting(true)}
          >
            {navigationLabels.importBody}
          </button>
        ) : null}
      </div>
      {member.member_name === "身体指标演示" ? (
        <p className="bm-demo">虚构演示数据 · 可编辑体验</p>
      ) : null}
      <div className="bm-card-grid">
        {CATEGORIES.map(([key, label, symbol]) => {
          const s = statistics.series.find((s) => s.metric === mainMetric(key));
          const values = s?.preview || [];
          const max = Math.max(...values.map((v) => v.value), 1);
          return (
            <button
              type="button"
              className="bm-summary-card"
              data-category={key}
              data-current={category === key || undefined}
              aria-label={`查看${label}`}
              aria-current={category === key ? "page" : undefined}
              key={key}
              onClick={() => navigate(bodyMetricPath(member.member_id, key))}
            >
              <span className="bm-card-title">
                <span className="bm-symbol">{symbol}</span>
                {label}
              </span>
              <span className="bm-card-value">
                {loading && !s ? "…" : valueOf(s)}{" "}
                <small>{s?.unit || ""}</small>
              </span>
              <span className="bm-spark" aria-hidden="true">
                {values.map((v, i) => (
                  <i
                    key={i}
                    style={{ height: `${Math.max(5, (v.value / max) * 100)}%` }}
                  />
                ))}
              </span>
              <span className="bm-card-description">
                {s
                  ? `${s.aggregation === "sum" ? "期间累计" : s.aggregation === "latest" ? "最近记录" : s.aggregation === "range" ? "最近记录" : "期间均值"} · ${s.days} 天有记录`
                  : "暂无记录"}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
  return (
    <section
      className="reports-workspace bm-workspace"
      data-detail-open={category || information ? "true" : "false"}
    >
      <div className="report-browser-layout">
        <div className="report-library-column">
          <WorkspaceToolbar
            title={navigationLabels.health}
            className="reports-list-toolbar"
            leading={sidebarToggle}
            showBack={false}
          />
          <HealthMemberOverview
            member={member}
            informationOpen={information}
            onOpenInformation={() => setInformation(true)}
            section="body-metrics"
            onSelectBodyMetrics={() =>
              navigate(bodyMetricPath(member.member_id))
            }
            onSelectReports={() =>
              navigate(healthPathForMember(member.member_id))
            }
            onSelectMedicalLogs={() =>
              navigate(medicalLogPath(member.member_id))
            }
            onSelectMedications={() =>
              navigate(medicationPath(member.member_id))
            }
            reportArchive={overview}
          />
        </div>
        <div className="report-detail-column">
          {information ? (
            <MemberInformationPanel
              member={member}
              panelRef={panel}
              onClose={() => setInformation(false)}
            />
          ) : (
            <>
              <WorkspaceToolbar
                className="reports-detail-toolbar"
                title={title}
                onBack={() => navigate(bodyMetricPath(member.member_id))}
                trailing={
                  category && member.can_edit && catalog ? (
                    <button
                      type="button"
                      className="control"
                      onClick={() =>
                        setEdit({ input: newRecord(category, catalog, date) })
                      }
                    >
                      ＋ {navigationLabels.createRecord}
                    </button>
                  ) : undefined
                }
              />
              <div className="bm-detail-scroll scroll-content content-column">
                <div
                  className="bm-period-tabs"
                  role="group"
                  aria-label="时间范围"
                >
                  {[
                    ["day", "日"],
                    ["week", "周"],
                    ["month", "月"],
                    ["year", "年"],
                    ["custom", "自定义"],
                  ].map(([key, label]) => (
                    <button
                      className="control"
                      type="button"
                      aria-pressed={period === key}
                      key={key}
                      onClick={() => {
                        setPeriod(key);
                        setOffset(0);
                      }}
                    >
                      {label}
                    </button>
                  ))}
                </div>
                <div className="bm-date-navigation">
                  <button
                    type="button"
                    className="control"
                    aria-label="上一时间范围"
                    onClick={() => shift(-1)}
                  >
                    ‹
                  </button>
                  <DateField
                    compact
                    required
                    label="选择日期"
                    value={date}
                    onChange={(v) => {
                      if (v) {
                        setDate(v);
                        setOffset(0);
                      }
                    }}
                  />
                  {period === "custom" ? (
                    <DateField
                      compact
                      required
                      label="结束日期"
                      value={customEnd}
                      onChange={(v) => {
                        if (v) {
                          setCustomEnd(v);
                          setOffset(0);
                        }
                      }}
                    />
                  ) : null}
                  <button
                    type="button"
                    className="control"
                    aria-label="下一时间范围"
                    onClick={() => shift(1)}
                  >
                    ›
                  </button>
                </div>
                <p className="bm-date-caption">
                  {dates.after}{" "}
                  {dates.before !== dates.after ? `— ${dates.before}` : ""}
                </p>
                {error ? (
                  <div className="bm-error" role="alert">
                    {error}
                    <button
                      className="control"
                      type="button"
                      onClick={refreshData}
                    >
                      重新读取
                    </button>
                  </div>
                ) : null}
                {!category ? (
                  <div className="bm-welcome">
                    <span className="bm-welcome-mark">◷</span>
                    <h2>让每一次记录，都有迹可循</h2>
                    <p>
                      从左侧选择身体指标，查看身体、饮食、睡眠与活动的变化。
                    </p>
                    <div className="bm-stat-grid">
                      <div>
                        <strong>{number(statistics.total_records)}</strong>
                        <span>期间记录</span>
                      </div>
                      <div>
                        <strong>{statistics.sources.length}</strong>
                        <span>数据来源</span>
                      </div>
                    </div>
                    <p className="bm-muted">
                      每条记录均可查看日期、时间和来源。
                    </p>
                    {member.can_edit ? (
                      <button
                        className="control control--primary"
                        type="button"
                        onClick={() => setImporting(true)}
                      >
                        {navigationLabels.importBody}
                      </button>
                    ) : null}
                  </div>
                ) : (
                  <>
                    {statisticsError ? (
                      <p role="alert">
                        统计读取失败：{statisticsError}{" "}
                        <button
                          className="control"
                          type="button"
                          onClick={refreshData}
                        >
                          重试
                        </button>
                      </p>
                    ) : null}
                    <div className="bm-filters">
                      <div className="bm-field">
                        <span>数据来源</span>
                        <SelectPopover
                          menuWidth="trigger"
                          menuAlign="start"
                          ariaLabel="数据来源"
                          interactionOwner="self"
                          value={source}
                          onChange={(v) => {
                            setSource(v);
                            setOffset(0);
                          }}
                          options={[
                            { value: "", label: "全部来源（分别统计）" },
                            ...statistics.sources.map((v) => ({
                              value: v,
                              label: v,
                            })),
                          ]}
                        />
                      </div>
                      {filtered.length > 1 ? (
                        <div className="bm-field">
                          <span>指标与统计口径</span>
                          <SelectPopover
                            menuWidth="trigger"
                            menuAlign="start"
                            ariaLabel="指标与统计口径"
                            interactionOwner="self"
                            value={selected?.series_id || ""}
                            onChange={setMetric}
                            options={filtered.map((s) => ({
                              value: s.series_id,
                              label: `${s.label}${s.method ? ` · ${s.method}` : ""} · ${s.unit}${s.score_max ? ` / ${s.score_max} 满分` : ""} · ${s.source}${s.device ? ` · ${s.device}` : ""}`,
                            }))}
                          />
                        </div>
                      ) : null}
                    </div>
                    {statistics.excluded_stale_scores ? (
                      <p className="bm-muted">
                        有 {statistics.excluded_stale_scores}{" "}
                        条过期睡眠评分已退出当前统计，可在记录详情中追溯。
                      </p>
                    ) : null}
                    {selected ? (
                      <>
                        <section className="bm-hero">
                          <span>
                            {selected.label}
                            {period === "day" ? " · 当日" : " · 期间"}
                          </span>
                          <div>
                            <strong>{valueOf(selected)}</strong>
                            <span>{selected.unit}</span>
                          </div>
                          <p>
                            {selected.aggregation === "range"
                              ? `范围 ${number(selected.minimum)}–${number(selected.maximum)} ${selected.unit}`
                              : selected.aggregation === "sum"
                                ? `有记录日均 ${number(selected.daily_mean)} ${selected.unit}`
                                : `${selected.count} 条记录 · ${selected.source}`}
                          </p>
                        </section>
                        <div className="bm-section-heading">
                          <h2>{period === "day" ? "日内记录" : "变化趋势"}</h2>
                          {category === "blood_glucose" && period === "day" ? (
                            <div className="bm-hour-tabs">
                              {[3, 6, 12, 24].map((h) => (
                                <button
                                  className="control"
                                  key={h}
                                  type="button"
                                  aria-pressed={hours === h}
                                  onClick={() => setHours(h)}
                                >
                                  {h}小时
                                </button>
                              ))}
                            </div>
                          ) : null}
                        </div>
                        <BodySeriesChart
                          key={`${member.member_id}-${selected.series_id}-${period}-${dates.after}-${dates.before}-${source}`}
                          memberId={member.member_id}
                          revision={refresh}
                          series={selected}
                          filters={{ ...dates, source, timezone }}
                          daily={period === "day"}
                          hours={hours}
                          onRecord={(id) => void openRecord(id)}
                        />
                        {selected.allocated_intervals ? (
                          <p className="bm-muted">
                            跨日累计记录按区间时长分摊至各日；汇总值为估算，原始区间与数值可在明细中查看。
                          </p>
                        ) : null}
                        {selected.omitted_overlaps ? (
                          <p className="bm-muted">
                            有 {selected.omitted_overlaps}{" "}
                            条重叠或汇总明细记录未重复计入总量，可在记录中核对。
                          </p>
                        ) : null}
                      </>
                    ) : (
                      <EmptyState layout="inline" title={loading
                          ? "正在读取…"
                          : "所选时间范围没有记录，可添加记录或导入文件。"} />
                    )}
                    {category === "body" || category === "heart" ? (
                      <div className="bm-metric-values">
                        {filtered.map((s) => (
                          <button
                            type="button"
                            className="bm-metric-value"
                            key={s.series_id}
                            onClick={() => setMetric(s.series_id)}
                          >
                            <span>
                              {s.label}
                              {s.method ? ` · ${s.method}` : ""}
                              <small>{s.source}</small>
                            </span>
                            <strong>
                              {valueOf(s)} <small>{s.unit}</small>
                            </strong>
                          </button>
                        ))}
                      </div>
                    ) : null}
                    {category === "nutrition" ? (
                      <>
                        <div className="bm-stat-grid">
                          {["carbohydrate", "protein", "fat"].map((m) => {
                            const s = filtered.find(
                              (s) =>
                                s.metric === m &&
                                s.source === selected?.source &&
                                s.device === selected?.device &&
                                s.method === selected?.method,
                            );
                            return (
                              <div key={m}>
                                <strong>
                                  {number(s?.total)} <small>g</small>
                                </strong>
                                <span>
                                  {
                                    (
                                      {
                                        carbohydrate: "碳水",
                                        protein: "蛋白质",
                                        fat: "脂肪",
                                      } as Record<string, string>
                                    )[m]
                                  }
                                </span>
                              </div>
                            );
                          })}
                        </div>
                        <p className="bm-muted">
                          {selected?.source || "所选来源"}的食物合计 ·
                          照片估算会保留依据
                        </p>
                        <input
                          ref={photo}
                          type="file"
                          accept="image/png,image/jpeg,image/webp"
                          multiple
                          hidden
                          onChange={(e) => {
                            const files = Array.from(
                              e.currentTarget.files || [],
                            );
                            e.currentTarget.value = "";
                            if (files.length) void recognize(files);
                          }}
                        />
                        {member.can_edit ? (
                          <button
                            className="control control--primary bm-recognize"
                            type="button"
                            disabled={recognizing}
                            onClick={() => photo.current?.click()}
                          >
                            {recognizing
                              ? "正在上传图片…"
                              : "拍照 / 图片识别饮食"}
                          </button>
                        ) : null}
                        {recognitionFiles.length &&
                        !recognizing &&
                        member.can_edit ? (
                          <div className="bm-pagination">
                            <button
                              className="control"
                              type="button"
                              onClick={() => void recognize(recognitionFiles)}
                            >
                              重试识别
                            </button>
                            <button
                              className="control"
                              type="button"
                              onClick={() => setRecognitionFiles([])}
                            >
                              取消识别
                            </button>
                          </div>
                        ) : null}
                      </>
                    ) : null}
                    {category === "sleep" && catalog
                      ? records
                          .filter((r) => r.kind === "sleep")
                          .slice(0, 7)
                          .map((r) => (
                            <SleepTimeline
                              key={r.record_id}
                              record={r}
                              catalog={catalog}
                              onEdit={() => void openRecord(r.record_id)}
                            />
                          ))
                      : null}
                    <div className="bm-section-heading">
                      <h2>
                        {category === "nutrition" ? "饮食记录" : "记录明细"}
                      </h2>
                      <span>{total} 条</span>
                    </div>
                    {recordsError ? (
                      <p role="alert">记录读取失败：{recordsError}</p>
                    ) : null}
                    {recordsLoading ? <p role="status">正在读取记录…</p> : null}
                    {catalog ? (
                      <div className="bm-record-list">
                        {records.map((r, index) => (
                          <div key={r.record_id}>
                            {category === "nutrition" &&
                            (index === 0 ||
                              dateOnly(
                                new Date(records[index - 1].starts_at),
                              ) !== dateOnly(new Date(r.starts_at))) ? (
                              <h3 className="bm-meal-date">
                                {dateOnly(new Date(r.starts_at))}
                              </h3>
                            ) : null}
                            <button
                              type="button"
                              key={r.record_id}
                              className="bm-record-row"
                              onClick={() => void openRecord(r.record_id)}
                            >
                              <span>
                                <strong>{recordLabel(r, catalog)}</strong>
                                <small>
                                  {time(r.starts_at)}
                                  {r.ends_at ? ` — ${time(r.ends_at)}` : ""}
                                  {r.precision === "day" ? " · 日汇总" : ""}
                                </small>
                                <small>
                                  {r.source}
                                  {r.edited ? " · 已修正" : ""}
                                  {r.data.estimated ? " · 估算" : ""}
                                </small>
                                {r.kind === "meal" ? (
                                  <small>
                                    {r.data.foods
                                      ?.map((f) => f.name)
                                      .join("、") || "整餐记录"}
                                  </small>
                                ) : null}
                              </span>
                              <span className="bm-record-number">
                                {recordValue(r)}
                                <small>
                                  查看{member.can_edit ? " / 编辑" : ""} ›
                                </small>
                              </span>
                            </button>
                          </div>
                        ))}
                      </div>
                    ) : null}
                    {total > 100 ? (
                      <div className="bm-pagination">
                        <button
                          className="control"
                          type="button"
                          disabled={recordsLoading || !offset}
                          onClick={() => setOffset((v) => Math.max(0, v - 100))}
                        >
                          上一页
                        </button>
                        <span>
                          {Math.floor(offset / 100) + 1} /{" "}
                          {Math.ceil(total / 100)}
                        </span>
                        <button
                          className="control"
                          type="button"
                          disabled={recordsLoading || offset + 100 >= total}
                          onClick={() => setOffset((v) => v + 100)}
                        >
                          下一页
                        </button>
                      </div>
                    ) : null}
                    <button
                      className="control bm-ask"
                      type="button"
                      onClick={() =>
                        void onAsk(
                          `请根据当前成员 ${dates.after} 至 ${dates.before} 的${title}记录，说明变化、数据覆盖及需要核对的信息。`,
                        ).catch((e) => setError(e.message))
                      }
                    >
                      询问这些记录
                    </button>
                  </>
                )}
              </div>
            </>
          )}
        </div>
      </div>
      {edit && catalog ? (
        <BodyRecordEditor
          key={`${member.member_id}:${edit.id || "new"}`}
          memberId={member.member_id}
          initial={edit.input}
          recordId={edit.id}
          catalog={catalog}
          canEdit={member.can_edit}
          onClose={() => {
            setEdit(null);
          }}
          onSaved={() => {
            setEdit(null);
            refreshData();
          }}
        />
      ) : null}
      {importing ? (
        <BodyImportDialog
          key={member.member_id}
          memberId={member.member_id}
          onClose={() => setImporting(false)}
          onComplete={refreshData}
        />
      ) : null}
    </section>
  );
}
function SleepTimeline({
  record: r,
  catalog,
  onEdit,
}: {
  record: BodyRecord;
  catalog: Catalog;
  onEdit: () => void;
}) {
  const stages = r.data.stages || [];
  const start = new Date(r.starts_at).getTime(),
    end = new Date(r.ends_at!).getTime();
  const total = end - start;
  const totals: Record<string, number> = {};
  stages.forEach((s) => {
    totals[s.stage] =
      (totals[s.stage] || 0) +
      (new Date(s.ends_at).getTime() - new Date(s.starts_at).getTime()) / 60000;
  });
  return (
    <section className="bm-sleep">
      <div className="bm-section-heading">
        <h3>
          {time(r.starts_at)} — {time(r.ends_at!)}
        </h3>
        <button className="control" type="button" onClick={onEdit}>
          查看阶段
        </button>
      </div>
      <div className="bm-sleep-summary">
        <strong>
          {number(r.data.duration_minutes)} <small>分钟睡眠</small>
        </strong>
        <span>
          {r.data.score == null
            ? "评分未提供"
            : `${r.data.score} / ${r.data.score_max} 分${r.data.score_stale ? " · 已过期，不计入统计" : ""}`}
        </span>
      </div>
      <div className="bm-hypnogram" aria-label="睡眠阶段时间轴">
        {["awake", "rem", "light", "deep", "unknown", "in_bed"].map(
          (stage, i) => (
            <div
              className="bm-stage-guide"
              key={stage}
              style={{ top: `${i * 26}px` }}
            >
              <span>{catalog.stages[stage]}</span>
            </div>
          ),
        )}
        {stages.map((s) => (
          <button
            type="button"
            key={s.stage_id}
            className={`bm-stage-block bm-stage-${s.stage}`}
            style={{
              left: `calc(58px + (100% - 58px) * ${(new Date(s.starts_at).getTime() - start) / total})`,
              width: `calc((100% - 58px) * ${(new Date(s.ends_at).getTime() - new Date(s.starts_at).getTime()) / total})`,
              top: `${["awake", "rem", "light", "deep", "unknown", "in_bed"].indexOf(s.stage) * 26}px`,
            }}
            title={`${catalog.stages[s.stage]} ${time(s.starts_at)}–${time(s.ends_at)}`}
            aria-label={`${catalog.stages[s.stage]} ${time(s.starts_at)}–${time(s.ends_at)}，编辑阶段`}
            onClick={onEdit}
          />
        ))}
      </div>
      <div className="bm-sleep-legend">
        {Object.entries(totals).map(([stage, duration]) => (
          <span key={stage}>
            <i className={`bm-stage-${stage}`} />
            {catalog.stages[stage]} {number(duration)} min ·{" "}
            {number(((duration * 60000) / total) * 100)}%
          </span>
        ))}
      </div>
      <p className="bm-muted">
        占比按完整时间区间计算 · 空白表示未提供阶段 · {r.source}
      </p>
    </section>
  );
}
