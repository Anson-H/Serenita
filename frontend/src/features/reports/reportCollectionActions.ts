import type * as React from "react";
import {
  type Dispatch,
  type SetStateAction
} from "react";
import {
  apiClient,
  type CreateReportInput,
  type ReportDetail
} from "../../api/client";

type Dependencies = {
  canEdit: boolean;
  deleting: boolean;
  setDeleting: Dispatch<SetStateAction<boolean>>;
  setActionError: Dispatch<SetStateAction<string>>;
  setActionMessage: Dispatch<SetStateAction<string>>;
  memberId: string;
  isCurrentScope: () => boolean;
  refreshConversationReportStates: (reportIds: string[]) => Promise<void>;
  setLatestAnalysisReportId: Dispatch<SetStateAction<string | null>>;
  selectedReportIdRef: React.RefObject<string | null>;
  clearSourcePreview: () => void;
  setSelectedReportId: Dispatch<SetStateAction<string | null>>;
  setSelectedReport: Dispatch<SetStateAction<ReportDetail | null>>;
  setDetailVisible: Dispatch<SetStateAction<boolean>>;
  onReportCleared: (() => void) | undefined;
  loadReports: () => Promise<void>;
  selectedReport: ReportDetail | null;
  creating: boolean;
  setCreating: Dispatch<SetStateAction<boolean>>;
  openReport: (reportId: string, showDetail?: boolean, updateLocation?: boolean) => Promise<ReportDetail | null>;
};

export function createReportCollectionActions({
  canEdit,
  deleting,
  setDeleting,
  setActionError,
  setActionMessage,
  memberId,
  isCurrentScope,
  refreshConversationReportStates,
  setLatestAnalysisReportId,
  selectedReportIdRef,
  clearSourcePreview,
  setSelectedReportId,
  setSelectedReport,
  setDetailVisible,
  onReportCleared,
  loadReports,
  selectedReport,
  creating,
  setCreating,
  openReport
}: Dependencies) {
  async function deleteReports(reportIds: string[]) {
    const uniqueReportIds = [...new Set(reportIds.filter(Boolean))];
    if (!canEdit || !uniqueReportIds.length || deleting) return uniqueReportIds;
    setDeleting(true);
    setActionError("");
    setActionMessage("");
    try {
      const outcomes = await Promise.all(uniqueReportIds.map(async (reportId) => {
        try {
          await apiClient.deleteReport(memberId, reportId);
          return { reportId, success: true as const };
        } catch (error) {
          return {
            error: error instanceof Error ? error.message : "报告删除失败。",
            reportId,
            success: false as const
          };
        }
      }));
      if (!isCurrentScope()) return uniqueReportIds;
      const deletedReportIds = outcomes
        .filter((outcome) => outcome.success)
        .map((outcome) => outcome.reportId);
      const failedOutcomes = outcomes.filter((outcome) => !outcome.success);
      const failedReportIds = failedOutcomes.map((outcome) => outcome.reportId);
      const deletedReportIdSet = new Set(deletedReportIds);

      void refreshConversationReportStates(deletedReportIds);
      setLatestAnalysisReportId((current) => (
        current && deletedReportIdSet.has(current) ? null : current
      ));

      if (
        selectedReportIdRef.current &&
        deletedReportIdSet.has(selectedReportIdRef.current)
      ) {
        clearSourcePreview();
        selectedReportIdRef.current = null;
        setSelectedReportId(null);
        setSelectedReport(null);
        setDetailVisible(false);
        onReportCleared?.();
      }

      if (
        selectedReportIdRef.current &&
        failedReportIds.includes(selectedReportIdRef.current)
      ) {
        try {
          const current = await apiClient.getReport(memberId, selectedReportIdRef.current);
          setSelectedReport(current);
        } catch {
          // Preserve the delete failure when the detail refresh also fails.
        }
      }

      await loadReports();
      if (failedOutcomes.length) {
        setActionError(
          uniqueReportIds.length === 1
            ? failedOutcomes[0]?.error ?? "报告删除失败。"
            : `有 ${failedOutcomes.length} 份报告未能删除，请重试。`
        );
      } else {
        setActionMessage(
          deletedReportIds.length === 1
            ? "报告已删除。"
            : `已删除 ${deletedReportIds.length} 份报告。`
        );
      }
      return failedReportIds;
    } finally {
      setDeleting(false);
    }
  }

  async function deleteSelectedReport() {
    if (!canEdit || !selectedReport || deleting) return false;
    const failedReportIds = await deleteReports([selectedReport.report_id]);
    return failedReportIds.length === 0;
  }

  async function createManualReport(input: CreateReportInput) {
    if (!canEdit || creating) return false;
    setCreating(true);
    setActionError("");
    setActionMessage("");
    try {
      const created = await apiClient.createReport(memberId, input);
      if (!isCurrentScope()) return created;
      await loadReports();
      await openReport(created.report_id, true);
      setActionMessage("报告已新增。");
      return created;
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "报告新增失败。");
      return false;
    } finally {
      setCreating(false);
    }
  }
  return {
    deleteReports,
    deleteSelectedReport,
    createManualReport
  };
}
