/** 管理医疗报告字段、检验指标、解读结果和来源的编辑状态及保存请求。 */
import { SerialTasks } from "../../../utils/serialTasks";
import { apiClient, type AddLabReportItemInput, type ReportDetail, type ReportEditableField } from "../../../api/client";
import type { ReportDetailState, ReportOperation } from "./detail";
import { ReportStore } from "./store";
import { validateReportFiles } from "../reportUploadValidation";

type MutationState = { saving: boolean; labItemMutation: string | null; deletingAnalysis: boolean; addingSources: boolean };
const idle: MutationState = { saving: false, labItemMutation: null, deletingAnalysis: false, addingSources: false };

export class ReportMutationActions extends ReportStore<MutationState> {
  private serialTasks = new SerialTasks();
  constructor(private detail: ReportDetailState, private options: {
    canEdit: () => boolean;
    deleting: () => boolean;
    analyzing: () => boolean;
    onChanged: (reportIds: string[]) => Promise<void>;
    onAnalysisDeleted: (reportId: string) => void;
    onError: (message: string) => void;
    onMessage: (message: string) => void;
  }) {
    super(idle);
    detail.onSelectionInvalidated(() => this.publish(idle));
  }

  private capture() {
    const operation = this.detail.capture();
    if (!this.options.canEdit() || !operation.isCurrent() || !operation.reportId || operation.report?.report_id !== operation.reportId) return null;
    return { ...operation, reportId: operation.reportId, report: operation.report, isRelevant: operation.isCurrent, isCurrent: () => operation.isCurrent() && this.options.canEdit() };
  }

  private async apply(updated: ReportDetail, operation: ReportOperation) {
    if (!this.detail.apply(updated, operation)) return false;
    await this.options.onChanged([updated.report_id]);
    return operation.isCurrent();
  }

  updateSelectedReportField = async (input: { field: ReportEditableField; value: string | null; item_id?: string }) => {
    const operation = this.capture();
    if (!operation || this.state.labItemMutation || this.state.deletingAnalysis || this.options.deleting()) return false;
    const key = operation.reportId;
    this.publish({ saving: true });
    this.options.onError("");
    try {
      const updated = await this.serialTasks.run(key, () => apiClient.updateReportField(this.detail.memberId, key, input), operation.isCurrent);
      if (!await this.apply(updated, operation)) return false;
      this.options.onMessage("医疗报告字段已保存。");
      return updated;
    } catch (error) {
      if (operation.isCurrent()) this.options.onError(error instanceof Error ? error.message : "医疗报告字段保存失败。");
      return false;
    } finally {
      if (operation.isRelevant()) this.publish({ saving: this.serialTasks.hasPending(key) });
    }
  };

  private async mutateLabItem(itemId: string, save: (reportId: string) => Promise<ReportDetail>, success: string, failure: string) {
    const operation = this.capture();
    if (!operation || this.state.saving || this.serialTasks.hasPending(operation.reportId) || this.state.labItemMutation || this.options.deleting()) return false;
    this.publish({ labItemMutation: itemId });
    this.options.onError("");
    this.options.onMessage("");
    try {
      const updated = await save(operation.reportId);
      if (!await this.apply(updated, operation)) return false;
      this.options.onMessage(success);
      return updated;
    } catch (error) {
      await this.detail.refresh(operation, false);
      if (operation.isCurrent()) this.options.onError(error instanceof Error ? error.message : failure);
      return false;
    } finally {
      if (operation.isRelevant()) this.publish({ labItemMutation: null });
    }
  }

  addSelectedReportLabItem = (input: AddLabReportItemInput) => this.mutateLabItem("adding",
    reportId => apiClient.addReportLabItem(this.detail.memberId, reportId, input), "检验指标已添加。", "检验指标添加失败。");

  deleteSelectedReportLabItem = (itemId: string) => this.mutateLabItem(itemId,
    reportId => apiClient.deleteReportLabItem(this.detail.memberId, reportId, itemId), "检验指标已删除。", "检验指标删除失败。");

  deleteSelectedReportAnalysis = async () => {
    const operation = this.capture();
    if (!operation?.report.has_analysis || this.state.deletingAnalysis || this.state.saving || this.options.analyzing() || this.options.deleting()) return false;
    this.publish({ deletingAnalysis: true });
    this.options.onError("");
    this.options.onMessage("");
    try {
      const updated = await apiClient.updateReportField(this.detail.memberId, operation.reportId, { field: "analysis_content", value: null });
      if (!await this.apply(updated, operation)) return false;
      this.options.onAnalysisDeleted(operation.reportId);
      this.options.onMessage("解读结果已删除。");
      return true;
    } catch (error) {
      await this.detail.refresh(operation, false);
      if (operation.isCurrent()) this.options.onError(error instanceof Error ? error.message : "解读结果删除失败。");
      return false;
    } finally {
      if (operation.isRelevant()) this.publish({ deletingAnalysis: false });
    }
  };

  addSelectedReportSources = async (fileList: FileList | File[]) => {
    const operation = this.capture();
    if (!operation || this.state.addingSources || this.options.deleting()) return false;
    const files = Array.from(fileList);
    const errors = validateReportFiles(files);
    if (errors.length) {
      this.options.onMessage("");
      this.options.onError(errors.join("；"));
      return false;
    }
    this.publish({ addingSources: true });
    this.options.onError("");
    this.options.onMessage("");
    try {
      const updated = await apiClient.addReportSourceFiles(this.detail.memberId, operation.reportId, files);
      if (!await this.apply(updated, operation)) return false;
      this.options.onMessage(files.length === 1 ? "原件已补充。" : `已补充 ${files.length} 份原件。`);
      return updated;
    } catch (error) {
      await this.detail.refresh(operation, false);
      if (operation.isCurrent()) this.options.onError(error instanceof Error ? error.message : "医疗报告原件补充失败。");
      return false;
    } finally {
      if (operation.isRelevant()) this.publish({ addingSources: false });
    }
  };
}
