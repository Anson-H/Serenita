import type { Favorite } from "../../api/types";
import { formatLocalDate } from "../../utils/localTime";

export function favoritePreview(favorite: Favorite) {
  const lines = favorite.content_summary.split(/\r?\n/);
  return lines
    .filter(line => line.trim() !== `# ${favorite.title}`)
    .filter(line => favorite.source_type !== "report" || !/^- \*\*(医疗报告类型|医疗报告时间|就诊机构)\*\*：/.test(line))
    .join(" ")
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/(^|\s)#{1,6}\s+/g, "$1")
    .replace(/[*`_~]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

// The report snapshot has a generated header followed by the saved report content.
// Project only that header; leave all medical content verbatim for Markdown rendering.
export function favoriteReportContent(favorite: Favorite) {
  const content = favorite.content_snapshot ?? favorite.content_summary;
  if (favorite.source_type !== "report") return { content, fields: [] };
  const prefix = `# ${favorite.title}\n\n`;
  if (!content.startsWith(prefix)) return { content, fields: [] };
  const header = content.slice(prefix.length).match(
    /^- \*\*医疗报告类型\*\*：([^\n]*)\n- \*\*医疗报告时间\*\*：([^\n]*)\n- \*\*就诊机构\*\*：([^\n]*)(?:\n|$)/
  );
  if (!header) return { content, fields: [] };
  return {
    content: content.slice(prefix.length + header[0].length).trimStart(),
    fields: [
      { label: "医疗报告类型", value: header[1] },
      { label: "医疗报告时间", value: readableReportTime(header[2]) },
      { label: "就诊机构", value: header[3] }
    ]
  };
}

function readableReportTime(value: string) {
  return formatLocalDate(value, true);
}
