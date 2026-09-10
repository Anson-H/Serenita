import { useAttachmentTask } from "../../features/conversations/useAttachmentTask";
import { lazy, Suspense, useState, type ReactNode } from "react";
import { apiClient } from "../../api/client";
import type { Member } from "../../api/memberApi";
import { HealthMemberNav } from "../../features/members/HealthMemberNav";
import { useMembers } from "../../features/members/MemberProvider";
import { useReportUpload } from "../../features/reports/useReportUpload";

import type { AuthenticatedSession } from "../../api/client";
import type { useConversationController } from "../../features/conversations/useConversationController";
import {
  DeferredContentBoundary,
  DeferredLoadingState
} from "../../components/DeferredContentBoundary";
import { PatientShell } from "../PatientShell";
import {
  bodyMetricPath,
  isBodyMetricRoute,
  APP_PATH,
  FAVORITES_PATH,
  NOTIFICATIONS_PATH,
  healthPathForMember,
  medicalLogPath,
  medicationPath,
  medicationRoute,
  isMedicalLogRoute,
  isReportRoute,
  memberIdFromHealthPath,
  SETTING_PATH
} from "../routes";
import {
  WorkspaceRouteShell
} from "../WorkspaceRouteShell";

const NotificationWorkspace = lazy(() => import("../../features/notifications/NotificationWorkspace").then(({NotificationWorkspace}) => ({default:NotificationWorkspace})));

const BodyMetricWorkspace = lazy(() => import("../../features/bodyMetrics/BodyMetricWorkspace").then(({BodyMetricWorkspace}) => ({default:BodyMetricWorkspace})));

const MedicationWorkspace = lazy(() => import("../../features/medications/MedicationWorkspace").then(({MedicationWorkspace}) => ({default:MedicationWorkspace})));

const MedicalLogWorkspace = lazy(() => import("../../features/medicalLogs/MedicalLogWorkspace").then(({ MedicalLogWorkspace }) => ({ default: MedicalLogWorkspace })));

const CreateMemberDialog = lazy(() => import("../../features/members/CreateMemberDialog").then(
  ({ CreateMemberDialog: Component }) => ({ default: Component })
));
const FavoritesWorkspacePanel = lazy(() => import("../../features/favorites/FavoritesWorkspacePanel").then(
  ({ FavoritesWorkspacePanel: Component }) => ({ default: Component })
));
const ReportWorkspacePanel = lazy(() => import("../../features/reports/ReportWorkspacePanel").then(
  ({ ReportWorkspacePanel: Component }) => ({ default: Component })
));
const SettingsWorkspacePanel = lazy(() => import("../../features/settings/SettingsWorkspacePanel").then(
  ({ SettingsWorkspacePanel: Component }) => ({ default: Component })
));

type WorkspaceRouteContentProps = ReturnType<typeof useConversationController> & {
  onAccountProfileChange: (session: AuthenticatedSession) => void;
  ShellComponent?: typeof PatientShell;
};

