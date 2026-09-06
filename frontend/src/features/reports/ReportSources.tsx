import {
  useEffect,
  useRef,
  useState,
  type ChangeEvent
} from "react";
import { createPortal } from "react-dom";
import {
  apiClient,
  type ReportDetail,
  type ReportSourceFile
} from "../../api/client";
import { GroupedList } from "../../components/GroupedList";
import {
  AudioFormatIcon,
  DocumentFormatIcon,
  DownloadIcon,
  ImageFormatIcon,
  OtherFormatIcon,
  TextFormatIcon,
  UploadIcon,
  VideoFormatIcon,
  XIcon
} from "../../components/icons";
import { useStatusNotification } from "../../components/StatusNotificationCenter";
import { useModalDialog } from "../../components/useModalDialog";
import { InlineEditableValue } from "./ReportInlineField";
import {
  formatReportDate,
  sourceFileName
} from "./reportPresentation";
import { REPORT_FILE_ACCEPT } from "./reportUploadValidation";
import type { ReportWorkspaceState } from "./useReportWorkspace";

function SourceFileTypeIcon({ file }: { file: ReportSourceFile }) {
  const mimeType = String(file.mime_type || "").toLowerCase();
  const className = "source-preview-file-icon";
  if (file.source_type === "conversation_text" || mimeType.startsWith("text/")) {
    return <TextFormatIcon className={className} />;
  }
  if (mimeType.startsWith("image/")) {
    return <ImageFormatIcon className={className} />;
  }
  if (mimeType.startsWith("audio/")) {
    return <AudioFormatIcon className={className} />;
  }
  if (mimeType.startsWith("video/")) {
    return <VideoFormatIcon className={className} />;
  }
  if (mimeType === "application/pdf") {
    return <DocumentFormatIcon className={className} />;
  }
  return <OtherFormatIcon className={className} />;
}

export function SourcePreview({ workspace }: { workspace: ReportSourcesWorkspace }) {
  const preview = workspace.sourcePreview;
  const previewOpen = Boolean(preview);
  const sourcePreviewDialogRef = useRef<HTMLElement | null>(null);
  const sourcePreviewHeadingRef = useRef<HTMLHeadingElement | null>(null);
  useModalDialog({
    active: previewOpen,
    dialogRef: sourcePreviewDialogRef,
    initialFocusRef: sourcePreviewHeadingRef,
    onEscape: workspace.clearSourcePreview
  });
  if (!preview) return null;
  const isImage = preview.mimeType.startsWith("image/");
  const isPdf = preview.mimeType === "application/pdf";
  const isText = preview.mimeType.startsWith("text/");
  const previewKind = isImage ? "image" : isPdf ? "pdf" : isText ? "text" : "unsupported";
  const previewName = sourceFileName(preview.file);
  const sourceFiles = [...(workspace.selectedReport?.sources ?? [])]
    .sort((left, right) => Number(right.is_primary) - Number(left.is_primary));
  const showSourceNavigation = sourceFiles.length > 1;
  return createPortal(
    <div className="source-preview-backdrop dialog-viewport-backdrop" onMouseDown={(event) => { if (event.currentTarget === event.target) workspace.clearSourcePreview(); }}>
      <section aria-labelledby="source-preview-heading" aria-modal="true" className="source-preview dialog-viewport-surface" ref={sourcePreviewDialogRef} role="dialog" tabIndex={-1}>
        <header className="dialog-titlebar">
          <h3 className="source-preview-heading source-preview-focus-target" id="source-preview-heading" ref={sourcePreviewHeadingRef} tabIndex={-1}>{previewName}</h3>
          <div className="source-preview-actions">
            <a className="control control--titlebar control--ghost source-preview-titlebar-action source-preview-download" download={previewName} href={preview.objectUrl}>
              <DownloadIcon className="source-preview-titlebar-action-icon" />
              <span>下载</span>
            </a>
            <button aria-label="关闭原件预览" className="control control--titlebar control--icon control--ghost source-preview-titlebar-action source-preview-close titlebar-icon-control" onClick={workspace.clearSourcePreview} type="button"><XIcon /></button>
          </div>
        </header>
        <div className="dialog-body source-preview-body" data-single-source={showSourceNavigation ? undefined : "true"}>
          {showSourceNavigation ? <aside aria-label={`关联文件，共 ${sourceFiles.length} 个`} className="source-preview-files scroll-content">
            <header>
              <strong>关联文件</strong>
              <span>{sourceFiles.length} 个</span>
            </header>
            <GroupedList as="ul" className="source-preview-file-list" density="standard">
              {sourceFiles.map((file) => {
                const selected = file.resource_id === preview.file.resource_id;
                const name = sourceFileName(file);
                return (
                  <li key={file.resource_id}>
                    <button
                      aria-current={selected ? "page" : undefined}
                      aria-label={`查看${file.is_primary ? "主文件" : "关联文件"}：${name}`}
                      data-interaction-owner="row"
                      disabled={workspace.sourcePreviewLoading}
                      onClick={() => { if (!selected) void workspace.openSourceFile(file); }}
                      type="button"
                    >
                      <SourceFileTypeIcon file={file} />
                      <span className="source-preview-file-name">{name}</span>
                      {file.is_primary ? <span className="source-preview-file-status">主文件</span> : null}
                    </button>
                  </li>
                );
              })}
            </GroupedList>
          </aside> : null}
          <div
            aria-busy={workspace.sourcePreviewLoading ? "true" : undefined}
            className="source-preview-frame"
            data-preview-kind={previewKind}
          >
            {isImage ? <img alt="原始报告" src={preview.objectUrl} /> : null}
            {isPdf && preview.file.thumbnail_url ? (
              <img alt="原始报告 PDF 第一页" src={preview.file.thumbnail_url} />
            ) : null}
            {isPdf && !preview.file.thumbnail_url ? (
              <iframe src={`${preview.objectUrl}#page=1&view=Fit`} title="原始报告 PDF 第一页预览" />
            ) : null}
            {isText ? <pre className="source-preview-text scroll-content">{preview.textContent ?? ""}</pre> : null}
            {!isImage && !isPdf && !isText ? <div className="report-subtle-empty"><strong>浏览器无法直接预览此文件</strong><p>可下载后使用本地应用打开。</p></div> : null}
          </div>
        </div>
      </section>
    </div>,
    document.body
  );
}

