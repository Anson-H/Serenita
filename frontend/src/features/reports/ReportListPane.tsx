import { ListSelectionSlot } from "../../components/ListSelectionSlot";
import { navigationLabels } from "../../components/navigationLabels";
import { EmptyState } from "../../components/EmptyState";
import type { HTMLAttributes } from "react";
import {
  useEffect
} from "react";
import { createPortal } from "react-dom";
import { GroupedList } from "../../components/GroupedList";
import { DateField } from "../../components/DateField";
import { useListContextMenu } from "../../components/useListContextMenu";
import { useActiveScope } from "../../utils/useActiveScope";
import { useScopedState } from "../../utils/useScopedState";
import { useReportSelection } from "./useReportSelection";

import type { ReportSummary } from "../../api/client";
import {
  AlertIcon,
  CalendarIcon,
  FilterIcon,
  SearchIcon,
  CheckIcon,
  ChevronRightIcon,
  ListChecksIcon,
  PlusIcon,
  StarIcon,
  TrashIcon
} from "../../components/icons";
import { MultiSelectPopover } from "../../components/MultiSelectPopover";
import { SelectAllButton } from "../../components/SelectAllButton";
import { ListSelectionBar } from "../../components/ListSelectionBar";
import { ListCount } from "../../components/ListCount";
import { ListBulkActions } from "../../components/ListBulkActions";
import {
  reportDisplayTitle,
  reportListDateHeading
} from "./reportPresentation";
import type { ReportWorkspaceState } from "./useReportWorkspace";

function dateKey(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value.slice(0, 10) || "unknown";
  }
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function reportsGroupedByDate(reports: ReportSummary[]) {
  const sorted = [...reports].sort((left, right) => {
    const leftTime = new Date(left.report_time).getTime();
    const rightTime = new Date(right.report_time).getTime();
    if (Number.isNaN(leftTime) || Number.isNaN(rightTime)) {
      return right.report_time.localeCompare(left.report_time);
    }
    return rightTime - leftTime;
  });
  const groups = new Map<string, ReportSummary[]>();
  for (const report of sorted) {
    const key = dateKey(report.report_time);
    const group = groups.get(key) ?? [];
    group.push(report);
    groups.set(key, group);
  }
  return [...groups.entries()].map(([key, items]) => ({ key, items }));
}

function ReportTimelineItem({
  active,
  rowInteractions,
  onOpen,
  onToggleSelection,
  report,
  selected,
  selectionMode
}: {
  active: boolean;
  rowInteractions: HTMLAttributes<HTMLLIElement>;
  onOpen: () => void;
  onToggleSelection: () => void;
  report: ReportSummary;
  selected: boolean;
  selectionMode: boolean;
}) {
  const title = reportDisplayTitle(report);
  const rowClassName = [
    "report-timeline-row",
    active && !selectionMode ? "active" : "",
    selectionMode ? "selection-mode" : ""
  ].filter(Boolean).join(" ");

  return (
    <li
      className={rowClassName}
      onClick={() => {
        if (selectionMode) onToggleSelection();
      }}
      {...rowInteractions}
    >
      {selectionMode ? (
        <button
          aria-label={`${selected ? "取消选择" : "选择"}医疗报告：${title}`}
          aria-pressed={selected}
          className="report-selection-toggle selection-check-control"
          data-interaction-owner="row"
          onClick={(event) => {
            event.stopPropagation();
            onToggleSelection();
          }}
          type="button"
        >
          {selected ? <CheckIcon className="report-selection-check selection-check-icon" /> : null}
        </button>
      ) : null}
      <button
        aria-current={active && !selectionMode ? "page" : undefined}
        aria-label={selectionMode ? `${selected ? "取消选择" : "选择"}医疗报告：${title}` : `打开医疗报告：${title}`}
        className="report-timeline-item"
        data-interaction-owner="row"
        onClick={(event) => {
          event.stopPropagation();
          if (selectionMode) onToggleSelection();
          else onOpen();
        }}
        type="button"
      >
        <span className="report-timeline-copy">
          <strong>{title}</strong>
        </span>
        <span className="report-timeline-meta">
          {report.flagged_count > 0 ? (
            <span aria-label="存在异常指标" className="report-timeline-alert" title="存在异常指标">
              <AlertIcon className="report-timeline-alert-icon" />
            </span>
          ) : null}
        </span>
        <span aria-hidden="true" className="report-timeline-chevron">
          <ChevronRightIcon className="report-timeline-chevron-icon" />
        </span>
      </button>
    </li>
  );
}

