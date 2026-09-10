import { saveBeforeNavigation } from "../../utils/pendingNavigation";
import { captureAuthContext } from "../../api/authLifecycle";
import { useCallback, useEffect, useMemo, useRef, useSyncExternalStore, type Dispatch, type SetStateAction } from "react";
import { REPORT_TYPES, apiClient, type ConversationDetail, type Favorite, type ReportContextResource, type ReportSummary, type ReportType } from "../../api/client";
import type { Member } from "../../api/memberApi";
import { useActiveScope } from "../../utils/useActiveScope";
import { useScopedState } from "../../utils/useScopedState";
import { ReportAnalysisActions } from "./model/analysis";
import { ReportCollectionActions } from "./model/collection";
import { reportContextResourceFromReport } from "./reportContext";
import { ReportDetailState } from "./model/detail";
import { createReportFavoriteActions } from "./model/favorites";
import { ReportMutationActions } from "./model/mutations";
import { ReportSourceActions } from "./model/sources";
import type { ReportStore } from "./model/store";
import { ReportStateRefresher } from "./model/conversationRefresh";
import { reportDateTimeInputValue } from "./reportPresentation";

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
  setFavorites: Dispatch<SetStateAction<Favorite[]>>;
  selectedModelId: string | null;
  thinkingMode: string;
};

function useReportState<T extends object>(store: ReportStore<T>) {
  return useSyncExternalStore(store.subscribe, store.snapshot, store.snapshot);
}

