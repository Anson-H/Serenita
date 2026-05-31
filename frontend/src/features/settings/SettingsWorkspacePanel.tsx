import type { ReactNode } from "react";

import { type AddedModel, apiClient } from "../../api/client";
import { mergeModelsWithChatDefault } from "../conversations/conversationModels";
import { SettingsShell } from "./SettingsShell";

type SettingsWorkspacePanelProps = {
  account: string;
  onModelsChanged: (models: AddedModel[]) => void;
  onSignOut: () => void;
  onUserNameChange: (userName: string) => void;
  settingsSidebarToggle: ReactNode;
  userName: string;
};

export function SettingsWorkspacePanel({
  account,
  onModelsChanged,
  onSignOut,
  onUserNameChange,
  settingsSidebarToggle,
  userName
}: SettingsWorkspacePanelProps) {
  async function refreshModels() {
    const [modelResponse, defaultsResponse] = await Promise.all([
      apiClient.fetchModels(),
      apiClient.fetchModelDefaults()
    ]);
    onModelsChanged(mergeModelsWithChatDefault(modelResponse.models, defaultsResponse.defaults.chat));
  }

  return (
    <section className="workspace-panel settings-workspace" aria-label="账号设置">
      <div className="settings-workspace-header">
        <div className="settings-toolbar">
          <div className="settings-toolbar-leading">
            {settingsSidebarToggle}
          </div>
          <strong className="settings-toolbar-title">账号设置</strong>
          <div className="settings-toolbar-controls" />
        </div>
      </div>
      <div className="settings-workspace-content">
        <SettingsShell
          account={account}
          mobileSidebarToggle={settingsSidebarToggle}
          onModelsChanged={refreshModels}
          onSignOut={onSignOut}
          onUserNameChange={onUserNameChange}
          userName={userName}
        />
      </div>
    </section>
  );
}