export function ReportListPane({
  onRequestCreate,
  workspace
}: {
  onRequestCreate: () => void;
  workspace: ReportWorkspaceState;
}) {
  const isCurrentScope = useActiveScope(workspace.memberId);
  const [batchBusy, setBatchBusy] = useScopedState(false, isCurrentScope);
  const [selectedReportIds, setSelectedReportIds] = useReportSelection(workspace.memberId);
  const [selectionMode, setSelectionMode] = useScopedState(false, isCurrentScope);
  const [filterMode, setFilterMode] = useScopedState<"type" | "search" | "date">("type", isCurrentScope);
  useEffect(() => { setBatchBusy(false); setSelectionMode(false); }, [workspace.memberId]);
  const { contextMenu, menuRef: contextMenuRef, closeContextMenu, rowProps, onMenuKeyDown } =
    useListContextMenu({ enabled: !selectionMode, scope: `reports:${workspace.memberId}` });
  const dateGroups = reportsGroupedByDate(workspace.reports);
  const allReportTypesSelected = workspace.selectedReportTypes.length === workspace.REPORT_TYPES.length;
  const contextReport = contextMenu
    ? workspace.reports.find((report) => report.report_id === contextMenu.id) ?? null
    : null;

  useEffect(() => {
    const availableReportIds = new Set(workspace.allReportIds);
    const visibleReportIds = new Set(workspace.reports.map((report) => report.report_id));
    setSelectedReportIds((current) => {
      const remaining = new Set([...current].filter((reportId) => availableReportIds.has(reportId)));
      if (remaining.size === current.size) return current;
      if (!remaining.size) setSelectionMode(false);
      return remaining;
    });
    if (contextMenu && !visibleReportIds.has(contextMenu.id)) closeContextMenu(false);
  }, [workspace.allReportIds, workspace.reports, contextMenu, closeContextMenu]);

  function openReport(report: ReportSummary) {
    void workspace.openReport(report.report_id);
  }

  function toggleReportSelection(reportId: string) {
    setSelectedReportIds((current) => {
      const next = new Set(current);
      if (next.has(reportId)) next.delete(reportId);
      else next.add(reportId);
      return next;
    });
  }

  function beginSelection(reportId: string) {
    closeContextMenu(false);
    setSelectionMode(true);
    setSelectedReportIds(new Set([reportId]));
  }

  function cancelSelection() {
    setSelectionMode(false);
    setSelectedReportIds(new Set());
  }

  async function favoriteSelection() {
    const reportIds = [...selectedReportIds];
    if (!reportIds.length || batchBusy) return;
    setBatchBusy(true);
    try {
      const failedReportIds = await workspace.favoriteReports(reportIds);
      if (!isCurrentScope()) return;
      if (failedReportIds.length) setSelectedReportIds(new Set(failedReportIds));
      else cancelSelection();
    } finally {
      setBatchBusy(false);
    }
  }

  async function deleteSelection() {
    const reportIds = [...selectedReportIds];
    if (!reportIds.length || batchBusy) return;
    setBatchBusy(true);
    try {
      const failedReportIds = await workspace.deleteReports(reportIds);
      if (!isCurrentScope()) return;
      if (failedReportIds.length) setSelectedReportIds(new Set(failedReportIds));
      else cancelSelection();
    } finally {
      setBatchBusy(false);
    }
  }

  const contextMenuPortal = contextMenu && contextReport && typeof document !== "undefined"
    ? createPortal(
      <GroupedList
        aria-label={`${reportDisplayTitle(contextReport)} 的医疗报告操作`}
        className="context-action-menu scroll-balanced report-context-menu"
        onKeyDown={onMenuKeyDown}
        ref={contextMenuRef}
        role="menu"
        style={{ left: contextMenu.x, top: contextMenu.y }}
        density="standard"
      >
        <button onClick={() => beginSelection(contextReport.report_id)} role="menuitem" type="button">
          <ListChecksIcon className="context-action-menu-icon" />
          <span>多选</span>
        </button>
        <button
          onClick={() => {
            closeContextMenu();
            void workspace.favoriteReports([contextReport.report_id]);
          }}
          role="menuitem"
          type="button"
        >
          <StarIcon
            className="context-action-menu-icon"
            filled={workspace.favoritedReportIds.has(contextReport.report_id)}
          />
          <span>收藏</span>
        </button>
        <button
          className="control control--secondary control--danger context-action-menu-removal report-context-delete removal-action-control"
          onClick={() => {
            closeContextMenu(false);
            void workspace.deleteReports([contextReport.report_id]);
          }}
          role="menuitem"
          type="button"
        >
          <TrashIcon className="context-action-menu-icon" />
          <span>删除</span>
        </button>
      </GroupedList>,
      document.body
    )
    : null;

  return (
    <section
      aria-label="医疗报告列表"
      className="report-library"
      data-selection-mode={selectionMode ? "true" : undefined}
    >
      <div className="report-library-controls">
        <ListSelectionSlot active={selectionMode} selection={<ListSelectionBar summary={`已选择 ${selectedReportIds.size} 份医疗报告`} label="医疗报告多选" cancelLabel="退出医疗报告多选" busy={batchBusy} onCancel={cancelSelection}>
              <SelectAllButton
                disabled={batchBusy || workspace.listLoading}
                ids={workspace.reports.map((report) => report.report_id)}
                onChange={setSelectedReportIds}
                scopeLabel="当前筛选结果中的医疗报告"
                selectedIds={selectedReportIds}
              />
          </ListSelectionBar>}>
        <div className="report-filter-bar" data-mode={filterMode}>
        {filterMode === "type" ? <MultiSelectPopover
          allSelectedLabel="全部医疗报告类型"
          ariaLabel="按医疗报告类型筛选"
          className="report-filter-picker multi-select-filter-picker"
          emptySelectedLabel="未选择医疗报告类型"
          menuWidth="trigger" menuAlign="start" interactionOwner="self"
          onChange={workspace.selectReportTypes}
          options={workspace.REPORT_TYPES.map((type) => ({
            label: type,
            value: type
          }))}
          selectedCountLabel={(count) => `已选 ${count} 种医疗报告类型`}
          values={workspace.selectedReportTypes}
        /> : <button type="button" className="control control--icon" aria-label="展开类型筛选栏" title="展开类型筛选栏"
          onClick={() => setFilterMode("type")}><FilterIcon /></button>}
        {filterMode === "search" ? <input aria-label="搜索医疗报告" placeholder="搜索名称或机构" type="search" value={workspace.reportQuery}
          onChange={event => workspace.setReportQuery(event.target.value)} /> :
          <button type="button" className="control control--icon" aria-label="展开搜索栏" title="展开搜索栏"
            onClick={() => setFilterMode("search")}><SearchIcon /></button>}
        {filterMode === "date" ? <div className="date-range-filter" role="group" aria-label="日期范围">
          <DateField compact emptyLabel="不限" emptyOptionLabel="不限" label="起始日期" value={workspace.reportAfterDate} onChange={workspace.setReportAfterDate} />
          <span aria-hidden="true">至</span>
          <DateField compact emptyLabel="不限" emptyOptionLabel="不限" label="结束日期" value={workspace.reportBeforeDate} onChange={workspace.setReportBeforeDate} />
        </div> : <button type="button" className="control control--icon" aria-label="展开日期范围栏" title="展开日期范围栏"
          onClick={() => setFilterMode("date")}><CalendarIcon /></button>}
        </div>
        </ListSelectionSlot>
      </div>

      <div
        aria-busy={workspace.listLoading ? "true" : "false"}
        className={`report-library-scroll scroll-content${!workspace.listLoading && !workspace.listError && !dateGroups.length ? " empty" : ""}`}
        id="report-archive-list"
      >
        {workspace.listLoading && !workspace.reports.length ? (
          <div className="report-list-skeleton" aria-label="正在加载医疗报告">
            {[0, 1, 2, 3].map((item) => <span key={item} />)}
          </div>
        ) : dateGroups.length ? (
          <div className="report-timeline">
            {dateGroups.map((group) => (
              <section className="report-date-group" key={group.key}>
                <h2 className="report-date-heading">
                  {reportListDateHeading(group.items[0].report_time)}
                </h2>
                <GroupedList as="ul" className="report-date-list" density="standard">
                  {group.items.map((report) => (
                    <ReportTimelineItem
                      active={workspace.selectedReportId === report.report_id}
                      key={report.report_id}
                      rowInteractions={rowProps<HTMLLIElement>(report.report_id, ".report-timeline-item")}
                      onOpen={() => openReport(report)}
                      onToggleSelection={() => toggleReportSelection(report.report_id)}
                      report={report}
                      selected={selectedReportIds.has(report.report_id)}
                      selectionMode={selectionMode}
                    />
                  ))}
                </GroupedList>
              </section>
            ))}
          </div>
        ) : workspace.listError ? null : (
          <EmptyState className="report-list-empty" title={workspace.selectedReportTypes.length === 0
                ? "未选择医疗报告类型"
                  : workspace.reportQuery.trim() || workspace.reportAfterDate || workspace.reportBeforeDate
                    ? "没有匹配的医疗报告"
                  : allReportTypesSelected
                  ? "暂无医疗报告"
                  : "暂无该类型医疗报告"}
            description={workspace.selectedReportTypes.length === 0
                ? "在筛选选择框中选择医疗报告类型后可查看对应医疗报告。"
                : workspace.reportQuery.trim() || workspace.reportAfterDate || workspace.reportBeforeDate
                  ? "请调整搜索内容或日期范围。"
                  : "可以文字录入，也可以上传文件"}
            />
        )}
        {!workspace.listLoading && !workspace.listError && workspace.total > 0 ? (
          <ListCount total={workspace.total} unit="份" label="医疗报告" />
        ) : null}
      </div>

      {!selectionMode ? (
        <div className="list-floating-actions report-library-floating-actions">
          <button
            aria-label={navigationLabels.createReport}
            className="control control--primary primary-action creation-action-button control-primary"
            disabled={!workspace.canEdit || workspace.creating}
            onClick={onRequestCreate}
            type="button"
          >
            <PlusIcon />
            <span>{workspace.creating ? "创建中" : navigationLabels.createReport}</span>
          </button>
        </div>
      ) : null}

      {selectionMode ? <ListBulkActions label="批量医疗报告操作" inset>
        <button className="control control--compact control--secondary" disabled={!selectedReportIds.size || batchBusy} onClick={() => void favoriteSelection()} type="button"><StarIcon /><span>收藏</span></button>
        <button className="control control--compact control--secondary control--danger removal-action-control" disabled={!workspace.canEdit || !selectedReportIds.size || batchBusy} onClick={() => void deleteSelection()} type="button"><TrashIcon /><span>删除</span></button>
      </ListBulkActions> : null}
      {contextMenuPortal}
    </section>
  );
}
