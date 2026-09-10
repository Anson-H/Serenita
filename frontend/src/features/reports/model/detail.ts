/** 管理医疗报告详情、当前选择和读取有效性，统一检查详情发布的身份与顺序。 */
import type { ReportDetail } from "../../../api/client";
import { ApiRequestError } from "../../../api/request";
import { ReportStore } from "./store";

type DetailState = {
  selectedReportId: string | null;
  selectedReport: ReportDetail | null;
  detailLoading: boolean;
  detailVisible: boolean;
};
export type ReportOperation = {
  reportId: string | null;
  report: ReportDetail | null;
  isCurrent: () => boolean;
};

export class ReportDetailState extends ReportStore<DetailState> {
  private generation = 0;
  private navigationRequest = 0;
  private revision = 0;
  private pendingReportId: string | null = null;
  private selectionListeners = new Set<() => void>();

  constructor(readonly memberId: string, private options: {
    read: (memberId: string, reportId: string) => Promise<ReportDetail>;
    isCurrent: () => boolean;
    beforeNavigate: () => Promise<boolean>;
    onError: (message: string) => void;
    onOpened: (reportId: string, updateLocation: boolean) => void;
  }) {
    super({ selectedReportId: null, selectedReport: null, detailLoading: false, detailVisible: false });
  }

  onSelectionInvalidated(listener: () => void) {
    this.selectionListeners.add(listener);
    return () => { this.selectionListeners.delete(listener); };
  }

  capture = (): ReportOperation => {
    const generation = this.generation;
    return {
      reportId: this.state.selectedReportId,
      report: this.state.selectedReport,
      isCurrent: () => this.options.isCurrent() && generation === this.generation,
    };
  };

  private invalidateSelection() {
    this.generation++;
    this.navigationRequest++;
    this.pendingReportId = null;
    this.selectionListeners.forEach(listener => listener());
  }

  clear = () => {
    this.invalidateSelection();
    this.revision++;
    this.publish({ selectedReportId: null, selectedReport: null, detailLoading: false, detailVisible: false });
  };

  hide = () => {
    this.invalidateSelection();
    this.publish({ detailVisible: false, detailLoading: false });
  };

  show = () => { this.publish({ detailVisible: true }); };

  /** Report identity and refresh ordering are checked at the publication boundary. */
  apply = (report: ReportDetail, operation = this.capture()) => {
    if (!operation.isCurrent() || report.member_id !== this.memberId || report.report_id !== this.state.selectedReportId) return false;
    this.revision++;
    this.publish({ selectedReport: report });
    return true;
  };

  open = async (reportId: string, showDetail = true, updateLocation = true) => {
    const previous = this.capture();
    const navigationRequest = ++this.navigationRequest;
    if (!this.memberId || !previous.isCurrent()) return null;
    if (previous.reportId !== reportId && !await this.options.beforeNavigate()) return null;
    if (!previous.isCurrent() || navigationRequest !== this.navigationRequest) return null;
    this.invalidateSelection();
    const operation = this.capture();
    this.pendingReportId = reportId;
    this.publish({ detailLoading: true });
    this.options.onError("");
    try {
      const report = await this.options.read(this.memberId, reportId);
      if (!operation.isCurrent()) return null;
      if (report.member_id !== this.memberId || report.report_id !== reportId) throw new Error("医疗报告详情与请求的医疗报告不一致。");
      this.revision++;
      this.publish({ selectedReportId: reportId, selectedReport: report, detailVisible: showDetail });
      this.options.onOpened(reportId, showDetail && updateLocation);
      return report;
    } catch (error) {
      if (operation.isCurrent()) this.options.onError(error instanceof ApiRequestError && error.status === 404
        ? "医疗报告已删除，无法打开。" : error instanceof Error ? error.message : "医疗报告详情加载失败。");
      return null;
    } finally {
      if (operation.isCurrent()) {
        this.pendingReportId = null;
        this.publish({ detailLoading: false });
      }
    }
  };

  refresh = async (operation = this.capture(), reportError = true) => {
    if (!operation.reportId || !operation.isCurrent()) return;
    const revision = this.revision;
    try {
      const report = await this.options.read(this.memberId, operation.reportId);
      if (revision === this.revision) this.apply(report, operation);
    } catch (error) {
      if (reportError && operation.isCurrent() && revision === this.revision)
        this.options.onError(error instanceof Error ? error.message : "医疗报告详情刷新失败。");
    }
  };

  remove = (reportIds: string[]) => {
    if ((this.state.selectedReportId && reportIds.includes(this.state.selectedReportId))
      || (this.pendingReportId && reportIds.includes(this.pendingReportId))) {
      this.clear();
      return true;
    }
    return false;
  };
}
