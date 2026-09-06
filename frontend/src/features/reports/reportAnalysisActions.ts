import type * as React from "react";
import {
  type Dispatch,
  type SetStateAction
} from "react";
import {
  apiClient,
  type ReportDetail
} from "../../api/client";
import type { ReportAnalysisMode } from './reportAnalysisPrompt';
import { reportAnalysisPrompt } from './reportAnalysisPrompt';
import { reportContextResourceFromReport } from "./reportContext";

type Dependencies = {
  thinkingMode: string;
  memberId: string;
  isCurrentScope: () => boolean;
  selectedModelId: string | null;
  setCurrentSessionId: Dispatch<SetStateAction<string | null>> | undefined;
  setDetailVisible: Dispatch<SetStateAction<boolean>>;
  onConversationStarted: (sessionId: string) => void;
  detailRequestSequenceRef: React.RefObject<number>;
  canEdit: boolean;
  analyzing: boolean;
  deletingAnalysis: boolean;
  setAnalyzing: Dispatch<SetStateAction<boolean>>;
  setAnalyzingReportId: Dispatch<SetStateAction<string | null>>;
  setLatestAnalysisReportId: Dispatch<SetStateAction<string | null>>;
  setLatestAnalysisMode: Dispatch<SetStateAction<ReportAnalysisMode>>;
  setAnalysisError: Dispatch<SetStateAction<string>>;
  setActionError: Dispatch<SetStateAction<string>>;
  selectedReport: ReportDetail | null;
  setActionMessage: Dispatch<SetStateAction<string>>;
  selectedReportId: string | null;
  latestAnalysisReportId: string | null;
  latestAnalysisMode: ReportAnalysisMode;
};

export function createReportAnalysisActions({
  thinkingMode,
  memberId,
  isCurrentScope,
  selectedModelId,
  setCurrentSessionId,
  setDetailVisible,
  onConversationStarted,
  detailRequestSequenceRef,
  canEdit,
  analyzing,
  deletingAnalysis,
  setAnalyzing,
  setAnalyzingReportId,
  setLatestAnalysisReportId,
  setLatestAnalysisMode,
  setAnalysisError,
  setActionError,
  selectedReport,
  setActionMessage,
  selectedReportId,
  latestAnalysisReportId,
  latestAnalysisMode
}: Dependencies) {
  async function submitReportTask(
    rawText: string,
    resources: Array<Record<string, unknown>>
  ) {
    if (!memberId || !isCurrentScope()) throw new Error("报告工作区没有绑定成员。");
    const queued = await apiClient.sendMessage({
      memberId,
      sessionId: null,
      rawText,
      modelId: selectedModelId,
      thinkingMode,
      contextResources: resources
    });
    if (!isCurrentScope()) return queued;
    setCurrentSessionId?.(queued.session_id);
    setDetailVisible(false);
    onConversationStarted(queued.session_id);
    return queued;
  }

  async function runReportAnalysis(reportId: string, mode: ReportAnalysisMode) {
    const sequence = detailRequestSequenceRef.current;
    const operationIsCurrent = () => isCurrentScope() && sequence === detailRequestSequenceRef.current;
    if (!canEdit || analyzing || deletingAnalysis) return false;
    setAnalyzing(true);
    setAnalyzingReportId(reportId);
    setLatestAnalysisReportId(reportId);
    setLatestAnalysisMode(mode);
    setAnalysisError("");
    setActionError("");
    try {
      const report = selectedReport?.report_id === reportId
        ? selectedReport
        : await apiClient.getReport(memberId, reportId);
      if (!operationIsCurrent()) return false;
      const queued = await submitReportTask(
        reportAnalysisPrompt(report, mode),
        [reportContextResourceFromReport(report)]
      );
      if (!operationIsCurrent()) return false;
      setActionMessage(`报告解读已提交到聊天 ${queued.session_id}，将在后台继续。`);
      return true;
    } catch (error) {
      if (!operationIsCurrent()) return false;
      const message = error instanceof Error ? error.message : "报告解读失败。";
      setAnalysisError(message);
      setActionError(message);
      return false;
    } finally {
      if (operationIsCurrent()) {
        setAnalyzing(false);
        setAnalyzingReportId(null);
      }
    }
  }

  async function analyzeSelectedReport(mode: ReportAnalysisMode) {
    return selectedReportId ? runReportAnalysis(selectedReportId, mode) : false;
  }

  async function retryLatestAnalysis() {
    return latestAnalysisReportId
      ? runReportAnalysis(latestAnalysisReportId, latestAnalysisMode)
      : false;
  }
  return {
    analyzeSelectedReport,
    retryLatestAnalysis
  };
}
