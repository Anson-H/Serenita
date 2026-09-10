/** 提交开始解读与重新解读的会话任务，管理提交状态、重试目标和完成导航。 */
import { apiClient, type ReportDetail } from "../../../api/client";
import { reportContextResourceFromReport } from "../reportContext";
import { reportListDateHeading } from "../reportPresentation";
import type { ReportDetailState } from "./detail";
import { ReportStore } from "./store";

export type ReportAnalysisMode = "initial" | "rewrite";

/** 根据目标医疗报告与解读方式构建提交给会话的用户任务文本。 */
export function reportAnalysisPrompt(
  report: ReportDetail,
  mode: ReportAnalysisMode
) {
  const target = `${reportListDateHeading(report.report_time)}的${report.report_name.trim()}${report.report_type}`;
  return mode === "rewrite"
    ? `对${target}重新解读`
    : `对${target}进行医疗报告解读`;
}

type AnalysisState = {
  analyzing: boolean;
  analyzingReportId: string | null;
  latestAnalysisReportId: string | null;
  latestAnalysisMode: ReportAnalysisMode;
  analysisError: string;
};
export class ReportAnalysisActions extends ReportStore<AnalysisState> {
  constructor(private detail: ReportDetailState, private options: {
    canEdit: () => boolean;
    deletingAnalysis: () => boolean;
    model: () => { selectedModelId: string | null; thinkingMode: string };
    onConversationStarted: (sessionId: string) => void;
    onError: (message: string) => void;
    onMessage: (message: string) => void;
  }) {
    super({ analyzing: false, analyzingReportId: null, latestAnalysisReportId: null, latestAnalysisMode: "initial", analysisError: "" });
    detail.onSelectionInvalidated(() => this.publish({ analyzing: false, analyzingReportId: null }));
  }

  forget = (reportIds: string[]) => {
    if (this.state.latestAnalysisReportId && reportIds.includes(this.state.latestAnalysisReportId))
      this.publish({ latestAnalysisReportId: null, analysisError: "" });
  };

  private async run(reportId: string, mode: ReportAnalysisMode) {
    const operation = this.detail.capture();
    if (!operation.isCurrent() || !this.options.canEdit() || this.state.analyzing || this.options.deletingAnalysis()) return false;
    this.publish({ analyzing: true, analyzingReportId: reportId, latestAnalysisReportId: reportId, latestAnalysisMode: mode, analysisError: "" });
    this.options.onError("");
    try {
      const report = operation.report?.report_id === reportId ? operation.report : await apiClient.getReport(this.detail.memberId, reportId);
      if (!operation.isCurrent() || !this.options.canEdit()) return false;
      const model = this.options.model();
      const queued = await apiClient.sendMessage({
        memberId: this.detail.memberId, sessionId: null,
        rawText: reportAnalysisPrompt(report, mode),
        modelId: model.selectedModelId, thinkingMode: model.thinkingMode,
        contextResources: [reportContextResourceFromReport(report)],
      });
      if (!operation.isCurrent()) return false;
      this.options.onMessage(`医疗报告解读已提交到聊天 ${queued.session_id}，将在后台继续。`);
      this.detail.hide();
      this.options.onConversationStarted(queued.session_id);
      return true;
    } catch (error) {
      if (!operation.isCurrent()) return false;
      const message = error instanceof Error ? error.message : "医疗报告解读失败。";
      this.publish({ analysisError: message });
      this.options.onError(message);
      return false;
    } finally {
      if (operation.isCurrent()) this.publish({ analyzing: false, analyzingReportId: null });
    }
  }

  analyzeSelectedReport = (mode: ReportAnalysisMode) => {
    const reportId = this.detail.snapshot().selectedReportId;
    return reportId ? this.run(reportId, mode) : Promise.resolve(false);
  };
  retryLatestAnalysis = () => this.state.latestAnalysisReportId
    ? this.run(this.state.latestAnalysisReportId, this.state.latestAnalysisMode) : Promise.resolve(false);
}
