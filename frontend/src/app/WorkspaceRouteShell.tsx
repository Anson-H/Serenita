import type { Dispatch, ReactNode, SetStateAction } from "react";

import type { AuthSession, ConversationSummary } from "../api/client";
import { SidebarBackIcon } from "../components/icons";
import { PatientShell } from "./PatientShell";
import type { RoutePath } from "./routes";
import { useResponsiveSidebar } from "./useResponsiveSidebar";
import type { ScenarioTab } from "../features/conversations/workspaceTypes";

export type WorkspaceRouteShellControls = {
  closeMobileSidebar: () => void;
  collapseSidebarFromSidebar: () => void;
  mobileSidebarOpen: boolean;
  renderSidebarToggle: (extraClassName?: string) => ReactNode;
  setMobileSidebarOpen: Dispatch<SetStateAction<boolean>>;
  setSidebarCollapsed: Dispatch<SetStateAction<boolean>>;
  sidebarCollapsed: boolean;
};

type WorkspaceRouteShellProps = {
  activeScenario: ScenarioTab;
  activeView: "home" | "health";
  children: ReactNode;
  conversations: ConversationSummary[];
  currentSession: Extract<AuthSession, { authenticated: true }>;
  currentSessionId: string | null;
  onDeleteConversation: (sessionId: string) => void;
  onNavigate: (path: RoutePath) => void;
  onOpenConversation: (sessionId: string) => void;
  onScenarioChange: (scenario: ScenarioTab) => void;
  onStartConversation: () => void;
  onSwitchView: (view: "home" | "health") => void;
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

  function closeMobileSidebar() {
    setMobileSidebarOpen(false);
  }

  function renderSidebarToggle(extraClassName = "") {
    if (!showWorkspaceSidebarToggle) {
      return null;
    }
    const className = ["sidebar-toggle-button", extraClassName].filter(Boolean).join(" ");
    return (
      <button
        aria-expanded={sidebarToggleExpanded}
        aria-label={sidebarToggleLabel}
        className={className}
        onClick={toggleSidebarFromMain}
        title={sidebarToggleLabel}
        type="button"
      >
        <SidebarBackIcon />
      </button>
    );
  }

  return {
    closeMobileSidebar,
    collapseSidebarFromSidebar,
    mobileSidebarOpen,
    renderSidebarToggle,
    setMobileSidebarOpen,
    setSidebarCollapsed,
    sidebarCollapsed
  };
}

export function WorkspaceRouteShell({
  activeScenario,
  activeView,
  children,
  conversations,
  currentSession,
  currentSessionId,
  onDeleteConversation,
  onNavigate,
  onOpenConversation,
  onScenarioChange,
  onStartConversation,
  onSwitchView,
  route,
  shellControls,
  ShellComponent = PatientShell
}: WorkspaceRouteShellProps) {
  return (
    <ShellComponent
      activeScenario={activeScenario}
      activeView={activeView}
      conversations={conversations}
      currentSession={currentSession}
      currentSessionId={currentSessionId}
      mobileSidebarOpen={shellControls.mobileSidebarOpen}
      onCloseMobileSidebar={shellControls.closeMobileSidebar}
      onCollapseSidebar={shellControls.collapseSidebarFromSidebar}
      onDeleteConversation={onDeleteConversation}
      onNavigate={onNavigate}
      onOpenConversation={onOpenConversation}
      onScenarioChange={onScenarioChange}
      onStartConversation={onStartConversation}
      onSwitchView={onSwitchView}
      route={route}
      sidebarCollapsed={shellControls.sidebarCollapsed}
    >
      {children}
    </ShellComponent>
  );
}
