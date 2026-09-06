import {
  type ReportDetail
} from "../../api/client";
import { reportListDateHeading } from "./reportPresentation";

export type ReportAnalysisMode = "initial" | "rewrite";

export function reportAnalysisPrompt(
  report: ReportDetail,
  mode: ReportAnalysisMode
) {
  const target = `${reportListDateHeading(report.report_time)}的${report.report_name.trim()}${report.report_type}`;
  return mode === "rewrite"
    ? `对${target}重新解读`
    : `对${target}进行报告解读`;
}
