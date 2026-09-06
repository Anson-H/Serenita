import { createRoot } from "react-dom/client";
import { RelatedReports, type RelatedReportReference } from "../../src/features/conversations/RelatedReports";
import { reportResourceStateMap } from "../../src/features/reports/reportContext";
import "../../src/styles/index.css";

const reports: RelatedReportReference[] = ["deleted", "forbidden", "available"].map(member => ({
  relationship: "read",
  resource: {
    resource_type: "report", resource_id: "same-report", member_id: member,
    report_name: member, report_type: "检验报告",
    report_time: "2026-09-05T10:00:00+08:00",
    captured_created_at: "2026-09-05T10:00:00+08:00",
    captured_updated_at: "2026-09-05T10:00:00+08:00"
  }
}));
const states = reportResourceStateMap((["deleted", "forbidden", "available"] as const).map(availability => ({
  resource_type: "report", resource_id: "same-report", member_id: availability, availability,
  current_created_at: "2026-09-05T10:00:00+08:00", current_updated_at: "2026-09-05T10:00:00+08:00"
})));
createRoot(document.getElementById("root")!).render(<RelatedReports
  messageId="historical-answer" reports={reports} resourceStateByReportId={states}
  onOpenReport={() => { document.body.dataset.opened = "true"; }}
/>);
