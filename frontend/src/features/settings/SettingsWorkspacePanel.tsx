import type { Dispatch, ReactNode, SetStateAction } from "react";

import { type AuthenticatedSession } from "../../api/client";
import { type ModelCatalog } from "../modelConfiguration/modelCatalog";
import { SettingsShell } from "./SettingsShell";

type SettingsWorkspacePanelProps = {
  accountId: string;
  account: string;
  modelCatalog: ModelCatalog;
  onModelsChanged: Dispatch<SetStateAction<ModelCatalog>>;
  onReportsChanged: () => void;
  onSignOut: () => void;
  onAccountProfileChange: (session: AuthenticatedSession) => void;
  settingsSidebarToggle: ReactNode;
  accountName: string;
};

export function SettingsWorkspacePanel({
  accountId,
  account,
  modelCatalog,
  onModelsChanged,
  onReportsChanged,
  onSignOut,
  onAccountProfileChange,
  settingsSidebarToggle,
  accountName
}: SettingsWorkspacePanelProps) {

  return (
    <section className="workspace-panel settings-workspace" aria-label="账号设置">
      <div className="settings-workspace-content">
        <SettingsShell
          accountId={accountId}
          account={account}
          mobileSidebarToggle={settingsSidebarToggle}
          modelCatalog={modelCatalog}
          onModelsChanged={onModelsChanged}
          onReportsChanged={onReportsChanged}
          onSignOut={onSignOut}
          onAccountProfileChange={onAccountProfileChange}
          accountName={accountName}
        />
      </div>
    </section>
  );
}