export function WorkspaceRouteContent({
  attachments,
  renderConversation,
  catalogActions,
  reportError,
  enterReports,
  favoriteWorkspace,
  lifecycle,
  onAccountProfileChange,
  pageState,
  reportWorkspace,
  route,
  session,
  ShellComponent = PatientShell,
  workspaceActions,
  workspaceShell
}: WorkspaceRouteContentProps) {
  const { reportUploading, uploadedReportNames, startReportUpload, remainingReportFiles, canRetryReportUpload, retryReportUpload } = useReportUpload({
    accountId: session.account_id, route, memberId: reportWorkspace.memberId, currentSessionId: pageState.currentSessionId,
    canEdit: reportWorkspace.canEdit, unavailableReason: reportWorkspace.reportUploadUnavailableReason,
    mimeTypes: reportWorkspace.reportImportMimeTypes, setUploadErrors: reportWorkspace.setUploadErrors,
    uploadFiles: attachments.uploadFiles, submitMessage: workspaceActions.submitConversationMessage
  });
  const [createMemberBack, setCreateMemberBack] = useState<(() => void) | null>(null);
  const [createMemberOpen, setCreateMemberOpen] = useState(false);
  const submitAttachmentTask = useAttachmentTask({
    scopeKey: `${session.account_id}:${route}`,
    uploadFiles: attachments.uploadFiles,
    submitMessage: workspaceActions.submitConversationMessage
  });
  function renderDeferredWorkspace(content: ReactNode, label: string) {
    return (
      <DeferredContentBoundary key={route}>
        <Suspense fallback={<DeferredLoadingState label={label} />}>
          {content}
        </Suspense>
      </DeferredContentBoundary>
    );
  }

  function renderWorkspaceShell(mainContent: ReactNode) {
    return (
      <WorkspaceRouteShell
        healthNavigation={<HealthMemberNav members={members.collection.members}
          activeMemberId={memberIdFromHealthPath(route) ?? members.activeMemberId ?? undefined}
          current={Boolean(memberIdFromHealthPath(route)) || isReportRoute(route)}
          onSelect={id => members.selectMember(id, { type: "health" })}
          onCreate={onBack => { setCreateMemberBack(() => onBack ?? null); setCreateMemberOpen(true); }} />}
        activeScenario={pageState.activeScenario}
        conversations={pageState.conversations}
        conversationPagination={pageState.conversationPagination}
        currentSession={session}
        currentSessionId={pageState.currentSessionId}
        onBatchDeleteConversations={lifecycle.batchDeleteConversationsFromSidebar}
        onBatchPinConversations={lifecycle.batchPinConversationsFromSidebar}
        onDeleteConversation={lifecycle.deleteConversationFromSidebar}
        onForkConversation={(sessionId) => void workspaceActions.forkConversationFromSidebar(sessionId)}
        onNavigate={lifecycle.navigateTo}
        onOpenConversation={(sessionId) => void lifecycle.openConversationFromSidebar(sessionId)}
        onRenameConversation={lifecycle.renameConversationFromSidebar}
        onStartConversation={lifecycle.startConversation}
        onSetConversationPinned={lifecycle.setConversationPinnedFromSidebar}
        route={route}
        shellControls={workspaceShell}
        ShellComponent={ShellComponent}
      >
        {mainContent}
      </WorkspaceRouteShell>
    );
  }

  function renderConversationPanel(options: {
    composerPlaceholder?: string;
    conversationEnabled?: boolean;
    surfaceMode?: "workspace" | "composer";
  } = {}) {
    return renderConversation({ ...options, onOpenReport: reportId => openStandaloneReport(reportId,
      pageState.conversationDetail ? pageState.conversationDetail.member_id : reportWorkspace.memberId || null) });
  }

  const members = useMembers();
  async function openStandaloneReport(reportId: string, memberId: string | null = reportWorkspace.memberId || null) {
    if (!memberId) {
      reportError("该医疗报告的所属成员当前不可访问。");
      return;
    }
    if (memberId !== reportWorkspace.memberId) {
      try {
        await apiClient.getReport(memberId, reportId);
        await members.selectMember(memberId, { type: "reports", reportId });
      } catch (error) { reportError(error instanceof Error ? error.message : "医疗报告无法打开。"); }
      return;
    }
    const opened = await reportWorkspace.openReport(reportId, true);
    if (!opened) {
      if (pageState.currentSessionId) {
        await lifecycle.openConversation(pageState.currentSessionId);
      }
      return;
    }
    enterReports();
  }

  function renderReportsPage(healthMember: Member) {
    return renderWorkspaceShell(
      renderDeferredWorkspace(
        <ReportWorkspacePanel
          onOpenBodyMetrics={() => lifecycle.navigateTo(bodyMetricPath(healthMember.member_id))}
          onOpenMedicalLogs={() => lifecycle.navigateTo(medicalLogPath(healthMember.member_id))}
          onOpenMedications={() => lifecycle.navigateTo(medicationPath(healthMember.member_id))}
          healthMember={healthMember}
          reportRoute={isReportRoute(route)}
          detailComposer={renderConversationPanel({
            composerPlaceholder: "询问这份医疗报告",
            conversationEnabled: true,
            surfaceMode: "composer"
          })}
          onBackToHealth={() => lifecycle.navigateTo(healthPathForMember(reportWorkspace.memberId))}
          onUploadReports={startReportUpload}
          uploadBusy={reportUploading}
          uploadStatus={<div aria-live="polite">
            {reportUploading ? <p>正在上传医疗报告…</p> : null}
            {uploadedReportNames.length ? <p>已上传：{uploadedReportNames.join("、")}</p> : null}
            {reportWorkspace.uploadErrors.map((error, index) => <p role="alert" key={index}>{error}</p>)}
            {!reportUploading && canRetryReportUpload ?
              <button type="button" onClick={() => void retryReportUpload()}>{remainingReportFiles.length ? "继续上传剩余文件" : "重新提交已上传医疗报告"}</button> : null}
          </div>}
          sidebarToggle={workspaceShell.renderSidebarToggle("reports-sidebar-toggle")}
          workspace={reportWorkspace}
        />,
        "正在载入医疗报告工作区…"
      )
    );
  }

  function renderAppPage() {
    return renderWorkspaceShell(renderConversationPanel());
  }

  function renderRoute() {
    const healthMemberId = memberIdFromHealthPath(route);
    if (healthMemberId) {
      const member = members.collection.members.find(item => item.member_id === healthMemberId);
      if (member && isBodyMetricRoute(route)) return renderWorkspaceShell(
        <DeferredContentBoundary key={`body-metrics-${member.member_id}`}><Suspense fallback={<DeferredLoadingState label="正在载入身体指标…" />}>
          <BodyMetricWorkspace member={member} route={route} navigate={lifecycle.navigateTo}
            sidebarToggle={workspaceShell.renderSidebarToggle("reports-sidebar-toggle")}
            onAsk={async text=>{const sent=await workspaceActions.submitConversationMessage({rawText:text,contextResources:[],memberId:member.member_id,startNewConversation:true});if(!sent)throw new Error('任务未发送，请重试。');}}
            onRecognize={files => submitAttachmentTask(files, member.member_id, "请识别这些食物或营养标签图片，整理食物、份量和摄入能量、碳水、蛋白质、脂肪。需要明确进食日期时间和餐次，缺少时询问我；有足够依据后将饮食记录和图片保存到当前成员的身体指标，照片推算须标明估算依据，给出可编辑记录的链接。")} />
        </Suspense></DeferredContentBoundary>
      );
      if (member && medicationRoute(route)) return renderWorkspaceShell(
        <DeferredContentBoundary key={`medications-${member.member_id}`}><Suspense fallback={<DeferredLoadingState label="正在载入用药记录…" />}>
          <MedicationWorkspace member={member} route={route} navigate={lifecycle.navigateTo}
            sidebarToggle={workspaceShell.renderSidebarToggle("reports-sidebar-toggle")}
            />
        </Suspense></DeferredContentBoundary>
      );
      if (member && isMedicalLogRoute(route)) return renderWorkspaceShell(
        <DeferredContentBoundary key={`medical-logs-${member.member_id}`}><Suspense fallback={<DeferredLoadingState label="正在载入健康日记…" />}>
          <MedicalLogWorkspace member={member} route={route} navigate={lifecycle.navigateTo}
            sidebarToggle={workspaceShell.renderSidebarToggle("reports-sidebar-toggle")} />
        </Suspense></DeferredContentBoundary>
      );
      return member ? renderReportsPage(member) : null;
    }
    if (route === NOTIFICATIONS_PATH) return renderWorkspaceShell(renderDeferredWorkspace(<NotificationWorkspace onNavigate={lifecycle.navigateTo} sidebarToggle={workspaceShell.renderSidebarToggle("notifications-sidebar-toggle")}/>, "正在载入通知…"));
    if (route === FAVORITES_PATH) {
      return renderWorkspaceShell(
        renderDeferredWorkspace(
          <FavoritesWorkspacePanel
            favoriteWorkspace={favoriteWorkspace}
            onOpenConversation={lifecycle.openFavoriteSourceConversation}
            onOpenReport={openStandaloneReport}
            sidebarToggle={workspaceShell.renderSidebarToggle("favorites-sidebar-toggle")}
          />,
          "正在载入收藏工作区…"
        )
      );
    }
    if (isReportRoute(route)) {
      const member = members.collection.members.find(item => item.member_id === reportWorkspace.memberId);
      return member ? renderReportsPage(member) : renderAppPage();
    }
    if (route === SETTING_PATH) {
      return renderWorkspaceShell(
        renderDeferredWorkspace(
          <SettingsWorkspacePanel
            accountId={session.account_id}
            account={session.account}
            modelCatalog={pageState.modelCatalog}
            onModelsChanged={catalogActions.update}
            refreshModels={catalogActions.refresh}
            onReportsChanged={reportWorkspace.invalidateReportData}
            onSignOut={() => void lifecycle.signOut()}
            onAccountProfileChange={onAccountProfileChange}
            settingsSidebarToggle={workspaceShell.renderSidebarToggle("settings-sidebar-toggle")}
            accountName={session.account_name}
          />,
          "正在载入设置工作区…"
        )
      );
    }
    if (route === APP_PATH) {
      return renderAppPage();
    }
    return renderAppPage();
  }

  return <>
    {renderRoute()}
    {createMemberOpen ? (
      <DeferredContentBoundary surface="dialog">
        <Suspense fallback={<DeferredLoadingState label="正在载入添加成员…" surface="dialog" />}>
          <CreateMemberDialog onBack={createMemberBack ? () => { setCreateMemberOpen(false); createMemberBack(); } : undefined} onClose={() => setCreateMemberOpen(false)} onCreated={async member => {
            await members.selectMember(member.member_id, { type: "health" });
            setCreateMemberOpen(false);
          }} />
        </Suspense>
      </DeferredContentBoundary>
    ) : null}
  </>;
}
