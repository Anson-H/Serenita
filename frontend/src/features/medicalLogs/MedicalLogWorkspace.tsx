import { ListSelectionSlot } from "../../components/ListSelectionSlot";
import { navigationLabels } from "../../components/navigationLabels";
import { EmptyState } from "../../components/EmptyState";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { ApiRequestError } from "../../api/request";
import type { Member } from "../../api/memberApi";
import { deleteMedicalLog, fetchMedicalLogs, getMedicalLog, type MedicalLog, type MedicalLogFilters, type MedicalLogSummary } from "../../api/medicalLogApi";
import { healthPathForMember, medicalLogPath, medicationPath, medicalLogIdFromPath, type RoutePath } from "../../app/routes";
import { GroupedList } from "../../components/GroupedList";
import { PlusIcon, ChevronRightIcon, SearchIcon, CalendarIcon } from "../../components/icons";
import { WorkspaceToolbar } from "../../components/WorkspaceToolbar";
import { HealthMemberOverview } from "../members/HealthMemberOverview";
import { MemberInformationPanel } from "../members/MemberInformationPanel";
import { saveBeforeNavigation } from "../../utils/pendingNavigation";
import { MedicalLogEditor, type MedicalLogEditorHandle } from "./MedicalLogEditor";
import { useListDeleteActions } from "../../components/useListDeleteActions";
import { ListCount } from "../../components/ListCount";
import { useStatusNotification } from "../../components/StatusNotificationCenter";
import { useActiveScope } from "../../utils/useActiveScope";
import { DateField } from "../../components/DateField";
import { formatDateOnly } from "../../utils/localTime";
import "../../styles/medical-logs.css";
import { medicalLogPosition, saveMedicalLogPosition } from "./medicalLogWorkspaceState";

