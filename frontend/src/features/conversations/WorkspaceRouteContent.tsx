import type { ReactNode } from "react";

import type { AuthSession, ConversationMessage, Favorite } from "../../api/client";
import { PatientShell } from "../../app/PatientShell";
import {
  APP_PATH,
  FAVORITES_PATH,
  SETTING_PATH,
  type RoutePath
} from "../../app/routes";
import {
  WorkspaceRouteShell,
  type WorkspaceRouteShellControls
} from "../../app/WorkspaceRouteShell";
import { FavoritesWorkspacePanel } from "../favorites/FavoritesWorkspacePanel";
import type { FavoriteWorkspaceState } from "../favorites/useFavoriteWorkspace";
import { SettingsWorkspacePanel } from "../settings/SettingsWorkspacePanel";
import { ConversationWorkspacePanel } from "./ConversationWorkspacePanel";
import type { useConversationAttachments } from "./useConversationAttachments";
import type { useConversationBranching } from "./useConversationBranching";
import type { useConversationLayout } from "./useConversationLayout";
import type { useConversationLifecycle } from "./useConversationLifecycle";
import type { useConversationMessageActions } from "./useConversationMessageActions";
import type { useConversationModelControl } from "./useConversationModelControl";
import type { useConversationPageState } from "./useConversationPageState";
import type { useConversationViewState } from "./useConversationViewState";
import type { useConversationWorkspace } from "./useConversationWorkspace";

type WorkspaceRouteContentProps = {
  attachments: ReturnType<typeof useConversationAttachments>;
  branching: ReturnType<typeof useConversationBranching>;
  favoriteWorkspace: FavoriteWorkspaceState;
  favorites: Favorite[];
  layout: ReturnType<typeof useConversationLayout>;
  lifecycle: ReturnType<typeof useConversationLifecycle>;
  messageActions: ReturnType<typeof useConversationMessageActions>;
  modelControl: ReturnType<typeof useConversationModelControl>;
  onToggleFavorite: (message: ConversationMessage) => void | Promise<void>;
  onUserNameChange: (userName: string) => void;
  pageState: ReturnType<typeof useConversationPageState>;
  route: RoutePath;
  session: Extract<AuthSession, { authenticated: true }>;
  ShellComponent?: typeof PatientShell;
  viewState: ReturnType<typeof useConversationViewState>;
  workspaceActions: ReturnType<typeof useConversationWorkspace>;
  workspaceShell: WorkspaceRouteShellControls;
};

export function WorkspaceRouteContent({
  attachments,
  branching,
  favoriteWorkspace,
  favorites,
  layout,
  lifecycle,
  messageActions,
  modelControl,
  onToggleFavorite,
  onUserNameChange,
  pageState,
  route,
  session,
  ShellComponent = PatientShell,
  viewState,
  workspaceActions,
  workspaceShell
}: WorkspaceRouteContentProps) {
  function renderWorkspaceShell(mainContent: ReactNode) {
    return (
      <WorkspaceRouteShell
        activeScenario={pageState.activeScenario}
        activeView={pageState.activeView}
        conversations={pageState.conversations}
        currentSession={session}
        currentSessionId={pageState.currentSessionId}
        onDeleteConversation={(sessionId) => void lifecycle.deleteConversationFromSidebar(sessionId)}
        onNavigate={lifecycle.navigateTo}
        onOpenConversation={(sessionId) => void lifecycle.openConversationFromSidebar(sessionId)}
        onScenarioChange={lifecycle.changeScenario}
        onStartConversation={lifecycle.startConversation}
        onSwitchView={lifecycle.switchView}
        route={route}
        shellControls={workspaceShell}
        ShellComponent={ShellComponent}
      >
        {mainContent}
      </WorkspaceRouteShell>
    );
  }

  function renderAppPage() {
    return renderWorkspaceShell(
      <ConversationWorkspacePanel
        attachments={attachments}
        branching={branching}
        favorites={favorites}
        layout={layout}
        messageActions={messageActions}
        modelControl={modelControl}
        onToggleFavorite={onToggleFavorite}
        pageState={pageState}
        sidebarToggle={() => workspaceShell.renderSidebarToggle()}
        viewState={viewState}
        workspaceActions={workspaceActions}
      />
    );
  }

  function renderRoute() {
    if (route === FAVORITES_PATH) {
      return renderWorkspaceShell(
        <FavoritesWorkspacePanel
          favoriteWorkspace={favoriteWorkspace}
          onOpenConversation={lifecycle.openFavoriteSourceConversation}
          sidebarToggle={workspaceShell.renderSidebarToggle("favorites-sidebar-toggle")}
        />
      );
    }
    if (route === SETTING_PATH) {
      return renderWorkspaceShell(
        <SettingsWorkspacePanel
          account={session.account}
          onModelsChanged={(nextModels) => pageState.setModels(nextModels)}
          onSignOut={() => void lifecycle.signOut()}
          onUserNameChange={onUserNameChange}
          settingsSidebarToggle={workspaceShell.renderSidebarToggle("settings-sidebar-toggle")}
          userName={session.user_name}
        />
      );
    }
    if (route === APP_PATH) {
      return renderAppPage();
    }
    return renderAppPage();
  }

  return renderRoute();
}
