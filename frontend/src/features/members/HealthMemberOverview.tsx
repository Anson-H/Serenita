import type { ReactNode } from "react";
import { IdentityRowCopy } from "../../components/IdentityRowCopy";
import { type Member } from "../../api/memberApi";
import { DocumentFormatIcon, HealthRecordIcon, MedicationIcon, ReportScenarioIcon } from "../../components/icons";
import { MemberAvatar } from "./MemberAvatar";
import { memberDisplayName } from "./memberPresentation";
import { formatDateOnly } from "../../utils/localTime";

export function HealthMemberOverview({
  informationOpen,
  onOpenInformation,
  member,
  reportArchive,
  section = "reports",
  onSelectBodyMetrics,
  onSelectReports,
  onSelectMedicalLogs,
  onSelectMedications
}: {
  informationOpen: boolean;
  onOpenInformation: (source: HTMLButtonElement) => void;
  member: Member;
  reportArchive: ReactNode;
  section?: "reports" | "medical-logs" | "medications" | "body-metrics";
  onSelectBodyMetrics?: () => void;
  onSelectReports?: () => void;
  onSelectMedicalLogs?: () => void;
  onSelectMedications?: () => void;
}) {
  const displayName = memberDisplayName(member);
  const sexLabel = member.sex ? { male: "男", female: "女", other: "其他" }[member.sex] : null;
  const bloodTypeLabel = member.blood_type ? { a: "A 型", b: "B 型", ab: "AB 型", o: "O 型", other: "其他" }[member.blood_type] : null;
  return <div className="health-member-overview">
      <section className="identity-row health-member-detail-identity" aria-label={`${displayName}的健康档案概览`}
        data-current={informationOpen ? "true" : undefined} data-row-surface>
        <button aria-controls="member-information-detail" aria-current={informationOpen ? "page" : undefined}
          aria-label={`查看${displayName}的个人信息`}
          className="control control--ghost health-member-detail-open" data-interaction-owner="row" data-row-trigger
          onClick={event => onOpenInformation(event.currentTarget)} type="button" />
        <MemberAvatar />
        <IdentityRowCopy title={displayName} description={sexLabel || member.birth_date || bloodTypeLabel ? <span className="health-member-detail-metadata">
          {sexLabel ? <span aria-label={`性别：${sexLabel}`}>{sexLabel}</span> : null}
          {sexLabel && (member.birth_date || bloodTypeLabel) ? <span aria-hidden="true">·</span> : null}
          {member.birth_date ? <time aria-label={`出生日期：${formatDateOnly(member.birth_date)}`} dateTime={member.birth_date}>{formatDateOnly(member.birth_date)}</time> : null}
          {member.birth_date && bloodTypeLabel ? <span aria-hidden="true">·</span> : null}
          {bloodTypeLabel ? <span aria-label={`血型：${bloodTypeLabel}`}>{bloodTypeLabel}</span> : null}
        </span> : null}/>
      </section>
      <nav className="health-member-sections" aria-label="健康档案内容">
        <button className="control health-section-entry" type="button" aria-current={section === "body-metrics" ? "page" : undefined} onClick={onSelectBodyMetrics ?? (() => window.location.assign(`/health/${encodeURIComponent(member.member_id)}/body-metrics`))}>
          <span className="health-section-icon" aria-hidden="true"><ReportScenarioIcon /></span>
          <span className="health-section-label">身体指标</span>
        </button>
        <button aria-controls="health-member-report-archive" aria-current={section === "reports" ? "page" : undefined} onClick={onSelectReports}
          className="control health-section-entry" type="button">
          <span className="health-section-icon" aria-hidden="true"><HealthRecordIcon /></span>
          <span className="health-section-label">医疗报告</span>
        </button>
        <button aria-current={section === "medical-logs" ? "page" : undefined} onClick={onSelectMedicalLogs} className="control health-section-entry" type="button">
          <span className="health-section-icon" aria-hidden="true"><DocumentFormatIcon /></span>
          <span className="health-section-label">健康日记</span>
        </button>
        <button aria-current={section === "medications" ? "page" : undefined} onClick={onSelectMedications} className="control health-section-entry" type="button">
          <span className="health-section-icon" aria-hidden="true"><MedicationIcon /></span>
          <span className="health-section-label">用药记录</span>
        </button>
      </nav>
      <section aria-label={section === "body-metrics" ? "身体指标" : section === "medications" ? "用药记录" : section === "medical-logs" ? "健康日记" : "医疗报告"} className="health-member-section-content" id="health-member-report-archive">
        {reportArchive}
      </section>
    </div>;
}
