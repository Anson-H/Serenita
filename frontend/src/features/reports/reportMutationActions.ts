import type * as React from "react";
import {
  type Dispatch,
  type SetStateAction
} from "react";
import {
  apiClient,
  type AddLabReportItemInput,
  type ReportDetail,
  type ReportEditableField
} from "../../api/client";
import { validateReportFiles } from "./reportUploadValidation";

type Dependencies = {
  detailRequestSequenceRef: React.RefObject<number>;
  isCurrentScope: () => boolean;
  canEdit: boolean;
  selectedReport: ReportDetail | null;
  saving: boolean;
  labItemMutation: string | null;
  deletingAnalysis: boolean;
  setSaving: Dispatch<SetStateAction<boolean>>;
  setActionError: Dispatch<SetStateAction<string>>;
  memberId: string;
  selectedReportIdRef: React.RefObject<string | null>;
  setSelectedReport: Dispatch<SetStateAction<ReportDetail | null>>;
  refreshConversationReportStates: (reportIds: string[]) => Promise<void>;
  loadReports: () => Promise<void>;
  setActionMessage: Dispatch<SetStateAction<string>>;
  deleting: boolean;
  setLabItemMutation: Dispatch<SetStateAction<string | null>>;
  analyzing: boolean;
  setDeletingAnalysis: Dispatch<SetStateAction<boolean>>;
  setLatestAnalysisReportId: Dispatch<SetStateAction<string | null>>;
  setAnalysisError: Dispatch<SetStateAction<string>>;
  addingSources: boolean;
  setAddingSources: Dispatch<SetStateAction<boolean>>;
};

