/** 执行医疗报告的手工创建与删除，并同步列表、详情选择和操作反馈。 */
import { apiClient, type CreateReportInput } from "../../../api/client";
import type { ReportDetailState } from "./detail";
import { ReportStore } from "./store";

export class ReportCollectionActions extends ReportStore<{ deleting: boolean; creating: boolean }> {
  constructor(private detail: ReportDetailState, private options: {
    canEdit: () => boolean;
    isCurrent: () => boolean;
    onChanged: (reportIds: string[]) => Promise<void>;
    onDeleted: (reportIds: string[]) => void;
    onReportCleared: () => void;
    onError: (message: string) => void;
    onMessage: (message: string) => void;
  }) { super({ deleting: false, creating: false }); }

  deleteReports = async (reportIds: string[]) => {
    const unique = [...new Set(reportIds.filter(Boolean))];
    if (!this.options.isCurrent() || !this.options.canEdit() || !unique.length || this.state.deleting) return unique;
    this.publish({ deleting: true });
    this.options.onError("");
    this.options.onMessage("");
    try {
      const outcomes = await Promise.all(unique.map(async reportId => {
        try { await apiClient.deleteReport(this.detail.memberId, reportId); return { reportId, success: true as const }; }
        catch (error) { return { reportId, success: false as const, error: error instanceof Error ? error.message : "医疗报告删除失败。" }; }
      }));
      if (!this.options.isCurrent()) return unique;
      const deleted = outcomes.filter(result => result.success).map(result => result.reportId);
      const failures = outcomes.filter(result => !result.success);
      const failed = failures.map(result => result.reportId);
      this.options.onDeleted(deleted);
      if (this.detail.remove(deleted)) this.options.onReportCleared();
      const operation = this.detail.capture();
      if (operation.reportId && failed.includes(operation.reportId)) await this.detail.refresh(operation, false);
      await this.options.onChanged(deleted);
      if (!this.options.isCurrent()) return failed;
      if (failures.length) this.options.onError(unique.length === 1 ? failures[0]?.error ?? "医疗报告删除失败。" : `有 ${failures.length} 份医疗报告未能删除，请重试。`);
      else this.options.onMessage(deleted.length === 1 ? "医疗报告已删除。" : `已删除 ${deleted.length} 份医疗报告。`);
      return failed;
    } finally { if (this.options.isCurrent()) this.publish({ deleting: false }); }
  };

  deleteSelectedReport = async () => {
    const reportId = this.detail.snapshot().selectedReportId;
    return reportId ? (await this.deleteReports([reportId])).length === 0 : false;
  };

  createManualReport = async (input: CreateReportInput) => {
    if (!this.options.isCurrent() || !this.options.canEdit() || this.state.creating) return false;
    this.publish({ creating: true });
    this.options.onError("");
    this.options.onMessage("");
    try {
      const created = await apiClient.createReport(this.detail.memberId, input);
      if (!this.options.isCurrent()) return created;
      await this.options.onChanged([created.report_id]);
      if (!this.options.isCurrent()) return created;
      await this.detail.open(created.report_id, true);
      if (this.options.isCurrent()) this.options.onMessage("医疗报告已创建。");
      return created;
    } catch (error) {
      if (this.options.isCurrent()) this.options.onError(error instanceof Error ? error.message : "医疗报告创建失败。");
      return false;
    } finally { if (this.options.isCurrent()) this.publish({ creating: false }); }
  };
}
