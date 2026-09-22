import { type ReactNode } from "react";
import { SidebarShell } from "./SidebarShell";

import type { AuthSession } from "../api/auth/authTypes";
import type { ConversationSummary } from "../api/conversations/conversationTypes";

import type { ScenarioTab } from "../features/conversations/workspaceTypes";
import { Sidebar } from "./Sidebar";
import { type RoutePath } from "./routes";

type PatientShellProps = {
  healthNavigation: ReactNode;
  memoryMemberId?: string | null;
  activeScenario: ScenarioTab;
  children: ReactNode;
  conversations: ConversationSummary[];
  conversationPagination?: { hasMore: boolean; loading: boolean; error: string; loadMore: () => Promise<void> };
  currentSession: Extract<AuthSession, { authenticated: true }>;
  currentSessionId: string | null;
  mobileSidebarOpen: boolean;
  onCollapseMobileSidebar: () => void;
  onCollapseSidebar: () => void;
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
  sidebarCollapsed: boolean;
};

export function PatientShell({
  healthNavigation,
  memoryMemberId,
  activeScenario,
  children,
  conversations,
  conversationPagination,
  currentSession,
  currentSessionId,
  mobileSidebarOpen,
  onCollapseMobileSidebar,
  onCollapseSidebar,
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
  sidebarCollapsed
}: PatientShellProps) {
  return <SidebarShell mobileSidebarOpen={mobileSidebarOpen} sidebarCollapsed={sidebarCollapsed}
    onCollapseMobileSidebar={onCollapseMobileSidebar} sidebar={
      <Sidebar
        healthNavigation={healthNavigation}
        memoryMemberId={memoryMemberId}
        activeScenario={activeScenario}
        conversations={conversations}
      conversationPagination={conversationPagination}
        currentSession={currentSession}
        currentSessionId={currentSessionId}
        onCollapseMobileSidebar={onCollapseMobileSidebar}
        onCollapseSidebar={onCollapseSidebar}
        onBatchDeleteConversations={onBatchDeleteConversations}
        onBatchPinConversations={onBatchPinConversations}
        onDeleteConversation={onDeleteConversation}
        onForkConversation={onForkConversation}
        onNavigate={onNavigate}
        onOpenConversation={onOpenConversation}
        onRenameConversation={onRenameConversation}
        onSetConversationPinned={onSetConversationPinned}
        onStartConversation={onStartConversation}
        route={route}
      />
    }>{children}</SidebarShell>;
}
