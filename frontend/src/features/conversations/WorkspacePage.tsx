import type { AuthSession } from "../../api/client";
import type { RoutePath } from "../../app/routes";
import { PatientShell } from "../../app/PatientShell";
import { WorkspaceRouteContent } from "./WorkspaceRouteContent";
import { useWorkspacePageModel } from "./useWorkspacePageModel";

type WorkspacePageProps = {
  route: RoutePath;
  onNavigate: (path: RoutePath, replace?: boolean) => void;
  session: Extract<AuthSession, { authenticated: true }>;
  onSignOut: () => Promise<void>;
  onUserNameChange: (userName: string) => void;
  ShellComponent?: typeof PatientShell;
};

export function WorkspacePage({
  route,
  onNavigate,
  session,
  onSignOut,
  onUserNameChange,
  ShellComponent = PatientShell
}: WorkspacePageProps) {
  const workspaceModel = useWorkspacePageModel({
    route,
    onNavigate,
    session,
    onSignOut
  });

  return (
    <WorkspaceRouteContent
      {...workspaceModel}
      onUserNameChange={onUserNameChange}
      ShellComponent={ShellComponent}
    />
  );
}
