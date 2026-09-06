import type { Dispatch, ReactNode, SetStateAction } from "react";

import type { AuthSession, ConversationSummary } from "../api/client";
import { SidebarCollapsedIcon } from "../components/icons";
import type { ScenarioTab } from "../features/conversations/workspaceTypes";
import { PatientShell } from "./PatientShell";
import type { RoutePath } from "./routes";
import { useResponsiveSidebar } from "./useResponsiveSidebar";

export type WorkspaceRouteShellControls = {
  collapseMobileSidebar: () => void;
  collapseSidebarFromSidebar: () => void;
  mobileSidebarOpen: boolean;
  renderSidebarToggle: (extraClassName?: string) => ReactNode;
  setMobileSidebarOpen: Dispatch<SetStateAction<boolean>>;
  setSidebarCollapsed: Dispatch<SetStateAction<boolean>>;
  sidebarCollapsed: boolean;
};

type WorkspaceRouteShellProps = {
  healthNavigation: ReactNode;
  activeScenario: ScenarioTab;
  children: ReactNode;
  conversations: ConversationSummary[];
  currentSession: Extract<AuthSession, { authenticated: true }>;
  currentSessionId: string | null;
  onBatchDeleteConversations: (sessionIds: string[]) => Promise<string[]>;
  onBatchPinConversations: (sessionIds: string[], isPinned: boolean) => Promise<boolean>;
  onDeleteConversation: (sessionId: string) => Promise<boolean>;
  onForkConversation: (sessionId: string) => void;
  onNavigate: (path: RoutePath) => void;
  onOpenConversation: (sessionId: string) => void;
  onRenameConversation: (sessionId: string, title: string) => Promise<boolean>;
  onSetConversationPinned: (sessionId: string, isPinned: boolean) => Promise<boolean>;
  onStartConversation: () => void;
  route: RoutePath;
  shellControls: WorkspaceRouteShellControls;
  ShellComponent?: typeof PatientShell;
};

export function useWorkspaceRouteShell(): WorkspaceRouteShellControls {
  const {
    compactSidebarMode,
    mobileSidebarOpen,
    setMobileSidebarOpen,
    sidebarCollapsed,
    setSidebarCollapsed,
    toggleSidebarFromMain,
    collapseSidebarFromSidebar
  } = useResponsiveSidebar();
  const sidebarToggleExpanded = compactSidebarMode ? mobileSidebarOpen : !sidebarCollapsed;
  const sidebarToggleLabel = sidebarToggleExpanded ? "折叠侧边栏" : "展开侧边栏";
  const showWorkspaceSidebarToggle = compactSidebarMode ? !mobileSidebarOpen : sidebarCollapsed;

  function collapseMobileSidebar() {
    setMobileSidebarOpen(false);
  }

  function renderSidebarToggle(extraClassName = "") {
    if (!showWorkspaceSidebarToggle) {
      return null;
    }
    const className = [
      "control control--titlebar control--icon control--ghost",
      "sidebar-toggle-button",
      "titlebar-icon-control",
      extraClassName
    ].filter(Boolean).join(" ");
    return (
      <button
        aria-expanded={sidebarToggleExpanded}
        aria-label={sidebarToggleLabel}
        className={className}
        onClick={toggleSidebarFromMain}
        title={sidebarToggleLabel}
        type="button"
      >
        <SidebarCollapsedIcon />
      </button>
    );
  }

  return {
    collapseMobileSidebar,
    collapseSidebarFromSidebar,
    mobileSidebarOpen,
    renderSidebarToggle,
    setMobileSidebarOpen,
    setSidebarCollapsed,
    sidebarCollapsed
  };
}

export function WorkspaceRouteShell({
  healthNavigation,
  activeScenario,
  children,
  conversations,
  currentSession,
  currentSessionId,
  onBatchDeleteConversations,
  onBatchPinConversations,
  onDeleteConversation,
  onForkConversation,
  onNavigate,
  onOpenConversation,
  onRenameConversation,
  onSetConversationPinned,
  onStartConversation,
  route,
  shellControls,
  ShellComponent = PatientShell
}: WorkspaceRouteShellProps) {
  return (
    <ShellComponent
      healthNavigation={healthNavigation}
      activeScenario={activeScenario}
      conversations={conversations}
      currentSession={currentSession}
      currentSessionId={currentSessionId}
      mobileSidebarOpen={shellControls.mobileSidebarOpen}
      onBatchDeleteConversations={onBatchDeleteConversations}
      onBatchPinConversations={onBatchPinConversations}
      onCollapseMobileSidebar={shellControls.collapseMobileSidebar}
      onCollapseSidebar={shellControls.collapseSidebarFromSidebar}
      onDeleteConversation={onDeleteConversation}
      onForkConversation={onForkConversation}
      onNavigate={onNavigate}
      onOpenConversation={onOpenConversation}
      onRenameConversation={onRenameConversation}
      onSetConversationPinned={onSetConversationPinned}
      onStartConversation={onStartConversation}
      route={route}
      sidebarCollapsed={shellControls.sidebarCollapsed}
    >
      {children}
    </ShellComponent>
  );
}
