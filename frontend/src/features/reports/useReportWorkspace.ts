import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  type Dispatch,
  type SetStateAction
} from "react";
import {
  REPORT_TYPES,
  apiClient,
  type ConversationDetail,
  type Favorite,
  type ReportContextResource,
  type ReportDetail,
  type ReportSummary,
  type ReportType
} from "../../api/client";
import type { Member } from "../../api/memberApi";
import { ApiRequestError } from "../../api/request";
import { useActiveScope } from "../../utils/useActiveScope";
import { useScopedState } from "../../utils/useScopedState";
import { createReportAnalysisActions } from './reportAnalysisActions';
import type { ReportAnalysisMode } from "./reportAnalysisPrompt";
import { createReportCollectionActions } from './reportCollectionActions';
import { reportContextResourceFromReport } from "./reportContext";
import { createReportFavoriteActions } from './reportFavoriteActions';
import { createReportMutationActions } from './reportMutationActions';
import { createReportSourceActions } from './reportSourceActions';
import type { ReportSourcePreview } from "./reportSourcePreview";
import { ReportStateRefresher } from "./reportStateRefresh";

type UseReportWorkspaceOptions = {
  attachmentCapabilities: {
    selectedModelFileMimeTypes: string[];
    attachmentCapabilitiesReady: boolean;
    attachmentCapabilitiesError: string;
    retryAttachmentCapabilities: () => void;
  };
  conversationDetail?: ConversationDetail | null;
  member: Member | null;
  active: boolean;
  favorites: Favorite[];
  onConversationStarted: (sessionId: string) => void;
  onReportCleared?: () => void;
  onReportSelected?: (reportId: string) => void;
  requestedReportId?: string | null;
  setConversationDetail?: Dispatch<SetStateAction<ConversationDetail | null>>;
  setCurrentSessionId?: Dispatch<SetStateAction<string | null>>;
  setFavorites: Dispatch<SetStateAction<Favorite[]>>;
  selectedModelId: string | null;
  thinkingMode: string;
};

