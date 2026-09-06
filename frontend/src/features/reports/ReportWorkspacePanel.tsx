import { useEffect, useRef, useState, type ChangeEvent, type ReactNode } from "react";
import type { Member } from "../../api/memberApi";
import { HealthMemberOverview } from "../members/HealthMemberOverview";
import { MemberInformationPanel } from "../members/MemberInformationPanel";

import { StarIcon } from "../../components/icons";
import { WorkspaceToolbar } from "../../components/WorkspaceToolbar";
import { focusWithoutScroll } from "../../utils/inputMethod";
import { ReportCreateFlow } from "./ReportCreateFlow";
import { ReportDetailPanel } from "./ReportDetailPanel";
import { ReportListPane } from "./ReportListPane";
import { reportDisplayTitle } from "./reportPresentation";
import type { ReportWorkspaceState } from "./useReportWorkspace";

export function ReportWorkspacePanel({
  uploadBusy = false,
  uploadStatus,
  detailComposer,
  healthMember,
  reportRoute,
  onUploadReports,
  onBackToHealth,
  sidebarToggle,
  workspace
}: {
  uploadBusy?: boolean;
  uploadStatus?: ReactNode;
  detailComposer: ReactNode;
  healthMember: Member;
  reportRoute: boolean;
  onBackToHealth: () => void;
  onUploadReports: (files: File[]) => void | Promise<void>;
  sidebarToggle: ReactNode;
  workspace: ReportWorkspaceState;
}) {
  const workspaceRef = useRef<HTMLElement | null>(null);
  const detailPanelRef = useRef<HTMLElement | null>(null);
  const uploadInputRef = useRef<HTMLInputElement | null>(null);
  const createReturnFocusRef = useRef<HTMLElement | null>(null);
  const memberInformationReturnFocusRef = useRef<HTMLElement | null>(null);
  const [createFlowOpen, setCreateFlowOpen] = useState(false);
  const [memberInformationOpen, setMemberInformationOpen] = useState(false);
  const detailOpen = memberInformationOpen || (reportRoute && workspace.detailVisible);
  const previousDetailOpenRef = useRef(detailOpen);
  const previousMemberInformationOpenRef = useRef(memberInformationOpen);
  const previousCreateFlowOpenRef = useRef(createFlowOpen);

  useEffect(() => {
    const wasVisible = previousDetailOpenRef.current;
    const wasMemberInformationOpen = previousMemberInformationOpenRef.current;
    previousDetailOpenRef.current = detailOpen;
    previousMemberInformationOpenRef.current = memberInformationOpen;
    if (
      wasVisible === detailOpen ||
      !window.matchMedia("(max-width: 650px)").matches
    ) {
      return;
    }
    const frame = window.requestAnimationFrame(() => {
      if (detailOpen) {
        detailPanelRef.current?.focus();
        return;
      }
      if (wasMemberInformationOpen && memberInformationReturnFocusRef.current?.isConnected) {
        focusWithoutScroll(memberInformationReturnFocusRef.current);
        return;
      }
      workspaceRef.current
        ?.querySelector<HTMLButtonElement>('.report-timeline-item[aria-current="page"]')
        ?.focus();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [detailOpen, memberInformationOpen]);

  useEffect(() => {
    setMemberInformationOpen(false);
  }, [healthMember.member_id]);

  useEffect(() => {
    const wasOpen = previousCreateFlowOpenRef.current;
    previousCreateFlowOpenRef.current = createFlowOpen;
    if (!wasOpen || createFlowOpen) return;
    const frame = window.requestAnimationFrame(() => {
      if (createReturnFocusRef.current?.isConnected) {
        focusWithoutScroll(createReturnFocusRef.current);
      }
    });
    return () => window.cancelAnimationFrame(frame);
  }, [createFlowOpen]);

  async function handleUpload(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.currentTarget.files ?? []);
    event.currentTarget.value = "";
    if (files.length) {
      await onUploadReports(files);
    }
  }

  function openCreateFlow() {
    createReturnFocusRef.current = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    setCreateFlowOpen(true);
  }

  function openMemberInformation(source: HTMLButtonElement) {
    memberInformationReturnFocusRef.current = source;
    setMemberInformationOpen(true);
  }

  function closeMemberInformation() {
    setMemberInformationOpen(false);
    window.requestAnimationFrame(() => {
      if (memberInformationReturnFocusRef.current?.isConnected) {
        focusWithoutScroll(memberInformationReturnFocusRef.current);
      }
    });
  }

  return (
    <section
      className="reports-workspace"
      data-detail-open={detailOpen ? "true" : "false"}
      ref={workspaceRef}
    >
      <input
        accept={workspace.reportImportMimeTypes.join(",")}
        className="report-upload-input"
        disabled={workspace.uploadBlocked || uploadBusy}
        hidden
        multiple
        onChange={handleUpload}
        ref={uploadInputRef}
        tabIndex={-1}
        type="file"
      />

      <div className="report-upload-status">{uploadStatus}</div>
      <div className="report-browser-layout">
        <div className="report-library-column">
          <WorkspaceToolbar
            className="reports-list-toolbar"
            leading={sidebarToggle}
            showBack={false}
            title="健康档案"
          />
          <HealthMemberOverview
            informationOpen={memberInformationOpen}
            onOpenInformation={openMemberInformation}
            member={healthMember}
            reportArchive={<ReportListPane onRequestCreate={openCreateFlow} workspace={workspace} />}
          />
        </div>
        <div className="report-detail-column">
          {memberInformationOpen ? <MemberInformationPanel
            onClose={closeMemberInformation}
            panelRef={detailPanelRef}
            member={healthMember}
          /> : <><WorkspaceToolbar
            className="reports-detail-toolbar"
            onBack={workspace.detailVisible ? onBackToHealth : undefined}
            title={workspace.selectedReport
              ? reportDisplayTitle(workspace.selectedReport)
              : "报告详情"}
            trailing={workspace.selectedReport ? (
              <button
                aria-label={workspace.reportFavorited ? "取消收藏报告" : "收藏报告"}
                aria-pressed={workspace.reportFavorited}
                className="control control--titlebar control--icon control--ghost message-icon-button report-action-icon-button reports-toolbar-favorite titlebar-icon-control"
                data-active={workspace.reportFavorited ? "true" : undefined}
                disabled={workspace.favoritingReport}
                onClick={() => void workspace.toggleReportFavorite()}
                title={workspace.reportFavorited ? "取消收藏报告" : "收藏报告"}
                type="button"
              >
                <StarIcon filled={workspace.reportFavorited} />
              </button>
            ) : null}
          />
            <ReportDetailPanel
              conversationComposer={detailComposer}
              panelRef={detailPanelRef}
              workspace={workspace}
            /></>}
        </div>
      </div>
      <ReportCreateFlow
        onClose={() => setCreateFlowOpen(false)}
        onRequestUpload={() => uploadInputRef.current?.click()}
        open={createFlowOpen}
        workspace={workspace}
      />
    </section>
  );
}
