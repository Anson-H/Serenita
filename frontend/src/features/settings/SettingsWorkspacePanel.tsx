import { readSettingsRoute, type SettingsPath } from "../../app/settingsRoutes";
import type { Dispatch, ReactNode, SetStateAction } from "react";

import type { AuthenticatedSession } from "../../api/auth/authTypes";

import { type ModelCatalog } from "../modelConfiguration/modelCatalog";
import { SettingsShell } from "./SettingsShell";
import { useDeployment } from "../../app/DeploymentContext";
import { navigationLabels } from "../../components/navigationLabels";

type SettingsWorkspacePanelProps = {
  route: SettingsPath;
  onNavigate: (path: SettingsPath) => void;
  accountId: string;
  account: string;
  modelCatalog: ModelCatalog;
  onModelsChanged: Dispatch<SetStateAction<ModelCatalog>>;
  refreshModels: (isRelevant?: () => boolean) => Promise<void>;
  onSignOut: () => void;
  onAccountProfileChange: (session: AuthenticatedSession) => void;
  settingsSidebarToggle: ReactNode;
  accountName: string;
};

export function SettingsWorkspacePanel({
  route,
  onNavigate,
  accountId,
  account,
  modelCatalog,
  onModelsChanged,
  refreshModels,
  onSignOut,
  onAccountProfileChange,
  settingsSidebarToggle,
  accountName
}: SettingsWorkspacePanelProps) {

  const title = useDeployment().mode === "self_hosted" ? navigationLabels.localSettings : navigationLabels.accountSettings;
  return (
    <section className="workspace-panel settings-workspace" aria-label={title}>
      <div className="settings-workspace-content">
        <SettingsShell
          location={readSettingsRoute(route)!}
          onNavigate={onNavigate}
          accountId={accountId}
          account={account}
          mobileSidebarToggle={settingsSidebarToggle}
          modelCatalog={modelCatalog}
          onModelsChanged={onModelsChanged}
          refreshModels={refreshModels}
          onSignOut={onSignOut}
          onAccountProfileChange={onAccountProfileChange}
          accountName={accountName}
        />
      </div>
    </section>
  );
}
