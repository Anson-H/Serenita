import { navigationLabels } from "../../components/navigationLabels";
import { EmptyState } from "../../components/EmptyState";
import { useEffect, useRef, useState } from "react";
import { ContentDialog } from "../../components/ContentDialog";
import { GroupedList } from "../../components/GroupedList";
import { MultiSelectPopover } from "../../components/MultiSelectPopover";
import { apiUrl } from "../../api/request";
import {
  getCatalog,
  bodyBase,
  previewImport,
  commitImport,
  getImport,
  getImports,
  deleteImport,
  type ImportJob,
} from "../../api/bodyMetricApi";
import { DateField } from "../../components/DateField";

const status = {
  preview: "待导入",
  running: "正在保存",
  complete: "已完成",
  failed: "失败，可重试",
};

export function BodyImportDialog({
  memberId,
  onClose,
  onComplete,
}: {
  memberId: string;
  onClose: () => void;
  onComplete: () => void;
}) {
  const active = useRef(true);
  const uploadRequest = useRef<{ file: File; id: string } | null>(null);
  const [uploadFailed, setUploadFailed] = useState(false);
  const [notice, setNotice] = useState("");
  const [labels, setLabels] = useState<Record<string, string>>({
    meal: "饮食",
    sleep: "睡眠",
    workout: "运动",
  });
  const [job, setJob] = useState<ImportJob | null>(null);
  const [history, setHistory] = useState<ImportJob[]>([]);
  const [historyCursor, setHistoryCursor] = useState<string | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const historyRequest = useRef<AbortController | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [after, setAfter] = useState<string | null>(null);
  const [before, setBefore] = useState<string | null>(null);
  const [categories, setCategories] = useState<string[]>([]);

  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
      historyRequest.current?.abort();
    };
  }, []);
  useEffect(() => {
    let current = true;
    void getCatalog(memberId)
      .then((catalog) => {
        if (current)
          setLabels((value) => ({
            ...value,
            ...Object.fromEntries(
              catalog.metrics.map((metric) => [metric.metric, metric.label]),
            ),
          }));
      })
      .catch((cause) => {
        if (current) setError(cause.message);
      });
    return () => {
      current = false;
    };
  }, [memberId]);
  useEffect(() => {
    const controller = new AbortController(); historyRequest.current?.abort(); historyRequest.current = controller;
    setHistoryLoading(true);
    void getImports(memberId, undefined, controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) { setHistory(result.items); setHistoryCursor(result.next_cursor); }
      })
      .catch((cause) => {
        if (!controller.signal.aborted) setError(cause.message);
      }).finally(() => { if (!controller.signal.aborted) setHistoryLoading(false); });
    return () => {
      controller.abort();
    };
  }, [memberId, job?.state]);
  async function loadMoreHistory() {
    if (!historyCursor || historyLoading) return;
    const controller = new AbortController(); historyRequest.current?.abort(); historyRequest.current = controller;
    setHistoryLoading(true);
    try {
      const result = await getImports(memberId, historyCursor, controller.signal);
      if (!active.current || controller.signal.aborted) return;
      setHistory(current => [...current, ...result.items.filter(item => !current.some(existing => existing.import_id === item.import_id))]);
      setHistoryCursor(result.next_cursor);
    } catch (cause) { if (active.current && !controller.signal.aborted) setError(cause instanceof Error ? cause.message : "导入记录读取失败。"); }
    finally { if (active.current && !controller.signal.aborted) setHistoryLoading(false); }
  }
  useEffect(() => {
    if (job?.state !== "running") return;
    let current = true;
    let timer: number;
    async function poll() {
      try {
        const result = await getImport(memberId, job!.import_id);
        if (!current) return;
        setJob(result);
        if (result.state === "complete") onComplete();
        if (result.state !== "running") return;
      } catch (cause) {
        if (current)
          setError(
            cause instanceof Error ? cause.message : "进度读取失败，请重试。",
          );
      }
      if (current) timer = window.setTimeout(() => void poll(), 1000);
    }
    timer = window.setTimeout(() => void poll(), 1000);
    return () => {
      current = false;
      window.clearTimeout(timer);
    };
  }, [memberId, job?.import_id, job?.state, onComplete]);

  function selectJob(item: ImportJob) {
    setJob(item);
    setAfter(item.date_from);
    setBefore(item.date_to);
    setCategories(item.categories);
  }
  async function upload(file: File, retry = false) {
    if (busy) return;
    if (!retry) uploadRequest.current = { file, id: crypto.randomUUID() };
    const attempt = uploadRequest.current!;
    setBusy(true);
    setError("");
    setUploadFailed(false);
    setJob(null);
    try {
      const item = await previewImport(memberId, file, attempt.id);
      if (active.current) selectJob(item);
    } catch (cause) {
      if (active.current) {
        setError(
          cause instanceof Error ? cause.message : "文件读取失败，请重试。",
        );
        setUploadFailed(true);
      }
    } finally {
      if (active.current) setBusy(false);
    }
  }
  async function run() {
    if (!job || busy) return;
    setError("");
    setBusy(true);
    try {
      const result = await commitImport(memberId, job.import_id, {
        ...(after ? { after } : {}),
        ...(before ? { before } : {}),
        categories,
      });
      if (active.current) setJob(result);
    } catch (cause) {
      if (active.current)
        setError(cause instanceof Error ? cause.message : "导入失败，请重试。");
    } finally {
      if (active.current) setBusy(false);
    }
  }
  async function remove(item: ImportJob) {
    setError("");
    setBusy(true);
    try {
      const result = await deleteImport(memberId, item.import_id);
      if (!active.current) return;
      setNotice(
        `批次已删除：删除 ${result.records_deleted} 条，保留 ${result.records_retained} 条记录。`,
      );
      setHistory((value) =>
        value.filter((entry) => entry.import_id !== item.import_id),
      );
      if (job?.import_id === item.import_id) setJob(null);
      onComplete();
    } catch (cause) {
      if (active.current)
        setError(
          cause instanceof Error ? cause.message : "批次删除失败，请重试。",
        );
    } finally {
      if (active.current) setBusy(false);
    }
  }

  return (
    <ContentDialog title={navigationLabels.importBody} onClose={onClose} busy={busy}>
      <p>
        支持苹果健康 XML / ZIP，或 Serenita 标准 CSV /
        JSON。同一文件可再次上传，选择此前尚未导入的范围。
      </p>
      <div className="bm-template-links">
        <a
          className="control"
          href={apiUrl(`${bodyBase(memberId)}/template?format=json`)}
          download
        >
          下载 JSON 示例
        </a>
        <a
          className="control"
          href={apiUrl(`${bodyBase(memberId)}/template?format=csv`)}
          download
        >
          下载 CSV 模板
        </a>
      </div>
      <label className="bm-upload">
        <strong>{busy ? "正在处理…" : "选择健康数据文件"}</strong>
        <span>最多 64 MiB · 示例文件含虚构数据</span>
        <input
          type="file"
          accept=".xml,.zip,.csv,.json"
          disabled={busy || job?.state === "running"}
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = "";
            if (file) void upload(file);
          }}
        />
      </label>
      {uploadFailed && uploadRequest.current ? (
        <button
          className="control"
          type="button"
          disabled={busy}
          onClick={() => void upload(uploadRequest.current!.file, true)}
        >
          重试读取文件
        </button>
      ) : null}
      {job ? (
        <section className="bm-edit-group">
          <div className="bm-section-heading">
            <h3>{job.filename}</h3>
            <span>{status[job.state]}</span>
          </div>
          <div className="bm-stat-grid">
            <div>
              <strong>{job.valid_count}</strong>
              <span>有效记录</span>
            </div>
            <div>
              <strong>{job.new_count}</strong>
              <span>预计创建</span>
            </div>
            <div>
              <strong>{job.duplicates}</strong>
              <span>重复记录</span>
            </div>
          </div>
          {job.state === "preview" || job.state === "failed" ? (
            <>
              <fieldset className="bm-fields-container" disabled={busy}>
                <GroupedList density="standard" layout="fields">
                  <DateField
                    label="开始日期"
                    value={after}
                    onChange={setAfter}
                    disabled={busy}
                  />
                  <DateField
                    label="结束日期"
                    value={before}
                    onChange={setBefore}
                    disabled={busy}
                  />
                  <div className="field-row">
                    <span>导入内容</span>
                    <MultiSelectPopover
                      ariaLabel="导入内容"
                      interactionOwner="row"
                      menuWidth="content"
                      menuAlign="end"
                      disabled={busy}
                      values={categories}
                      options={job.categories.map((value) => ({
                        value,
                        label: labels[value] || value,
                      }))}
                      onChange={setCategories}
                      allSelectedLabel="全部类型"
                      emptySelectedLabel="请选择"
                      selectedCountLabel={(count) => `${count} 类`}
                    />
                  </div>
                </GroupedList>
              </fieldset>
              <button
                className="control control--primary"
                type="button"
                disabled={busy || !job.valid_count || !categories.length}
                onClick={() => void run()}
              >
                导入所选记录
              </button>
            </>
          ) : null}
          {job.state === "running" ? (
            <>
              <progress aria-label="导入进行中" />
              <p>正在校验与保存，完成后刷新趋势。</p>
              <button
                type="button"
                className="control"
                disabled={busy}
                onClick={() => void run()}
              >
                继续导入
              </button>
            </>
          ) : null}
          {job.state === "complete" ? (
            <p role="status">已完成，创建 {job.inserted} 条记录。</p>
          ) : null}
          {job.error ? <p role="alert">{job.error}</p> : null}
          {job.issues.length ? (
            <details>
              <summary>查看 {job.issues.length} 条问题</summary>
              {job.issues.map((issue, index) => (
                <p key={index}>
                  第 {issue.row} 条：{issue.message}
                </p>
              ))}
            </details>
          ) : null}
          {Object.keys(job.unsupported).length ? (
            <details>
              <summary>未导入类型与无效记录</summary>
              {Object.entries(job.unsupported).map(([key, count]) => (
                <p key={key}>
                  {key}：{count}
                </p>
              ))}
            </details>
          ) : null}
        </section>
      ) : null}
      <section className="bm-edit-group">
        <h3>导入记录</h3>
        <GroupedList density="standard">
          {history.map((item) => (
            <div className="bm-history-row" key={item.import_id}>
              <button
                type="button"
                className="control"
                disabled={busy}
                onClick={() => selectJob(item)}
              >
                {item.filename} · {status[item.state]}
              </button>
              <button
                type="button"
                className="control"
                disabled={busy || item.state === "running"}
                onClick={() => void remove(item)}
              >
                删除批次
              </button>
            </div>
          ))}
        </GroupedList>
        {!history.length ? <EmptyState layout="inline" title="暂无导入记录" /> : null}
        {historyCursor ? <button className="control" type="button" disabled={historyLoading} onClick={() => void loadMoreHistory()}>{historyLoading ? "正在读取…" : "加载更多导入记录"}</button> : null}
      </section>
      {notice ? <p role="status">{notice}</p> : null}
      {error ? (
        <p role="alert" className="bm-error">
          {error}
        </p>
      ) : null}
    </ContentDialog>
  );
}
