import type { AuthenticatedSession, AuthSession } from "../../api/client";
import { useStatusNotification } from "../../components/StatusNotificationCenter";
import { PatientShell } from "../PatientShell";
import type { RoutePath } from "../routes";
import { WorkspaceRouteContent } from "./WorkspaceRouteContent";
import { useConversationController } from "../../features/conversations/useConversationController";

type WorkspacePageProps = {
  route: RoutePath;
  onNavigate: (path: RoutePath, replace?: boolean) => void;
  session: Extract<AuthSession, { authenticated: true }>;
  onSignOut: () => Promise<void>;
  onAccountProfileChange: (session: AuthenticatedSession) => void;
  ShellComponent?: typeof PatientShell;
};

export function WorkspacePage({
  route,
  onNavigate,
  session,
  onSignOut,
  onAccountProfileChange,
  ShellComponent = PatientShell
}: WorkspacePageProps) {
  const workspaceModel = useConversationController({
    route,
    onNavigate,
    session,
    onSignOut
  });

  useStatusNotification(workspaceModel.pageState.composerError, {
    id: "workspace-operation-error",
    title: "操作未完成",
    tone: "error"
  });
  useStatusNotification(
    workspaceModel.reportWorkspace.actionError !== workspaceModel.reportWorkspace.analysisError
      ? workspaceModel.reportWorkspace.actionError
      : "",
    {
      action:
        workspaceModel.reportWorkspace.selectedReportId &&
          !workspaceModel.reportWorkspace.selectedReport
          ? {
            label: "重试",
            onClick: () => void workspaceModel.reportWorkspace.openReport(
              workspaceModel.reportWorkspace.selectedReportId!,
              true
            )
          }
          : undefined,
      id: "report-action-error",
      title:
        workspaceModel.reportWorkspace.selectedReportId &&
          !workspaceModel.reportWorkspace.selectedReport
          ? "医疗报告详情加载失败"
          : "医疗报告操作未完成",
      tone: "error"
    }
  );
  useStatusNotification(workspaceModel.reportWorkspace.actionMessage, {
    id: "report-action-success",
    tone: "success"
  });
  useStatusNotification(workspaceModel.reportWorkspace.listError, {
    action: {
      label: "重试",
      onClick: () => void workspaceModel.reportWorkspace.loadReports()
    },
    id: "report-list-load-error",
    title: "医疗报告列表加载失败",
    tone: "error"
  });
  useStatusNotification(
    workspaceModel.reportWorkspace.uploadErrors.length
      ? workspaceModel.reportWorkspace.uploadErrors.join("；")
      : "",
    {
      id: "report-upload-error",
      title: "部分文件未能处理",
      tone: "error"
    }
  );
  useStatusNotification(workspaceModel.reportWorkspace.analysisError, {
    action: workspaceModel.reportWorkspace.latestAnalysisReportId
      ? {
        label: "重新解读",
        onClick: () => void workspaceModel.reportWorkspace.retryLatestAnalysis()
      }
      : undefined,
    id: "report-analysis-error",
    title: "医疗报告解读未完成",
    tone: "error"
  });

  return (
    <WorkspaceRouteContent
      {...workspaceModel}
      onAccountProfileChange={onAccountProfileChange}
      ShellComponent={ShellComponent}
    />
  );
}
