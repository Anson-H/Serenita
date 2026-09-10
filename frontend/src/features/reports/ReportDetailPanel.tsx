import { EmptyState } from "../../components/EmptyState";
import {
  useEffect,
  useRef,
  type ReactNode,
  type RefObject
} from "react";
import {
  type ReportDetail,
  type ReportSourceFile
} from "../../api/client";
import {
  HealthRecordIcon,
  RegenerateIcon,
  TrashIcon
} from "../../components/icons";
import { DeleteReportAction, EditableAnalysis, StartReportAnalysisAction } from "./ReportAnalysisEditor";
import { ReportOverview, SourcePreview } from "./ReportSources";
import { StructuredReportContent } from "./ReportStructuredFields";
import type { ReportWorkspaceState } from "./useReportWorkspace";

function ReportDetailContent({ onOpenSource, report, workspace }: {
  onOpenSource: (file: ReportSourceFile) => void;
  report: ReportDetail;
  workspace: ReportWorkspaceState;
}) {
  const analysisRunning = workspace.analyzingReportId === report.report_id;
  const visibleAnalysisContent =
    report.analysis_content;
  const analysisActions = report.has_analysis ? (
    <>
      <button aria-label="删除解读结果" className="control control--inline control--icon control--ghost control--danger message-icon-button report-action-icon-button report-analysis-delete-button removal-action-control" disabled={!workspace.canEdit || workspace.deletingAnalysis || workspace.analyzing || analysisRunning} onClick={() => void workspace.deleteSelectedReportAnalysis()} title={workspace.deletingAnalysis ? "删除中" : "删除解读结果"} type="button"><TrashIcon className="message-action-icon" /></button>
      <button aria-label="重新解读" className="control control--inline control--icon control--ghost message-icon-button report-action-icon-button" disabled={!workspace.canEdit || workspace.deletingAnalysis || workspace.analyzing || analysisRunning} onClick={() => void workspace.analyzeSelectedReport("rewrite")} title={analysisRunning ? "解读中" : "重新解读"} type="button"><RegenerateIcon /></button>
    </>
  ) : undefined;
  return (
    <>
      <ReportOverview loading={workspace.sourcePreviewLoading} onOpenSource={onOpenSource} report={report} workspace={workspace} />
      <StructuredReportContent report={report} workspace={workspace} />
      {report.has_analysis ? (
        <EditableAnalysis
          actions={analysisActions}
          content={visibleAnalysisContent}
          key={report.report_id}
          workspace={workspace}
        />
      ) : null}
      {!report.has_analysis ? <StartReportAnalysisAction analysisRunning={analysisRunning} workspace={workspace} /> : null}
      <DeleteReportAction workspace={workspace} />
    </>
  );
}

export function ReportDetailPanel({ conversationComposer, panelRef, workspace }: {
  conversationComposer?: ReactNode;
  panelRef?: RefObject<HTMLElement | null>;
  workspace: ReportWorkspaceState;
}) {
  const detailPanelElementRef = useRef<HTMLElement | null>(null);
  const sourceResourceIdRef = useRef<string | null>(null);
  const previousSourcePreviewRef = useRef(workspace.sourcePreview);

  useEffect(() => {
    const previousPreview = previousSourcePreviewRef.current;
    previousSourcePreviewRef.current = workspace.sourcePreview;
    const wasOpen = Boolean(previousPreview);
    const isOpen = Boolean(workspace.sourcePreview);
    if (wasOpen === isOpen) return;
    const frame = window.requestAnimationFrame(() => {
      if (isOpen) return;
      if (!previousPreview || !sourceResourceIdRef.current) return;
      Array.from(detailPanelElementRef.current?.querySelectorAll<HTMLButtonElement>("[data-source-resource-id]") ?? []).find((button) => button.dataset.sourceResourceId === sourceResourceIdRef.current)?.focus();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [workspace.sourcePreview]);
  return (
    <article aria-busy={workspace.detailLoading ? "true" : "false"} aria-label={workspace.selectedReport?.report_name ?? "医疗报告详情"} className="report-detail-pane" data-composer-stage data-empty={!workspace.detailLoading && !workspace.selectedReport ? "true" : undefined} ref={(node) => { detailPanelElementRef.current = node; if (panelRef) panelRef.current = node; }} tabIndex={-1}>
      <div className={`report-detail-scroll scroll-content content-column${!workspace.detailLoading && !workspace.selectedReport ? " empty" : ""}`}>
        {workspace.detailLoading && !workspace.selectedReport ? <div className="report-detail-skeleton" aria-label="正在加载医疗报告详情"><span /><span /><span /></div> : workspace.selectedReport ? (
          <ReportDetailContent onOpenSource={(file) => { sourceResourceIdRef.current = file.resource_id; void workspace.openSourceFile(file); }} report={workspace.selectedReport} workspace={workspace} />
        ) : <EmptyState className="report-detail-empty" icon={<HealthRecordIcon />} title="查看医疗报告详情" description="从左侧选择一份医疗报告，查看医疗报告内容和解读结果。" />}
      </div>
      {conversationComposer && workspace.selectedReport ? <section aria-label="询问这份医疗报告" className="report-detail-composer">{conversationComposer}</section> : null}
      <SourcePreview workspace={workspace} />
    </article>
  );
}