export function useReportWorkspace({
  conversationDetail, attachmentCapabilities, member: activeMember, active, favorites,
  onConversationStarted, onReportCleared, onReportSelected, requestedReportId,
  setConversationDetail, setFavorites, selectedModelId, thinkingMode,
}: UseReportWorkspaceOptions) {
  const memberId = activeMember?.member_id ?? "";
  const authContext = captureAuthContext();
  const isCurrentScope = useActiveScope(`${memberId || "unbound-report-workspace"}:${active}`);
  const canEdit = Boolean(activeMember?.can_edit);
  const reportImportMimeTypes = attachmentCapabilities.selectedModelFileMimeTypes.filter(type =>
    ["application/pdf", "image/jpeg", "image/png", "image/heic"].includes(type));
  const reportUploadUnavailableReason = attachmentCapabilities.attachmentCapabilitiesError ||
    (!attachmentCapabilities.attachmentCapabilitiesReady ? "正在读取附件能力。" : !reportImportMimeTypes.length ? "当前模型配置不支持医疗报告附件。" : "");
  const [selectedReportTypes, setSelectedReportTypes] = useScopedState<ReportType[]>(() => [...REPORT_TYPES], isCurrentScope);
  const [allReports, setAllReports] = useScopedState<ReportSummary[]>([], isCurrentScope);
  const [reportQuery, setReportQuery] = useScopedState("", isCurrentScope);
  const [reportAfterDate, setReportAfterDate] = useScopedState<string | null>(null, isCurrentScope);
  const [reportBeforeDate, setReportBeforeDate] = useScopedState<string | null>(null, isCurrentScope);
  const [listLoading, setListLoading] = useScopedState(false, isCurrentScope);
  const [listError, setListError] = useScopedState("", isCurrentScope);
  const [actionError, setActionError] = useScopedState("", isCurrentScope);
  const [actionMessage, setActionMessage] = useScopedState("", isCurrentScope);
  const [favoritingReport, setFavoritingReport] = useScopedState(false, isCurrentScope);
  const [uploadErrors, setUploadErrors] = useScopedState<string[]>([], isCurrentScope);
  const [reportDataRevision, setReportDataRevision] = useScopedState(0, isCurrentScope);
  const listRequestSequence = useRef(0);
  const conversationRef = useRef(conversationDetail);
  conversationRef.current = conversationDetail;
  const resourceRefresher = useRef<ReportStateRefresher | null>(null);
  if (!resourceRefresher.current) resourceRefresher.current = new ReportStateRefresher(apiClient.getConversation);
  useEffect(() => () => resourceRefresher.current?.invalidate(), [memberId, conversationDetail?.session_id]);

  const loadReports = useCallback(async () => {
    if (!memberId || !isCurrentScope()) return;
    const sequence = ++listRequestSequence.current;
    setListLoading(true);
    setListError("");
    try {
      const response = await apiClient.fetchReports(memberId);
      if (isCurrentScope() && sequence === listRequestSequence.current) setAllReports(response.reports);
    } catch (error) {
      if (isCurrentScope() && sequence === listRequestSequence.current)
        setListError(error instanceof Error ? error.message : "医疗报告列表加载失败。");
    } finally {
      if (isCurrentScope() && sequence === listRequestSequence.current) setListLoading(false);
    }
  }, [memberId, active, authContext]);

  async function refreshConversationReportStates(reportIds: string[]) {
    const session = conversationRef.current;
    if (!setConversationDetail || !session || !isCurrentScope()) return;
    await resourceRefresher.current?.refresh({
      sessionId: session.session_id, memberId, reportIds,
      isCurrent: () => isCurrentScope() && conversationRef.current?.session_id === session.session_id && conversationRef.current?.member_id === session.member_id,
      update: setConversationDetail,
      onError: () => setActionError("医疗报告操作已完成，会话资源状态刷新失败，请重新打开医疗报告重试。"),
    });
  }

  // Callbacks follow current props; controller identity follows the resource scope.
  const behavior = useRef({ canEdit, selectedModelId, thinkingMode, onConversationStarted, onReportSelected, onReportCleared, loadReports, refreshConversationReportStates });
  behavior.current = { canEdit, selectedModelId, thinkingMode, onConversationStarted, onReportSelected, onReportCleared, loadReports, refreshConversationReportStates };
  const controllers = useMemo(() => {
    const detail = new ReportDetailState(memberId, {
      read: apiClient.getReport, isCurrent: isCurrentScope, beforeNavigate: saveBeforeNavigation,
      onError: setActionError,
      onOpened: (reportId, updateLocation) => {
        void behavior.current.refreshConversationReportStates([reportId]);
        if (updateLocation) behavior.current.onReportSelected?.(reportId);
      },
    });
    const source = new ReportSourceActions(detail, { read: apiClient.fetchReportSourceBlob, onError: setActionError });
    async function changed(reportIds: string[]) {
      if (!isCurrentScope()) return;
      void behavior.current.refreshConversationReportStates(reportIds);
      await behavior.current.loadReports();
    }
    const analysis: ReportAnalysisActions = new ReportAnalysisActions(detail, {
      canEdit: () => behavior.current.canEdit,
      deletingAnalysis: () => mutation.snapshot().deletingAnalysis,
      model: () => behavior.current,
      onConversationStarted: sessionId => behavior.current.onConversationStarted(sessionId),
      onError: setActionError, onMessage: setActionMessage,
    });
    const collection: ReportCollectionActions = new ReportCollectionActions(detail, {
      canEdit: () => behavior.current.canEdit, isCurrent: isCurrentScope,
      onChanged: changed, onDeleted: analysis.forget,
      onReportCleared: () => behavior.current.onReportCleared?.(),
      onError: setActionError, onMessage: setActionMessage,
    });
    const mutation: ReportMutationActions = new ReportMutationActions(detail, {
      canEdit: () => behavior.current.canEdit,
      deleting: () => collection.snapshot().deleting,
      analyzing: () => analysis.snapshot().analyzing,
      onChanged: changed, onAnalysisDeleted: reportId => analysis.forget([reportId]),
      onError: setActionError, onMessage: setActionMessage,
    });
    return { detail, source, analysis, collection, mutation };
  }, [memberId, active, authContext]);
  const detailState = useReportState(controllers.detail);
  const sourceState = useReportState(controllers.source);
  const mutationState = useReportState(controllers.mutation);
  const analysisState = useReportState(controllers.analysis);
  const collectionState = useReportState(controllers.collection);
  const { selectedReport, selectedReportId } = detailState;
  const reportSaveKey = `${authContext.accountId}:${memberId}:${selectedReportId}`;

  const invalidateReportData = useCallback(() => {
    listRequestSequence.current++;
    controllers.detail.clear();
    setReportDataRevision(value => value + 1);
  }, [controllers]);

  useEffect(() => {
    setReportQuery(""); setReportAfterDate(null); setReportBeforeDate(null);
  }, [memberId]);
  useEffect(() => {
    invalidateReportData();
    setAllReports([]); setActionError(""); setUploadErrors([]);
    return () => { listRequestSequence.current++; controllers.detail.clear(); };
  }, [controllers]);
  useEffect(() => { if (active) void loadReports(); }, [active, loadReports, reportDataRevision]);
  useEffect(() => {
    if (!active) return;
    if (!requestedReportId) { controllers.detail.hide(); return; }
    const current = controllers.detail.snapshot();
    if (current.selectedReportId === requestedReportId && current.selectedReport) controllers.detail.show();
    else void controllers.detail.open(requestedReportId, true, false);
  }, [controllers, active, requestedReportId]);
  useEffect(() => { if (active) void controllers.detail.refresh(); }, [controllers, active, reportDataRevision]);

  const selectedReportTypeSet = useMemo(() => new Set(selectedReportTypes), [selectedReportTypes]);
  const reports = useMemo(() => {
    const query = reportQuery.trim().toLocaleLowerCase();
    return allReports.filter(report => {
      const date = reportDateTimeInputValue(report.report_time).slice(0, 10);
      return selectedReportTypeSet.has(report.report_type)
        && (!query || [report.report_name, report.report_type, report.institution_name ?? ""].some(text => text.toLocaleLowerCase().includes(query)))
        && (!reportAfterDate || date >= reportAfterDate) && (!reportBeforeDate || date <= reportBeforeDate);
    });
  }, [allReports, selectedReportTypeSet, reportQuery, reportAfterDate, reportBeforeDate]);
  const allReportIds = useMemo(() => allReports.map(report => report.report_id), [allReports]);
  const reportFavorite = useMemo(() => favorites.find(favorite => favorite.source_type === "report" && favorite.member_id === memberId && favorite.source_id === selectedReportId) ?? null,
    [favorites, selectedReportId, memberId]);
  const favoritedReportIds = useMemo(() => new Set(favorites.filter(favorite => favorite.source_type === "report" && favorite.member_id === memberId).map(favorite => favorite.source_id)), [favorites, memberId]);
  const activeReportResource = useMemo<ReportContextResource | null>(() => {
    const report = selectedReport ?? reports.find(report => report.report_id === selectedReportId);
    return report ? reportContextResourceFromReport(report) : null;
  }, [reports, selectedReport, selectedReportId]);
  const { favoriteReports, toggleReportFavorite } = createReportFavoriteActions({
    memberId, favoritingReport, favoritedReportIds, setActionError, setActionMessage,
    setFavoritingReport, isCurrentScope, setFavorites, selectedReportId, selectedReport, reportFavorite,
  });

  return {
    reportSaveKey, memberId, canEdit, reportImportMimeTypes, reportUploadUnavailableReason,
    retryAttachmentCapabilities: attachmentCapabilities.retryAttachmentCapabilities,
    attachmentCapabilitiesError: attachmentCapabilities.attachmentCapabilitiesError,
    REPORT_TYPES, actionError, actionMessage,
    ...detailState, ...sourceState, ...mutationState, ...analysisState, ...collectionState,
    addSelectedReportSources: controllers.mutation.addSelectedReportSources,
    addSelectedReportLabItem: controllers.mutation.addSelectedReportLabItem,
    allReportIds, reportFavorited: Boolean(reportFavorite), activeReportResource,
    analyzeSelectedReport: controllers.analysis.analyzeSelectedReport,
    clearActionFeedback: () => { setActionError(""); setActionMessage(""); },
    clearSourcePreview: controllers.source.clearSourcePreview,
    createManualReport: controllers.collection.createManualReport,
    deleteSelectedReportAnalysis: controllers.mutation.deleteSelectedReportAnalysis,
    deleteSelectedReportLabItem: controllers.mutation.deleteSelectedReportLabItem,
    deleteReports: controllers.collection.deleteReports,
    deleteSelectedReport: controllers.collection.deleteSelectedReport,
    favoritingReport, favoriteReports, favoritedReportIds, invalidateReportData,
    listError, listLoading, loadReports,
    openReport: controllers.detail.open, openSourceFile: controllers.source.openSourceFile,
    reports, reportQuery, setReportQuery, reportAfterDate, setReportAfterDate, reportBeforeDate, setReportBeforeDate,
    retryLatestAnalysis: controllers.analysis.retryLatestAnalysis,
    selectedReportTypes,
    setDetailVisible: (visible: boolean) => visible ? controllers.detail.show() : controllers.detail.hide(),
    total: reports.length,
    toggleReportType: (type: ReportType) => setSelectedReportTypes(current => {
      const next = new Set(current);
      if (next.has(type)) next.delete(type); else next.add(type);
      return REPORT_TYPES.filter(type => next.has(type));
    }),
    selectReportTypes: (types: ReportType[]) => setSelectedReportTypes(REPORT_TYPES.filter(type => types.includes(type))),
    toggleReportFavorite, updateSelectedReportField: controllers.mutation.updateSelectedReportField,
    uploadBlocked: !canEdit || Boolean(reportUploadUnavailableReason), uploadErrors, setUploadErrors,
  };
}

export type ReportWorkspaceState = ReturnType<typeof useReportWorkspace>;
