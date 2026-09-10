import {OriginalFileThumbnail} from "../../components/OriginalFileThumbnail";
import {
  useEffect,
  useRef,
  useState,
  type ChangeEvent
} from "react";
import { FilePreview, type PreviewFile } from "../../components/FilePreview";
import {
  apiClient,
  type ReportDetail,
  type ReportSourceFile
} from "../../api/client";
import { GroupedList } from "../../components/GroupedList";
import {
  UploadIcon
} from "../../components/icons";
import { useStatusNotification } from "../../components/StatusNotificationCenter";
import { InlineEditableValue } from "./ReportInlineField";
import {
  formatReportDate,
  sourceFileName
} from "./reportPresentation";
import { REPORT_FILE_ACCEPT } from "./reportUploadValidation";
import type { ReportWorkspaceState } from "./useReportWorkspace";

export function SourcePreview({ workspace }: { workspace: ReportSourcesWorkspace }) {
  const preview=workspace.sourcePreview;
  if(!preview)return null;
  const sources=[...(workspace.selectedReport?.sources??[])].sort((left,right)=>Number(right.is_primary)-Number(left.is_primary));
  const present=(file:ReportSourceFile):PreviewFile=>({id:file.resource_id,name:sourceFileName(file),mimeType:file.source_type==='conversation_text'?'text/plain':file.mime_type||'',thumbnailUrl:file.thumbnail_url,isPrimary:file.is_primary});
  return <FilePreview file={{...present(preview.file),mimeType:preview.mimeType}} files={sources.map(present)} objectUrl={preview.objectUrl} textContent={preview.textContent??undefined} loading={workspace.sourcePreviewLoading} imageLabel="原始医疗报告" onClose={workspace.clearSourcePreview} onSelect={file=>{const source=sources.find(s=>s.resource_id===file.id);if(source)void workspace.openSourceFile(source);}}/>;
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
    id: `original-file-thumbnail-${reportId}`,
    title: "原件预览未加载",
    tone: "error"
  });
  return <OriginalFileThumbnail fileId={file?.resource_id} previewUrl={preview?.objectUrl} text={file?.source_type==='conversation_text'} loading={hasThumbnail&&!preview} failed={previewFailed} count={sourceCount} disabled={loading} onOpen={()=>{if(file)onOpen(file);}}/>;
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
      <section aria-label="医疗报告原件" className="report-overview-thumbnail">
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
            <div className="field-row"><dt className="field-label">医疗报告类型</dt><dd className="field-value">{report.report_type}</dd></div>
            <div className="report-basic-name-row field-row">
              <dt className="field-label">医疗报告名称</dt>
              <dd className="field-value">
                {report.report_type === "检验报告"
                  ? report.report_name
                  : <InlineEditableValue field="report_name" label="医疗报告名称" required value={report.report_name} workspace={workspace} />}
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

type ReportSourcesWorkspace = Pick<ReportWorkspaceState, "reportSaveKey" | "saving" | "updateSelectedReportField" | "clearActionFeedback" | "addSelectedReportSources" | "addingSources" | "canEdit" | "clearSourcePreview" | "deleting" | "openSourceFile" | "selectedReport" | "sourcePreview" | "sourcePreviewLoading">;
