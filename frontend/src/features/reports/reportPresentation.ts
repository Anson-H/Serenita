import type {
  ReportSummary
} from "../../api/client";
import { formatLocalDate, localDateTimeInputValue } from "../../utils/localTime";

export function reportDisplayTitle(
  report: Pick<ReportSummary, "report_name" | "report_type">
) {
  return report.report_name.trim() || report.report_type;
}

export function reportListDateHeading(value: string) {
  return formatLocalDate(value) || "时间未识别";
}

export function formatReportDate(value: string, includeTime = false) {
  return formatLocalDate(value, includeTime) || "时间未识别";
}

export function reportDateTimeInputValue(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value.slice(0, 16);
  }
  return localDateTimeInputValue(date);
}

export function sourceFileName(file: {
  filename: string;
}) {
  return file.filename;
}