export function createReportMutationActions({
  detailRequestSequenceRef,
  isCurrentScope,
  canEdit,
  selectedReport,
  saving,
  labItemMutation,
  deletingAnalysis,
  setSaving,
  setActionError,
  memberId,
  selectedReportIdRef,
  setSelectedReport,
  refreshConversationReportStates,
  loadReports,
  setActionMessage,
  deleting,
  setLabItemMutation,
  analyzing,
  setDeletingAnalysis,
  setLatestAnalysisReportId,
  setAnalysisError,
  addingSources,
  setAddingSources
}: Dependencies) {
  function captureOperation() {
    const sequence = detailRequestSequenceRef.current;
    return () => isCurrentScope() && sequence === detailRequestSequenceRef.current;
  }

  async function applyMutationResult(updated: ReportDetail, isCurrent: () => boolean) {
    if (!isCurrent()) return;
    if (selectedReportIdRef.current === updated.report_id) setSelectedReport(updated);
    void refreshConversationReportStates([updated.report_id]);
    await loadReports();
  }

  async function refreshAfterFailure(reportId: string, isCurrent: () => boolean) {
    try {
      const current = await apiClient.getReport(memberId, reportId);
      if (isCurrent() && selectedReportIdRef.current === reportId) setSelectedReport(current);
    } catch {
      // The mutation error remains the user-facing failure.
    }
  }

  async function updateSelectedReportField(input: {
    field: ReportEditableField;
    value: string | null;
    item_id?: string;
  }) {
    const operationIsCurrent = captureOperation();
    if (!canEdit || !selectedReport || saving || labItemMutation || deletingAnalysis) return false;
    setSaving(true);
    setActionError("");
    try {
      const updated = await apiClient.updateReportField(memberId,
        selectedReport.report_id,
        input
      );
      if (!operationIsCurrent()) return false;
      await applyMutationResult(updated, operationIsCurrent);
      if (!operationIsCurrent()) return false;
      setActionMessage("报告字段已保存。");
      return updated;
    } catch (error) {
      if (!operationIsCurrent()) return false;
      const reportId = selectedReport.report_id;
      await refreshAfterFailure(reportId, operationIsCurrent);
      if (!operationIsCurrent()) return false;
      setActionError(error instanceof Error ? error.message : "报告字段保存失败。");
      return false;
    } finally {
      if (operationIsCurrent()) {
        setSaving(false);
      }
    }
  }

  async function addSelectedReportLabItem(input: AddLabReportItemInput) {
    const operationIsCurrent = captureOperation();
    if (!canEdit || !selectedReport || saving || labItemMutation || deleting) return false;
    const reportId = selectedReport.report_id;
    setLabItemMutation("adding");
    setActionError("");
    setActionMessage("");
    try {
      const updated = await apiClient.addReportLabItem(memberId, reportId, input);
      if (!operationIsCurrent()) return false;
      await applyMutationResult(updated, operationIsCurrent);
      if (!operationIsCurrent()) return false;
      setActionMessage("检验指标已添加。");
      return updated;
    } catch (error) {
      if (!operationIsCurrent()) return false;
      await refreshAfterFailure(reportId, operationIsCurrent);
      if (!operationIsCurrent()) return false;
      setActionError(error instanceof Error ? error.message : "检验指标添加失败。");
      return false;
    } finally {
      if (operationIsCurrent()) {
        setLabItemMutation(null);
      }
    }
  }

  async function deleteSelectedReportLabItem(itemId: string) {
    const operationIsCurrent = captureOperation();
    if (!canEdit || !selectedReport || saving || labItemMutation || deleting) return false;
    const reportId = selectedReport.report_id;
    setLabItemMutation(itemId);
    setActionError("");
    setActionMessage("");
    try {
      const updated = await apiClient.deleteReportLabItem(memberId, reportId, itemId);
      if (!operationIsCurrent()) return false;
      await applyMutationResult(updated, operationIsCurrent);
      if (!operationIsCurrent()) return false;
      setActionMessage("检验指标已删除。");
      return updated;
    } catch (error) {
      if (!operationIsCurrent()) return false;
      await refreshAfterFailure(reportId, operationIsCurrent);
      if (!operationIsCurrent()) return false;
      setActionError(error instanceof Error ? error.message : "检验指标删除失败。");
      return false;
    } finally {
      if (operationIsCurrent()) {
        setLabItemMutation(null);
      }
    }
  }

  async function deleteSelectedReportAnalysis() {
    const operationIsCurrent = captureOperation();
    if (
      !selectedReport?.has_analysis ||
      deletingAnalysis ||
      saving ||
      analyzing
    ) return false;
    const reportId = selectedReport.report_id;
    setDeletingAnalysis(true);
    setActionError("");
    setActionMessage("");
    try {
      const updated = await apiClient.updateReportField(memberId, reportId, {
        field: "analysis_content",
        value: null
      });
      if (!operationIsCurrent()) return false;
      if (isCurrentScope() && selectedReportIdRef.current === reportId) {
        setSelectedReport(updated);
      }
      void refreshConversationReportStates([reportId]);
      setLatestAnalysisReportId((current) => current === reportId ? null : current);
      setAnalysisError("");
      await loadReports();
      if (!operationIsCurrent()) return false;
      setActionMessage("解读结果已删除。");
      return true;
    } catch (error) {
      if (!operationIsCurrent()) return false;
      await refreshAfterFailure(reportId, operationIsCurrent);
      if (!operationIsCurrent()) return false;
      setActionError(error instanceof Error ? error.message : "解读结果删除失败。");
      return false;
    } finally {
      if (operationIsCurrent()) {
        setDeletingAnalysis(false);
      }
    }
  }

  async function addSelectedReportSources(fileList: FileList | File[]) {
    const operationIsCurrent = captureOperation();
    const reportId = selectedReportIdRef.current;
    if (!canEdit || !memberId || !reportId || addingSources || deleting) {
      return false;
    }
    const files = Array.from(fileList);
    const errors = validateReportFiles(files);
    if (errors.length) {
      setActionMessage("");
      setActionError(errors.join("；"));
      return false;
    }

    setAddingSources(true);
    setActionError("");
    setActionMessage("");
    try {
      const updated = await apiClient.addReportSourceFiles(
        memberId,
        reportId,
        files
      );
      if (!operationIsCurrent()) return false;
      if (!isCurrentScope()) return updated;
      await applyMutationResult(updated, operationIsCurrent);
      if (!operationIsCurrent()) return false;
      setActionMessage(
        files.length === 1
          ? "原件已补充。"
          : `已补充 ${files.length} 份原件。`
      );
      return updated;
    } catch (error) {
      if (!operationIsCurrent()) return false;
      if (isCurrentScope() && selectedReportIdRef.current === reportId) {
        try {
          const refreshed = await apiClient.getReport(memberId, reportId);
          if (!operationIsCurrent()) return false;
          setSelectedReport(refreshed);
          if (!operationIsCurrent()) return false;
        } catch {
          if (!operationIsCurrent()) return false;
          // Preserve the upload failure when refreshing the report also fails.
        }
      }
      if (isCurrentScope()) {
        setActionError(error instanceof Error ? error.message : "报告原件补充失败。");
      }
      return false;
    } finally {
      if (operationIsCurrent()) {
        setAddingSources(false);
      }
    }
  }
  return {
    updateSelectedReportField,
    addSelectedReportLabItem,
    deleteSelectedReportLabItem,
    deleteSelectedReportAnalysis,
    addSelectedReportSources
  };
}