export function useReportWorkspace({
  conversationDetail,
  attachmentCapabilities,
  member: activeMember,
  active,
  favorites,
  onConversationStarted,
  onReportCleared,
  onReportSelected,
  requestedReportId,
  setConversationDetail,
  setCurrentSessionId,
  setFavorites,
  selectedModelId,
  thinkingMode
}: UseReportWorkspaceOptions) {
  const memberId = activeMember?.member_id ?? "";
  const isCurrentScope = useActiveScope(`${memberId || "unbound-report-workspace"}:${active}`);
  const canEdit = Boolean(activeMember?.can_edit);
  const reportImportMimeTypes = attachmentCapabilities.selectedModelFileMimeTypes.filter(type =>
    ["application/pdf", "image/jpeg", "image/png", "image/heic"].includes(type));
  const reportUploadUnavailableReason = attachmentCapabilities.attachmentCapabilitiesError
    || (!attachmentCapabilities.attachmentCapabilitiesReady ? "正在读取附件能力。"
      : !reportImportMimeTypes.length ? "当前模型配置不支持报告附件。" : "");
  const [selectedReportTypes, setSelectedReportTypes] = useScopedState<ReportType[]>(
    () => [...REPORT_TYPES]
    , isCurrentScope);
  const [allReports, setAllReports] = useScopedState<ReportSummary[]>([], isCurrentScope);
  const [listLoading, setListLoading] = useScopedState(false, isCurrentScope);
  const [listError, setListError] = useScopedState("", isCurrentScope);
  const [selectedReportId, setSelectedReportId] = useScopedState<string | null>(null, isCurrentScope);
  const [selectedReport, setSelectedReport] = useScopedState<ReportDetail | null>(null, isCurrentScope);
  const [detailLoading, setDetailLoading] = useScopedState(false, isCurrentScope);
  const [detailVisible, setDetailVisible] = useScopedState(false, isCurrentScope);
  const [actionError, setActionError] = useScopedState("", isCurrentScope);
  const [actionMessage, setActionMessage] = useScopedState("", isCurrentScope);
  const [analysisError, setAnalysisError] = useScopedState("", isCurrentScope);

  const [latestAnalysisReportId, setLatestAnalysisReportId] = useScopedState<string | null>(null, isCurrentScope);
  const [latestAnalysisMode, setLatestAnalysisMode] = useScopedState<ReportAnalysisMode>("initial", isCurrentScope);
  const [analyzing, setAnalyzing] = useScopedState(false, isCurrentScope);
  const [analyzingReportId, setAnalyzingReportId] = useScopedState<string | null>(null, isCurrentScope);
  const [saving, setSaving] = useScopedState(false, isCurrentScope);
  const [labItemMutation, setLabItemMutation] = useScopedState<"adding" | string | null>(null, isCurrentScope);
  const [deletingAnalysis, setDeletingAnalysis] = useScopedState(false, isCurrentScope);
  const [deleting, setDeleting] = useScopedState(false, isCurrentScope);
  const [favoritingReport, setFavoritingReport] = useScopedState(false, isCurrentScope);

  const [addingSources, setAddingSources] = useScopedState(false, isCurrentScope);
  const [creating, setCreating] = useScopedState(false, isCurrentScope);
  const [uploadErrors, setUploadErrors] = useScopedState<string[]>([], isCurrentScope);
  const [sourcePreview, setSourcePreview] = useScopedState<ReportSourcePreview | null>(null, isCurrentScope);
  const [sourcePreviewLoading, setSourcePreviewLoading] = useScopedState(false, isCurrentScope);
  const [reportDataRevision, setReportDataRevision] = useScopedState(0, isCurrentScope);
  const conversationRef = useRef(conversationDetail);
  conversationRef.current = conversationDetail;
  const resourceRefresher = useRef<ReportStateRefresher | null>(null);
  if (!resourceRefresher.current) resourceRefresher.current = new ReportStateRefresher(apiClient.getConversation);
  useEffect(() => () => resourceRefresher.current?.invalidate(), [memberId, conversationDetail?.session_id]);
  const selectedReportIdRef = useRef<string | null>(null);
  const detailRequestSequenceRef = useRef(0);
  const listRequestSequenceRef = useRef(0);
  const sourceRequestSequence = useRef(0);
  const sourceObjectUrlRef = useRef<string | null>(null);

  const loadReports = useCallback(async () => {
    if (!memberId || !isCurrentScope()) return;
    const requestSequence = ++listRequestSequenceRef.current;
    setListLoading(true);
    setListError("");
    try {
      const response = await apiClient.fetchReports(memberId);
      if (!isCurrentScope() || requestSequence !== listRequestSequenceRef.current) return;
      setAllReports(response.reports);
    } catch (error) {
      if (!isCurrentScope() || requestSequence !== listRequestSequenceRef.current) return;
      setListError(error instanceof Error ? error.message : "报告列表加载失败。");
    } finally {
      if (requestSequence === listRequestSequenceRef.current) setListLoading(false);
    }
  }, [memberId, active]);

  useEffect(() => {
    invalidateReportData();
    setAllReports([]);
    setLatestAnalysisReportId(null);
    setActionError("");
    setAnalysisError("");
    setUploadErrors([]);
    return () => { listRequestSequenceRef.current += 1; detailRequestSequenceRef.current += 1; };
  }, [memberId, active]);

  const selectedReportTypeSet = useMemo(
    () => new Set(selectedReportTypes),
    [selectedReportTypes]
  );
  const reports = useMemo(
    () => allReports.filter((report) => selectedReportTypeSet.has(report.report_type)),
    [allReports, selectedReportTypeSet]
  );
  const allReportIds = useMemo(
    () => allReports.map((report) => report.report_id),
    [allReports]
  );
  const total = reports.length;

  useEffect(() => {
    if (active) void loadReports();
  }, [active, loadReports, reportDataRevision]);

  useEffect(() => {
    if (!active) return;
    if (!requestedReportId) {
      detailRequestSequenceRef.current += 1;
      clearSourcePreview();
      setDetailVisible(false);
      return;
    }
    if (
      selectedReportIdRef.current === requestedReportId &&
      selectedReport
    ) {
      setDetailVisible(true);
      return;
    }
    void openReport(requestedReportId, true, false);
  }, [active, requestedReportId]);

  useEffect(() => {
    if (!active) return;
    const reportId = selectedReportIdRef.current;
    if (!reportId) return;

    let cancelled = false;
    setDetailLoading(true);
    setSelectedReport(null);
    void apiClient.getReport(memberId, reportId)
      .then((detail) => {
        if (!cancelled && selectedReportIdRef.current === reportId) {
          setSelectedReport(detail);
        }
      })
      .catch((error) => {
        if (!cancelled && selectedReportIdRef.current === reportId) {
          setActionError(error instanceof Error ? error.message : "报告详情刷新失败。");
        }
      })
      .finally(() => {
        if (!cancelled && selectedReportIdRef.current === reportId) {
          setDetailLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [active, reportDataRevision]);

  useEffect(() => () => {
    if (sourceObjectUrlRef.current) URL.revokeObjectURL(sourceObjectUrlRef.current);
  }, []);

  function toggleReportType(type: ReportType) {
    setSelectedReportTypes((current) => {
      const next = new Set(current);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return REPORT_TYPES.filter((reportType) => next.has(reportType));
    });
  }

  function selectReportTypes(types: ReportType[]) {
    const selectedTypes = new Set(types);
    setSelectedReportTypes(REPORT_TYPES.filter((type) => selectedTypes.has(type)));
  }

  const invalidateReportData = useCallback(() => {
    listRequestSequenceRef.current += 1;
    detailRequestSequenceRef.current += 1;
    if (sourceObjectUrlRef.current) URL.revokeObjectURL(sourceObjectUrlRef.current);
    sourceObjectUrlRef.current = null;
    selectedReportIdRef.current = null;
    setSelectedReportId(null);
    setSelectedReport(null);
    setDetailVisible(false);
    setDetailLoading(false);
    setSourcePreview(null);
    setSourcePreviewLoading(false);
    setReportDataRevision((current) => current + 1);
  }, [memberId, active]);

  async function openReport(
    reportId: string,
    showDetail = true,
    updateLocation = true
  ) {
    if (!memberId) return null;
    const requestSequence = ++detailRequestSequenceRef.current;
    clearSourcePreview();
    setSaving(false);
    setLabItemMutation(null);
    setDeletingAnalysis(false);
    setAddingSources(false);
    setAnalyzing(false);
    setAnalyzingReportId(null);
    setDetailLoading(true);
    setActionError("");
    try {
      const detail = await apiClient.getReport(memberId, reportId);
      if (!isCurrentScope() || detailRequestSequenceRef.current !== requestSequence) return null;
      selectedReportIdRef.current = reportId;
      setSelectedReportId(reportId);
      setSelectedReport(detail);
      setDetailVisible(showDetail);
      void refreshConversationReportStates([reportId]);
      if (showDetail && updateLocation) onReportSelected?.(reportId);
      return detail;
    } catch (error) {
      if (isCurrentScope() && detailRequestSequenceRef.current === requestSequence) {
        setActionError(
          error instanceof ApiRequestError && error.status === 404
            ? "报告已删除，无法打开。"
            : error instanceof Error
              ? error.message
              : "报告详情加载失败。"
        );
      }
      return null;
    } finally {
      if (isCurrentScope() && detailRequestSequenceRef.current === requestSequence) setDetailLoading(false);
    }
  }

  async function refreshConversationReportStates(reportIds: string[]) {
    const session = conversationRef.current;
    if (!setConversationDetail || !session || !isCurrentScope()) return;
    await resourceRefresher.current?.refresh({
      sessionId: session.session_id, memberId, reportIds,
      isCurrent: () => isCurrentScope() && conversationRef.current?.session_id === session.session_id
        && conversationRef.current?.member_id === session.member_id,
      update: setConversationDetail,
      onError: () => setActionError("报告操作已完成，会话资源状态刷新失败，请重新打开报告重试。")
    });
  }

  const reportFavorite = useMemo(
    () => favorites.find(
      (favorite) => favorite.source_type === "report" && favorite.member_id === memberId && favorite.source_id === selectedReportId
    ) ?? null,
    [favorites, selectedReportId, memberId]
  );

  const favoritedReportIds = useMemo(
    () => new Set(
      favorites
        .filter((favorite) => favorite.source_type === "report" && favorite.member_id === memberId)
        .map((favorite) => favorite.source_id)
    ),
    [favorites, memberId]
  );

  const activeReportResource = useMemo<ReportContextResource | null>(() => {
    if (selectedReport) return reportContextResourceFromReport(selectedReport);
    const summary = reports.find((report) => report.report_id === selectedReportId);
    return summary ? reportContextResourceFromReport(summary) : null;
  }, [reports, selectedReport, selectedReportId]);
  const { updateSelectedReportField, addSelectedReportLabItem, deleteSelectedReportLabItem, deleteSelectedReportAnalysis, addSelectedReportSources } = createReportMutationActions({
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
  });
  const { analyzeSelectedReport, retryLatestAnalysis } = createReportAnalysisActions({
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
  });
  const { favoriteReports, toggleReportFavorite } = createReportFavoriteActions({
    memberId,
    favoritingReport,
    favoritedReportIds,
    setActionError,
    setActionMessage,
    setFavoritingReport,
    isCurrentScope,
    setFavorites,
    detailRequestSequenceRef,
    selectedReportId,
    selectedReport,
    reportFavorite
  });
  const { clearSourcePreview, openSourceFile } = createReportSourceActions({
    sourceRequestSequence,
    sourceObjectUrlRef,
    setSourcePreview,
    setSourcePreviewLoading,
    selectedReportIdRef,
    memberId,
    setActionError,
    isCurrentScope
  });
  const { deleteReports, deleteSelectedReport, createManualReport } = createReportCollectionActions({
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
  });

  return {
    memberId,
    canEdit,
    reportImportMimeTypes,
    reportUploadUnavailableReason,
    retryAttachmentCapabilities: attachmentCapabilities.retryAttachmentCapabilities,
    attachmentCapabilitiesError: attachmentCapabilities.attachmentCapabilitiesError,
    REPORT_TYPES,
    actionError,
    actionMessage,
    addSelectedReportSources,
    addSelectedReportLabItem,
    addingSources,
    allReportIds,
    analysisError,
    reportFavorited: Boolean(reportFavorite),
    activeReportResource,
    analyzeSelectedReport,
    analyzing,
    analyzingReportId,
    clearActionFeedback: () => { setActionError(""); setActionMessage(""); },
    clearSourcePreview,
    createManualReport,
    creating,
    deleteSelectedReportAnalysis,
    deleteSelectedReportLabItem,
    deleteReports,
    deleteSelectedReport,
    deletingAnalysis,
    deleting,
    detailLoading,
    detailVisible,
    favoritingReport,
    favoriteReports,
    favoritedReportIds,
    invalidateReportData,
    latestAnalysisReportId,
    labItemMutation,
    listError,
    listLoading,
    loadReports,
    openReport,
    openSourceFile,
    reports,
    retryLatestAnalysis,
    saving,
    selectedReport,
    selectedReportId,
    selectedReportTypes,
    setDetailVisible,
    sourcePreview,
    sourcePreviewLoading,
    total,
    toggleReportType,
    selectReportTypes,
    toggleReportFavorite,
    updateSelectedReportField,
    uploadBlocked: !canEdit || Boolean(reportUploadUnavailableReason),
    uploadErrors,
    setUploadErrors,
  };
}

export type ReportWorkspaceState = ReturnType<typeof useReportWorkspace>;
