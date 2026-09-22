import { ModelSettingsApiContext } from "../modelConfiguration/ModelSettingsApi";
import { clientModelSettingsApi } from "../../api/models/settingsAdapter";
import { useRef, useState, type ReactNode, type Dispatch, type SetStateAction } from "react";
import { useDeployment } from "../../app/DeploymentContext";
import type { AuthenticatedSession } from "../../api/auth/authTypes";

import { SerialTasks } from "../../utils/serialTasks";
import { saveBeforeNavigation } from "../../utils/pendingNavigation";
import { useActiveScope } from "../../utils/useActiveScope";
import { settingsPath, type SettingsLocation, type SettingsPath } from "../../app/settingsRoutes";
import type { ModelCatalog } from "../modelConfiguration/modelCatalog";
import { createSettingsNavigationActions } from "./settingsNavigationActions";
import { SettingsNavigationContext } from "./SettingsNavigationContext";
import { SettingsView } from "./SettingsView";
import { AccountSettingsSection } from "./account/AccountSettingsSection";
import { ModelsSettingsSection } from "./models/ModelsSettingsSection";
import { WebSettingsSection } from "./web/WebSettingsSection";
import { ConversationSettingsSection } from "./conversation/ConversationSettingsSection";
import { GeneralSettingsSection } from "./GeneralSettingsSection";
type SettingsShellProps = {
  location: SettingsLocation;
  onNavigate: (path: SettingsPath) => void;
  accountId: string;
  account: string;
  accountName: string;
  mobileSidebarToggle?: ReactNode;
  onSignOut: () => void;
  onAccountProfileChange: (session: AuthenticatedSession) => void;
  modelCatalog: ModelCatalog;
  onModelsChanged: Dispatch<SetStateAction<ModelCatalog>>;
  refreshModels: (isRelevant?: () => boolean) => Promise<void>;
};

/** Composition root: all editing sessions stay mounted while settings navigation changes. */
export function SettingsShell({ location, onNavigate, accountId, account, accountName, mobileSidebarToggle,
  onSignOut, onAccountProfileChange, modelCatalog, onModelsChanged, refreshModels }: SettingsShellProps) {
  const local = useDeployment().mode === "self_hosted";
  const [composing, setComposing] = useState(false);
  const isCurrentScope = useActiveScope(accountId);
  const serialTasks = useRef(new SerialTasks());
  const session = { accountId, composing, isCurrentScope, serialTasks };
  const actions = createSettingsNavigationActions({ location, local, onNavigate });
  return <SettingsNavigationContext.Provider value={{ location, actions, mobileSidebarToggle, navigateSettings: target => onNavigate(settingsPath(target)) }}>
    <div style={{ display: "contents" }} onCompositionStartCapture={() => setComposing(true)} onCompositionEndCapture={() => setComposing(false)}>
      <SettingsView onSignOut={() => { void saveBeforeNavigation().then(saved => { if (saved) onSignOut(); }); }}>
        <AccountSettingsSection session={session} account={account} accountName={accountName} onAccountProfileChange={onAccountProfileChange} />
        <ModelSettingsApiContext.Provider value={clientModelSettingsApi}><ModelsSettingsSection session={session} modelCatalog={modelCatalog} onModelsChanged={onModelsChanged} refreshModels={refreshModels} /></ModelSettingsApiContext.Provider>
        <WebSettingsSection session={session} />
        <ConversationSettingsSection accountId={accountId} />
        <GeneralSettingsSection />
      </SettingsView>
    </div>
  </SettingsNavigationContext.Provider>;
}