type ReportSourceThumbnailData = { objectUrl: string };

function ReportSourceThumbnail({ file, loading, onOpen, memberId, reportId, sourceCount }: {
  file?: ReportSourceFile;
  loading: boolean;
  onOpen: (file: ReportSourceFile) => void;
  memberId: string;
  reportId: string;
  sourceCount: number;
}) {
  const hasThumbnail = Boolean(file?.thumbnail_url);
  const [preview, setPreview] = useState<ReportSourceThumbnailData | null>(null);
  const [previewFailed, setPreviewFailed] = useState(false);
  useEffect(() => {
    setPreview(null);
    setPreviewFailed(false);
    if (!memberId || !file || !hasThumbnail) return;
    const controller = new AbortController();
    let objectUrl: string | null = null;
    void apiClient.fetchReportSourceThumbnailBlob(memberId, reportId, file.resource_id, controller.signal)
      .then((blob) => {
        if (controller.signal.aborted) return;
        objectUrl = URL.createObjectURL(blob);
        setPreview({ objectUrl });
      })
      .catch(error => { if (!controller.signal.aborted && error?.message) setPreviewFailed(true); });
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [file, hasThumbnail, reportId, memberId]);
  useStatusNotification(previewFailed ? "原件缩略图暂时无法加载。" : "", {
    id: `report-source-thumbnail-${reportId}`,
    title: "原件预览未加载",
    tone: "error"
  });
  if (!file) {
    return <div className="report-source-thumbnail empty"><DocumentFormatIcon className="report-source-thumbnail-icon" /><small>暂无原件</small></div>;
  }
  return (
    <div className="report-source-thumbnail">
      <div className="report-source-thumbnail-frame" aria-hidden="true">
        {preview ? <img alt="" src={preview.objectUrl} /> : null}
        {!preview ? <div className="report-source-thumbnail-placeholder">{file.source_type === "conversation_text" ? <span>TXT</span> : <DocumentFormatIcon className="report-source-thumbnail-icon" />}<small>{hasThumbnail && !previewFailed ? "正在载入原件" : file.source_type === "conversation_text" ? "文本原件" : "原件"}</small></div> : null}
      </div>
      <button aria-busy={loading ? "true" : undefined} aria-label={`打开原件预览，共 ${sourceCount} 个关联文件`} className="report-source-thumbnail-open" data-hover="none" data-source-resource-id={file.resource_id} disabled={loading} onClick={() => onOpen(file)} type="button" />
    </div>
  );
}

export function ReportOverview({ loading, onOpenSource, report, workspace }: {
  loading: boolean;
  onOpenSource: (file: ReportSourceFile) => void;
  report: ReportDetail;
  workspace: ReportSourcesWorkspace;
}) {
  const sourceUploadInputRef = useRef<HTMLInputElement | null>(null);
  const originalSources = report.sources;
  const primarySource = originalSources.find((file) => file.is_primary) ?? originalSources[0];
  const analysisStatus = report.analysis_outdated
    ? "解读结果待更新"
    : report.has_analysis
      ? "已有解读结果"
      : "暂无解读结果";
  function handleSourceUpload(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.currentTarget.files ?? []);
    event.currentTarget.value = "";
    if (files.length) void workspace.addSelectedReportSources(files);
  }
  return (
    <div className="report-section report-overview-layout">
      <section aria-label="报告原件" className="report-overview-thumbnail">
        <input
          accept={REPORT_FILE_ACCEPT}
          disabled={!workspace.canEdit || workspace.addingSources}
          hidden
          multiple
          onChange={handleSourceUpload}
          ref={sourceUploadInputRef}
          tabIndex={-1}
          type="file"
        />
        <ReportSourceThumbnail memberId={report.member_id} file={primarySource} loading={loading} onOpen={onOpenSource} reportId={report.report_id} sourceCount={originalSources.length} />
        <button
          aria-busy={workspace.addingSources ? "true" : undefined}
          className="control control--secondary report-source-add-button"
          disabled={!workspace.canEdit || workspace.addingSources || workspace.deleting}
          onClick={() => sourceUploadInputRef.current?.click()}
          title={!workspace.canEdit ? "只读健康档案不能补充原件" : undefined}
          type="button"
        >
          <UploadIcon />
          <span>{workspace.addingSources ? "正在补充" : "补充原件"}</span>
        </button>
      </section>
      <section className="report-basic-information" aria-labelledby="report-basic-information-heading">
        <div className="group-heading"><h3 id="report-basic-information-heading">基础信息</h3></div>
        <div className="report-section-body report-basic-information-body">
          <GroupedList as="dl" layout="fields" className="report-basic-information-grid" density="standard">
            <div className="field-row"><dt className="field-label">报告类型</dt><dd className="field-value">{report.report_type}</dd></div>
            <div className="report-basic-name-row field-row">
              <dt className="field-label">报告名称</dt>
              <dd className="field-value">
                {report.report_type === "检验报告"
                  ? report.report_name
                  : <InlineEditableValue field="report_name" label="报告名称" required value={report.report_name} workspace={workspace} />}
              </dd>
            </div>
            <div className="field-row"><dt className="field-label">就诊机构</dt><dd className="field-value"><InlineEditableValue field="institution_name" label="就诊机构" value={report.institution_name} workspace={workspace} /></dd></div>
            <div className="report-basic-time-row field-row"><dt className="field-label">就诊时间</dt><dd className="field-value"><InlineEditableValue displayValue={<time dateTime={report.report_time}>{formatReportDate(report.report_time, true)}</time>} field="report_time" inputKind="datetime-local" label="就诊时间" required value={report.report_time} workspace={workspace} /></dd></div>
            <div className="field-row"><dt className="field-label">解读状态</dt><dd className="field-value">{analysisStatus}</dd></div>
          </GroupedList>
        </div>
      </section>
    </div>
  );
}

type ReportSourcesWorkspace = Pick<ReportWorkspaceState, "saving" | "updateSelectedReportField" | "clearActionFeedback" | "addSelectedReportSources" | "addingSources" | "canEdit" | "clearSourcePreview" | "deleting" | "openSourceFile" | "selectedReport" | "sourcePreview" | "sourcePreviewLoading">;