export function MedicalLogWorkspace({ member, route, navigate, sidebarToggle }: {
  member: Member; route: RoutePath; navigate: (path: RoutePath) => void; sidebarToggle: ReactNode;
}) {
  const logId = medicalLogIdFromPath(route);
  const [logs, setLogs] = useState<MedicalLogSummary[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [total, setTotal] = useState(0);
  const [loadingMore, setLoadingMore] = useState(false);
  const [selected, setSelected] = useState<MedicalLog | null>(null);
  const [creating, setCreating] = useState(false);
  const [information, setInformation] = useState(false);
  const [filters, setFilters] = useState<MedicalLogFilters>(() => medicalLogPosition(member.member_id).filters);
  const [filterMode, setFilterMode] = useState<"search" | "date">("search");
  const [catalogError, setCatalogError] = useState("");
  const [detailError, setDetailError] = useState("");
  const [targetMissing, setTargetMissing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refresh, setRefresh] = useState(0);
  const [deleteError, setDeleteError] = useState("");
  const editor = useRef<MedicalLogEditorHandle>(null);
  const isCurrent = useActiveScope(member.member_id);
  const currentLogId = useRef(logId);
  currentLogId.current = logId;
  useStatusNotification(deleteError, { id: "medical-log-delete-error", title: "健康日记未删除", tone: "error" });
  const detail = useRef<HTMLElement | null>(null);
  const sequence = useRef(0);
  const active = useRef(true);
  const list = useRef<HTMLDivElement>(null);
  const savedPosition = useRef(medicalLogPosition(member.member_id));
  const restorePosition = useRef(true);
  savedPosition.current.filters = filters;
  useEffect(() => () => saveMedicalLogPosition(member.member_id, savedPosition.current), [member.member_id]);
  useEffect(() => {
    if (!loading && restorePosition.current && list.current) {
      list.current.scrollTop = savedPosition.current.scrollTop;
      restorePosition.current = false;
    }
  }, [loading]);
  useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);
  useEffect(() => {
    const reload = () => setRefresh(value => value + 1);
    const visible = () => { if (document.visibilityState === "visible") reload(); };
    window.addEventListener("focus", reload); document.addEventListener("visibilitychange", visible);
    return () => { window.removeEventListener("focus", reload); document.removeEventListener("visibilitychange", visible); };
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    const token = ++sequence.current;
    setLoading(true);
    setNextCursor(null);
    setLoadingMore(false);
    const timer = window.setTimeout(() => {
      void fetchMedicalLogs(member.member_id, filters, controller.signal).then(result => {
        if (token === sequence.current) { setLogs(result.medical_logs); setTotal(result.total ?? result.medical_logs.length); setNextCursor(result.next_cursor ?? null); setCatalogError(""); }
      }).catch(cause => {
        if (!controller.signal.aborted && token === sequence.current) { setLogs([]); setCatalogError(cause instanceof Error ? cause.message : "健康日记读取失败。"); }
      }).finally(() => { if (token === sequence.current) setLoading(false); });
    }, 150);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [member.member_id, filters, refresh]);
  useEffect(() => {
    if (!logId) { setSelected(null); setDetailError(""); setTargetMissing(false); return; }
    setCreating(false); setInformation(false);
    const controller = new AbortController();
    void getMedicalLog(member.member_id, logId, controller.signal).then(result => {
      if (!controller.signal.aborted) { setSelected(result.medical_log); setDetailError(""); setTargetMissing(false); }
    }).catch(cause => {
      if (!controller.signal.aborted) { setDetailError(cause instanceof Error ? cause.message : "健康日记读取失败。"); setTargetMissing(cause instanceof ApiRequestError && cause.status === 404); }
    });
    return () => controller.abort();
  }, [member.member_id, logId, refresh]);

  async function loadMore() {
    if (!nextCursor || loading || loadingMore) return;
    const token = sequence.current;
    setLoadingMore(true);
    try {
      const result = await fetchMedicalLogs(member.member_id, { ...filters, cursor: nextCursor });
      if (!active.current || !isCurrent() || token !== sequence.current) return;
      setLogs(current => [...current, ...result.medical_logs.filter(log => !current.some(item => item.medical_log_id === log.medical_log_id))]);
      setTotal(result.total);
      setNextCursor(result.next_cursor);
      setCatalogError("");
    } catch (cause) {
      if (active.current && isCurrent() && token === sequence.current) setCatalogError(cause instanceof Error ? cause.message : "后续日记读取失败，请重试。");
    } finally {
      if (active.current && token === sequence.current) setLoadingMore(false);
    }
  }

  async function open(id?: string) {
    if (!await saveBeforeNavigation()) return;
    setCreating(false); setInformation(false);
    navigate(medicalLogPath(member.member_id, id));
  }
  function saved(log: MedicalLog) {
    if (!active.current) return;
    setSelected(log); setRefresh(value => value + 1);
    if (creating) { setCreating(false); navigate(medicalLogPath(member.member_id, log.medical_log_id)); }
  }
  function deleted(id: string) {
    if (!isCurrent()) return;
    setLogs(value => value.filter(log => log.medical_log_id !== id));
    setRefresh(value => value + 1);
    if (currentLogId.current === id) {
      setSelected(null); navigate(medicalLogPath(member.member_id));
    }
  }
  const actions = useListDeleteActions({
    insetActions: true,
    scope: `medical-logs:${member.member_id}`, enabled: member.can_edit, label: "健康日记", countLabel: "条健康日记",
    entries: logs.map(log => ({ id: log.medical_log_id, name: log.title })),
    onDelete: async ids => {
      const failed: string[] = [];
      setDeleteError("");
      for (const id of ids) {
        if (!isCurrent()) return ids;
        try {
          if (editor.current?.medicalLogId === id) {
            if (!await editor.current.remove()) failed.push(id);
          } else {
            await deleteMedicalLog(member.member_id, id);
            deleted(id);
          }
        } catch (cause) {
          failed.push(id);
          if (isCurrent()) setDeleteError(cause instanceof Error ? cause.message : "健康日记未删除。");
        }
      }
      return failed;
    }
  });
  const groups = new Map<string, MedicalLogSummary[]>();
  for (const log of logs) { const key = log.recorded_on; groups.set(key, [...(groups.get(key) ?? []), log]); }
  const current = selected?.medical_log_id === logId ? selected : null;
  return <section className="reports-workspace medical-logs-workspace" data-detail-open={creating || logId || information ? "true" : "false"}>
    <div className="report-browser-layout">
      <div className="report-library-column">
        <WorkspaceToolbar className="reports-list-toolbar" title={navigationLabels.health} showBack={false} leading={sidebarToggle} />
        <HealthMemberOverview member={member} informationOpen={information} section="medical-logs"
          onOpenInformation={async () => { if (await saveBeforeNavigation()) { setCreating(false); setInformation(true); } }}
          onSelectReports={() => navigate(healthPathForMember(member.member_id))}
          onSelectMedications={() => navigate(medicationPath(member.member_id))}
          onSelectMedicalLogs={async () => { if (information && await saveBeforeNavigation()) setInformation(false); }}
          reportArchive={<section className="report-library" aria-label="健康日记列表" data-selection-mode={actions.selectionMode ? "true" : undefined} onKeyDown={actions.onKeyDown}>
            <div className="report-library-controls">
            <ListSelectionSlot active={actions.selectionMode} selection={actions.heading}>
            <div className="medical-log-filters" data-mode={filterMode}>
              {filterMode === "search" ? <input aria-label="搜索健康日记" placeholder="搜索标题或内容" type="search" value={filters.query}
                onChange={event => setFilters(value => ({ ...value, query: event.target.value }))} /> :
                <button type="button" className="control control--icon" aria-label="展开搜索栏" title="展开搜索栏"
                  onClick={() => setFilterMode("search")}><SearchIcon /></button>}
              {filterMode === "date" ? <div className="date-range-filter" role="group" aria-label="日期范围">
                <DateField compact label="起始日期" emptyLabel="不限" emptyOptionLabel="不限" value={filters.after_date ?? null} onChange={date => setFilters(value => ({ ...value, after_date: date ?? undefined }))} />
                <span aria-hidden="true">至</span>
                <DateField compact label="结束日期" emptyLabel="不限" emptyOptionLabel="不限" value={filters.before_date ?? null} onChange={date => setFilters(value => ({ ...value, before_date: date ?? undefined }))} />
              </div> : <button type="button" className="control control--icon" aria-label="展开日期范围栏" title="展开日期范围栏"
                onClick={() => setFilterMode("date")}><CalendarIcon /></button>}
            </div>
            </ListSelectionSlot>
            </div>
            <div className={`report-library-scroll scroll-content${!logs.length ? " empty" : ""}`} ref={list} aria-busy={loading}
              onScroll={event => { savedPosition.current.scrollTop = event.currentTarget.scrollTop; }}>
              {logs.length ? <div className="report-timeline">
                {[...groups].map(([date, items]) => <section key={date} className="report-date-group"><h2 className="report-date-heading">{formatDateOnly(date)}</h2>
                  <GroupedList as="ul" density="standard" className="report-date-list">
                    {items.map(log => <li key={log.medical_log_id} className="report-timeline-row">
                      <button {...actions.rowProps(log.medical_log_id)} className="report-timeline-item medical-log-list-item" type="button" data-interaction-owner="row"
                        disabled={actions.busy} aria-haspopup={member.can_edit && !actions.selectionMode ? "menu" : undefined}
                        role={actions.selectionMode ? "checkbox" : undefined} aria-checked={actions.selectionMode ? actions.selected(log.medical_log_id) : undefined}
                        aria-current={!actions.selectionMode && logId === log.medical_log_id ? "page" : undefined}
                        onClick={() => actions.selectionMode ? actions.toggle(log.medical_log_id) : void open(log.medical_log_id)}>
                        {actions.indicator(log.medical_log_id)}
                        <span className="report-timeline-copy"><strong>{log.title}</strong><span className="medical-log-summary content-description">{log.summary}</span></span>
                        {!actions.selectionMode ? <ChevronRightIcon className="report-timeline-chevron-icon" /> : null}
                      </button>
                    </li>)}
                  </GroupedList>
                </section>)}
                <ListCount total={total} unit="条" label="健康日记" />
                {nextCursor ? <button type="button" className="control" disabled={loading || loadingMore} onClick={() => void loadMore()}>{loadingMore ? "正在读取…" : "加载更多健康日记"}</button> : null}
              </div> : <EmptyState role={loading ? "status" : undefined} title={loading ? "正在读取健康日记…" : catalogError || "没有匹配的健康日记"} />}
              {catalogError ? <div className="medical-log-read-error" role="alert">{logs.length ? <p>{catalogError}</p> : null}
                <button type="button" className="control" onClick={() => setRefresh(value => value + 1)}>重新读取</button></div> : null}
            </div>
            {member.can_edit && !actions.selectionMode ? <div className="list-floating-actions report-library-floating-actions">
              <button className="control control--primary creation-action-button" type="button" onClick={async () => {
                if (await saveBeforeNavigation()) { setInformation(false); setCreating(true); }
              }}><PlusIcon /><span>{navigationLabels.createLog}</span></button>
            </div> : null}
            {actions.toolbar}
          </section>} />
      </div>
      <div className="report-detail-column">
        {information ? <MemberInformationPanel member={member} panelRef={detail} onClose={() => setInformation(false)} /> : creating || current ?
          <MedicalLogEditor ref={editor} key={creating ? "new" : current!.medical_log_id} memberId={member.member_id} canEdit={member.can_edit && !targetMissing} readError={detailError} log={creating ? null : current}
            onSaved={saved} onDeleted={() => { if (current) deleted(current.medical_log_id); }}
            onClose={() => { setCreating(false); if (!creating) void open(); }} /> :
          <><WorkspaceToolbar className="reports-detail-toolbar" title={logs.find(log => log.medical_log_id === logId)?.title ?? "健康日记详情"} onBack={() => void open()} />
            <EmptyState title={logId ? detailError || "正在读取健康日记…" : "选择一条健康日记查看内容"} /></>}
      </div>
    </div>
    {actions.portal}
  </section>;
}
