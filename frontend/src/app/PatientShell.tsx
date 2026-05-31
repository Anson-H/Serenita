import { ReactNode } from "react";

import { AuthSession, ConversationSummary } from "../api/client";
import { Sidebar } from "./Sidebar";
import { type RoutePath } from "./routes";
import type { ScenarioTab } from "../features/conversations/workspaceTypes";

type PatientShellProps = {
  activeScenario: ScenarioTab;
  activeView: "home" | "health";
  children: ReactNode;
  conversations: ConversationSummary[];
  currentSession: Extract<AuthSession, { authenticated: true }>;
  currentSessionId: string | null;
  mobileSidebarOpen: boolean;
  onCloseMobileSidebar: () => void;
  onCollapseSidebar: () => void;
  onDeleteConversation: (sessionId: string) => void;
  onNavigate: (path: RoutePath) => void;
  onOpenConversation: (sessionId: string) => void;
  onScenarioChange: (scenario: ScenarioTab) => void;
  onStartConversation: () => void;
  onSwitchView: (view: "home" | "health") => void;
  route: RoutePath;
  sidebarCollapsed: boolean;
};

export function PatientShell({
  activeScenario,
  activeView,
  children,
  conversations,
  currentSession,
  currentSessionId,
  mobileSidebarOpen,
  onCloseMobileSidebar,
  onCollapseSidebar,
  onDeleteConversation,
  onNavigate,
  onOpenConversation,
  onScenarioChange,
  onStartConversation,
  onSwitchView,
  route,
  sidebarCollapsed
}: PatientShellProps) {
  return (
    <main
      className="patient-shell main-page"
      data-mobile-sidebar-open={mobileSidebarOpen ? "true" : "false"}
      data-sidebar-collapsed={sidebarCollapsed ? "true" : "false"}
    >
      <button
        aria-label="关闭侧边栏"
        className="mobile-sidebar-backdrop"
        onClick={onCloseMobileSidebar}
        type="button"
      />
      <Sidebar
        activeScenario={activeScenario}
        activeView={activeView}
        conversations={conversations}
        currentSession={currentSession}
        currentSessionId={currentSessionId}
        onCloseMobileSidebar={onCloseMobileSidebar}
        onCollapseSidebar={onCollapseSidebar}
        onDeleteConversation={onDeleteConversation}
        onNavigate={onNavigate}
        onOpenConversation={onOpenConversation}
        onScenarioChange={onScenarioChange}
        onStartConversation={onStartConversation}
        onSwitchView={onSwitchView}
        route={route}
      />
      <section className="patient-main">{children}</section>
    </main>
  );
}
