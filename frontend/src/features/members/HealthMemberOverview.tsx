import type { ReactNode } from "react";
import { type Member } from "../../api/memberApi";
import { DocumentFormatIcon, HealthRecordIcon, MedicationIcon, ReportScenarioIcon } from "../../components/icons";
import { MemberAvatar } from "./MemberAvatar";
import { memberDisplayName } from "./memberPresentation";

export function HealthMemberOverview({
  informationOpen,
  onOpenInformation,
  member,
  reportArchive
}: {
  informationOpen: boolean;
  onOpenInformation: (source: HTMLButtonElement) => void;
  member: Member;
  reportArchive: ReactNode;
}) {
  const displayName = memberDisplayName(member);
  const sexLabel = member.sex ? { male: "男", female: "女", other: "其他" }[member.sex] : null;
  const bloodTypeLabel = member.blood_type ? { a: "A 型", b: "B 型", ab: "AB 型", o: "O 型", other: "其他" }[member.blood_type] : null;
  return <div className="health-member-overview">
      <section className="sidebar-identity-row health-member-detail-identity" aria-label={`${displayName}的健康档案概览`}
        data-current={informationOpen ? "true" : undefined} data-row-surface>
        <button aria-controls="member-information-detail" aria-current={informationOpen ? "page" : undefined}
          aria-label={`查看${displayName}的个人信息`}
          className="control control--ghost health-member-detail-open" data-interaction-owner="row" data-row-trigger
          onClick={event => onOpenInformation(event.currentTarget)} type="button" />
        <MemberAvatar />
        <strong className="health-member-detail-name" title={displayName}>{displayName}</strong>
        {sexLabel || member.birth_date || bloodTypeLabel ? <p className="health-member-detail-metadata">
          {sexLabel ? <span aria-label={`性别：${sexLabel}`}>{sexLabel}</span> : null}
          {sexLabel && (member.birth_date || bloodTypeLabel) ? <span aria-hidden="true">·</span> : null}
          {member.birth_date ? <time aria-label={`出生日期：${member.birth_date}`} dateTime={member.birth_date}>{member.birth_date}</time> : null}
          {member.birth_date && bloodTypeLabel ? <span aria-hidden="true">·</span> : null}
          {bloodTypeLabel ? <span aria-label={`血型：${bloodTypeLabel}`}>{bloodTypeLabel}</span> : null}
        </p> : null}
      </section>
      <nav className="health-member-sections" aria-label="健康档案内容">
        <button className="control control--ghost health-section-entry" type="button">
          <span className="health-section-icon" aria-hidden="true"><ReportScenarioIcon /></span>
          <span className="health-section-label">身体指标</span>
        </button>
        <button aria-controls="health-member-report-archive" aria-current="page"
          className="control control--ghost health-section-entry" type="button">
          <span className="health-section-icon" aria-hidden="true"><HealthRecordIcon /></span>
          <span className="health-section-label">报告档案</span>
        </button>
        <button className="control control--ghost health-section-entry" type="button">
          <span className="health-section-icon" aria-hidden="true"><DocumentFormatIcon /></span>
          <span className="health-section-label">医疗日志</span>
        </button>
        <button className="control control--ghost health-section-entry" type="button">
          <span className="health-section-icon" aria-hidden="true"><MedicationIcon /></span>
          <span className="health-section-label">用药记录</span>
        </button>
      </nav>
      <section aria-label="报告档案" className="health-member-section-content" id="health-member-report-archive">
        {reportArchive}
      </section>
    </div>;
}
