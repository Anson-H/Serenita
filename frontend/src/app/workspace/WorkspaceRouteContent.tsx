import { lazy, Suspense, useState, type ReactNode } from "react";
import { apiClient } from "../../api/client";
import type { Member } from "../../api/memberApi";
import { HealthMemberNav } from "../../features/members/HealthMemberNav";
import { useMembers } from "../../features/members/MemberProvider";
import { useReportUpload } from "../../features/reports/useReportUpload";

import type {
  AuthenticatedSession,
  AuthSession,
  ConversationMessage,
  Favorite
} from "../../api/client";
import {
  DeferredContentBoundary,
  DeferredLoadingState
} from "../../components/DeferredContentBoundary";
import { ConversationWorkspaceSurface } from "../../features/conversations/ConversationWorkspaceSurface";
import type { useConversationAttachments } from "../../features/conversations/useConversationAttachments";
import type { useConversationLayout } from "../../features/conversations/useConversationLayout";
import type { useConversationLifecycle } from "../../features/conversations/useConversationLifecycle";
import type { useConversationMessageActions } from "../../features/conversations/useConversationMessageActions";
import type { useConversationModelControl } from "../../features/conversations/useConversationModelControl";
import type { useConversationPageState } from "../../features/conversations/useConversationPageState";
import type { useConversationViewState } from "../../features/conversations/useConversationViewState";
import type { useConversationWorkspace } from "../../features/conversations/useConversationWorkspace";
import type { FavoriteWorkspaceState } from "../../features/favorites/useFavoriteWorkspace";
import type { ReportWorkspaceState } from "../../features/reports/useReportWorkspace";
import { PatientShell } from "../PatientShell";
import {
  APP_PATH,
  FAVORITES_PATH,
  healthPathForMember,
  isReportRoute,
  memberIdFromHealthPath,
  SETTING_PATH,
  type RoutePath
} from "../routes";
import {
  WorkspaceRouteShell,
  type WorkspaceRouteShellControls
} from "../WorkspaceRouteShell";

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

type WorkspaceRouteContentProps = {
  attachments: ReturnType<typeof useConversationAttachments>;
  favoriteWorkspace: FavoriteWorkspaceState;
  favorites: Favorite[];
  layout: ReturnType<typeof useConversationLayout>;
  lifecycle: ReturnType<typeof useConversationLifecycle>;
  messageActions: ReturnType<typeof useConversationMessageActions>;
  modelControl: ReturnType<typeof useConversationModelControl>;
  onToggleFavorite: (message: ConversationMessage) => void | Promise<void>;
  onAccountProfileChange: (session: AuthenticatedSession) => void;
  pageState: ReturnType<typeof useConversationPageState>;
  reportWorkspace: ReportWorkspaceState;
  route: RoutePath;
  session: Extract<AuthSession, { authenticated: true }>;
  ShellComponent?: typeof PatientShell;
  viewState: ReturnType<typeof useConversationViewState>;
  workspaceActions: ReturnType<typeof useConversationWorkspace>;
  workspaceShell: WorkspaceRouteShellControls;
};

export function WorkspaceRouteContent({
  attachments,
  favoriteWorkspace,
  favorites,
  layout,
  lifecycle,
  messageActions,
  modelControl,
  onToggleFavorite,
  onAccountProfileChange,
  pageState,
  reportWorkspace,
  route,
  session,
  ShellComponent = PatientShell,
  viewState,
  workspaceActions,
  workspaceShell
}: WorkspaceRouteContentProps) {
  const { reportUploading, uploadedReportNames, startReportUpload, remainingReportFiles } = useReportUpload({
    accountId: session.account_id, route, memberId: reportWorkspace.memberId, currentSessionId: pageState.currentSessionId,
    canEdit: reportWorkspace.canEdit, unavailableReason: reportWorkspace.reportUploadUnavailableReason,
    mimeTypes: reportWorkspace.reportImportMimeTypes, setUploadErrors: reportWorkspace.setUploadErrors,
    uploadFiles: attachments.uploadFiles, submitMessage: workspaceActions.submitConversationMessage
  });
  const [createMemberOpen, setCreateMemberOpen] = useState(false);
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
          onCreate={() => setCreateMemberOpen(true)} />}
        activeScenario={pageState.activeScenario}
        conversations={pageState.conversations}
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
    return (
      <ConversationWorkspaceSurface
        accountId={session.account_id}
        attachments={attachments}
        favorites={favorites}
        layout={layout}
        messageActions={messageActions}
        modelControl={modelControl}
        onOpenReport={(reportId) => openStandaloneReport(reportId,
          pageState.conversationDetail ? pageState.conversationDetail.member_id : reportWorkspace.memberId || null)}
        onToggleFavorite={onToggleFavorite}
        pageState={pageState}
        composerPlaceholder={options.composerPlaceholder}
        conversationEnabled={pageState.conversationDetail?.access_state !== "history_only" && options.conversationEnabled !== false}
        sidebarToggle={() => workspaceShell.renderSidebarToggle()}
        surfaceMode={options.surfaceMode}
        viewState={viewState}
        workspaceActions={workspaceActions}
      />
    );
  }

  const members = useMembers();
  async function openStandaloneReport(reportId: string, memberId: string | null = reportWorkspace.memberId || null) {
    if (!memberId) {
      pageState.setComposerError("该报告的所属成员当前不可访问。");
      return;
    }
    if (memberId !== reportWorkspace.memberId) {
      try {
        await apiClient.getReport(memberId, reportId);
        await members.selectMember(memberId, { type: "reports", reportId });
      } catch (error) { pageState.setComposerError(error instanceof Error ? error.message : "报告无法打开。"); }
      return;
    }
    const opened = await reportWorkspace.openReport(reportId, true);
    if (!opened) {
      if (pageState.currentSessionId) {
        await lifecycle.openConversation(pageState.currentSessionId);
      }
      return;
    }
    pageState.setActiveScenario("reports");
  }

  function renderReportsPage(healthMember: Member) {
    return renderWorkspaceShell(
      renderDeferredWorkspace(
        <ReportWorkspacePanel
          healthMember={healthMember}
          reportRoute={isReportRoute(route)}
          detailComposer={renderConversationPanel({
            composerPlaceholder: "询问这份报告",
            conversationEnabled: true,
            surfaceMode: "composer"
          })}
          onBackToHealth={() => lifecycle.navigateTo(healthPathForMember(reportWorkspace.memberId))}
          onUploadReports={startReportUpload}
          uploadBusy={reportUploading}
          uploadStatus={<div aria-live="polite">
            {reportUploading ? <p>正在上传报告…</p> : null}
            {uploadedReportNames.length ? <p>已上传：{uploadedReportNames.join("、")}</p> : null}
            {reportWorkspace.uploadErrors.map((error, index) => <p role="alert" key={index}>{error}</p>)}
            {!reportUploading && uploadedReportNames.length && remainingReportFiles.length ?
              <button type="button" onClick={() => void startReportUpload(remainingReportFiles)}>继续上传剩余文件</button> : null}
          </div>}
          sidebarToggle={workspaceShell.renderSidebarToggle("reports-sidebar-toggle")}
          workspace={reportWorkspace}
        />,
        "正在载入报告工作区…"
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
      return member ? renderReportsPage(member) : null;
    }
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
            onModelsChanged={pageState.setModelCatalog}
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
          <CreateMemberDialog onClose={() => setCreateMemberOpen(false)} onCreated={async member => {
            await members.selectMember(member.member_id, { type: "health" });
            setCreateMemberOpen(false);
          }} />
        </Suspense>
      </DeferredContentBoundary>
    ) : null}
  </>;
}
