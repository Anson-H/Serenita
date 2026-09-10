import type { ConversationResourceState } from "../../api/client";
import { GroupedList } from "../../components/GroupedList";
import { ChevronDownIcon, ChevronRightIcon } from "../../components/icons";
import { formatDateOnly } from "../../utils/localTime";
import { RelatedReportRows, type RelatedReportReference } from "./RelatedReports";
import { RESOURCE_LABELS, RESOURCE_RELATIONSHIPS, relatedResourcePath, resourceKey, type RelatedResourceReference } from "./relatedResources";

export function RelatedContent({ messageId, reports, resources, resourceStates, resourceStateByReportId, onOpenReport }: {
  messageId: string; reports: RelatedReportReference[]; resources: RelatedResourceReference[];
  resourceStates: ConversationResourceState[];
  resourceStateByReportId: ReadonlyMap<string, ConversationResourceState>;
  onOpenReport: (reportId: string) => void | Promise<void>;
}) {
  if (!reports.length && !resources.length) return null;
  const titleId = `related-content-${messageId}`;
  const states = new Map(resourceStates.map(state => [resourceKey(state), state]));
  const count = resources.length ? `${reports.length + resources.length} 项` : `${reports.length} 份医疗报告`;
  const entries = [
    ...reports.map(item => ({ kind: "report" as const, item })),
    ...resources.map(item => ({ kind: "resource" as const, item })),
  ];
  const order = (relationship: string) => relationship === "created" ? 0 : relationship === "deleted" ? 1 : relationship === "read" ? 3 : 2;
  entries.sort((a, b) => order(a.item.relationship) - order(b.item.relationship));
  return <details aria-labelledby={titleId} className="related-reports assistant-turn-disclosure root-disclosure-list">
    <summary className="related-reports-summary root-disclosure-toggle">
      <span className="related-reports-title" id={titleId}>相关内容</span>
      <span className="related-reports-count">{count}</span>
      <ChevronDownIcon className="assistant-turn-disclosure-chevron" />
    </summary>
    <GroupedList as="ul" className="related-report-list scroll-balanced root-disclosure-content" density="standard">
      {entries.map(entry => {
        if (entry.kind === "report") return <RelatedReportRows key={resourceKey(entry.item.resource)} reports={[entry.item]} resourceStateByReportId={resourceStateByReportId} onOpenReport={onOpenReport} />;
        const item = entry.item;
        const state = states.get(resourceKey(item));
        const unavailable = state?.availability === "deleted" || state?.availability === "forbidden";
        const status = state?.availability === "deleted" ? "已删除" : state?.availability === "forbidden" ? "无权访问"
          : !state ? "状态待刷新" : state.current_created_at !== item.created_at || state.current_updated_at !== item.updated_at ? "已更新" : "";
        const label = `${RESOURCE_RELATIONSHIPS[item.relationship]}：${item.name}${status ? `，${status}` : ""}`;
        const copy = <>
          <span className="related-report-relation">{RESOURCE_RELATIONSHIPS[item.relationship]}</span>
          <span className="related-report-summary">
            {item.recorded_on ? <><time className="related-report-time" dateTime={item.recorded_on}>{formatDateOnly(item.recorded_on)}</time><span className="related-report-separator">-</span></> : null}
            <span className="related-report-type">{RESOURCE_LABELS[item.resource_type]}</span>
            <span className="related-report-separator">-</span><span className="related-report-name">{item.name}</span>
          </span>
          <span className="related-report-trailing">
            {status ? <span className="compact-control-bar related-report-state">{status}</span> : null}
            {!unavailable ? <ChevronRightIcon className="related-report-chevron" /> : null}
          </span>
        </>;
        return <li className="related-report-item root-disclosure-row" key={resourceKey(item)}>
          {unavailable ? <button aria-label={label} className="related-report-row" data-interaction-owner="row" data-disabled="true" disabled type="button">{copy}</button>
            : <a aria-label={label} className="related-report-row" data-interaction-owner="row" href={relatedResourcePath(item)}>{copy}</a>}
        </li>;
      })}
    </GroupedList>
  </details>;
}
