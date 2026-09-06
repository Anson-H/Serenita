import type {
  ReportSummary
} from "../../api/client";
import { localDateTimeInputValue } from "../../utils/localTime";

export function reportDisplayTitle(
  report: Pick<ReportSummary, "report_name" | "report_type">
) {
  const reportName = report.report_name.trim();
  if (!reportName || reportName === report.report_type) {
    return report.report_type;
  }
  const typePrefix = `${report.report_type} - `;
  return reportName.startsWith(typePrefix) ? reportName : `${typePrefix}${reportName}`;
}

export function reportListDateHeading(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value || "时间未识别";
  }
  return `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日`;
}

export function formatReportDate(value: string, includeTime = false) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value || "时间未识别";
  }
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    ...(includeTime
      ? {
        hour: "2-digit" as const,
        minute: "2-digit" as const,
        hour12: false
      }
      : {})
  }).format(date);
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
