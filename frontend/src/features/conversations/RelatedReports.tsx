import type {
  ConversationResourceState,
  ReportContextResource
} from "../../api/client";
import { ChevronRightIcon } from "../../components/icons";
import {
  reportReferenceStatus,
  reportResourceKey
} from "../reports/reportContext";
import { formatReportDate } from "../reports/reportPresentation";

export type RelatedReportRelationship =
  | "created"
  | "read"
  | "modified"
  | "reclassified"
  | "analysis_written"
  | "source_linked"
  | "deleted";

export type RelatedReportReference = {
  relationship: RelatedReportRelationship;
  resource: ReportContextResource;
};

const RELATIONSHIP_LABELS: Record<RelatedReportRelationship, string> = {
  created: "创建",
  read: "查阅",
  modified: "更新",
  reclassified: "重新分类",
  analysis_written: "更新解读结果",
  source_linked: "关联来源",
  deleted: "删除"
};

type RelatedReportsProps = {
  onOpenReport: (reportId: string) => void | Promise<void>;
  reports: RelatedReportReference[];
  resourceStateByReportId: ReadonlyMap<string, ConversationResourceState>;
};

function RelatedReportCopy({ item }: { item: RelatedReportReference }) {
  const report = item.resource;
  return (
    <>
      <span className="related-report-relation">
        {RELATIONSHIP_LABELS[item.relationship]}
      </span>
      <span className="related-report-summary">
        <time className="related-report-time" dateTime={report.report_time}>
          {formatReportDate(report.report_time, true)}
        </time>
        <span aria-hidden="true" className="related-report-separator">-</span>
        <span className="related-report-type">{report.report_type}</span>
        <span aria-hidden="true" className="related-report-separator">-</span>
        <span className="related-report-name">{report.report_name}</span>
      </span>
    </>
  );
}

export function RelatedReportRows({
  onOpenReport,
  reports,
  resourceStateByReportId
}: RelatedReportsProps) {
  if (!reports.length) {
    return null;
  }

  return (
    <>
        {reports.map((item) => {
          const report = item.resource;
          const status = reportReferenceStatus(
            report,
            resourceStateByReportId.get(reportResourceKey(report))
          );
          const trailing = (
            <span className="related-report-trailing">
              {status === "unknown" ? <span className="compact-control-bar related-report-state">状态待刷新</span> : null}
              {status === "modified" ? (
                <span className="compact-control-bar related-report-state">已更新</span>
              ) : null}
              {(status === "deleted" || status === "forbidden") ? (
                <span className="compact-control-bar related-report-state">{status === "forbidden" ? "无权访问" : "已删除"}</span>
              ) : (
                <ChevronRightIcon className="related-report-chevron" />
              )}
            </span>
          );
          return (
            <li
              className="related-report-item root-disclosure-row"
              key={reportResourceKey(report)}
            >
              {(status === "deleted" || status === "forbidden") ? (
                <button
                  aria-label={`${RELATIONSHIP_LABELS[item.relationship]}：${report.report_name}，${status === "forbidden" ? "无权访问" : "医疗报告已删除"}`}
                  className="related-report-row"
                  data-interaction-owner="row"
                  data-disabled="true"
                  disabled
                  type="button"
                >
                  <RelatedReportCopy item={item} />
                  {trailing}
                </button>
              ) : (
                <button
                  aria-label={`${RELATIONSHIP_LABELS[item.relationship]}：${report.report_name}${status === "modified" ? "，当前医疗报告已更新" : ""}`}
                  className="related-report-row"
                  data-interaction-owner="row"
                  onClick={() => void onOpenReport(report.resource_id)}
                  type="button"
                >
                  <RelatedReportCopy item={item} />
                  {trailing}
                </button>
              )}
            </li>
          );
        })}
    </>
  );
}
