import { ReactNode, useLayoutEffect, useRef } from "react";

import { AuthSession, ConversationSummary } from "../api/client";
import type { ScenarioTab } from "../features/conversations/workspaceTypes";
import { Sidebar } from "./Sidebar";
import { type RoutePath } from "./routes";

type PatientShellProps = {
  healthNavigation: ReactNode;
  activeScenario: ScenarioTab;
  children: ReactNode;
  conversations: ConversationSummary[];
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
  activeScenario,
  children,
  conversations,
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
  const lastMainFocusRef = useRef<HTMLElement | null>(null);
  const mobileSidebarCollapseRef = useRef<HTMLButtonElement | null>(null);
  const previousMobileSidebarOpenRef = useRef(mobileSidebarOpen);

  useLayoutEffect(() => {
    const wasOpen = previousMobileSidebarOpenRef.current;
    previousMobileSidebarOpenRef.current = mobileSidebarOpen;
    if (wasOpen === mobileSidebarOpen) return;

    let secondFrame: number | null = null;
    let settledFocusTimer: number | null = null;
    const focusCurrentTarget = () => {
      if (mobileSidebarOpen) {
        const collapseControl = mobileSidebarCollapseRef.current
          ?? document.querySelector<HTMLElement>(
            ".patient-sidebar .mobile-sidebar-collapse-button"
          );
        collapseControl?.focus({ preventScroll: true });
      } else {
        const previousTarget = lastMainFocusRef.current;
        const currentSidebarToggle = document.querySelector<HTMLElement>(
          ".patient-main .sidebar-toggle-button"
        );
        const focusTarget = previousTarget?.isConnected
          ? previousTarget
          : currentSidebarToggle;
        focusTarget?.focus({ preventScroll: true });
      }
    };
    focusCurrentTarget();
    const frame = window.requestAnimationFrame(() => {
      focusCurrentTarget();
      secondFrame = window.requestAnimationFrame(focusCurrentTarget);
    });
    // The compact rail is visibility-gated while it slides in. Re-assert the
    // destination once that short transition has settled for engines that
    // reject focus during the first composited frame.
    settledFocusTimer = window.setTimeout(() => {
      // Do not overwrite a newer, intentional focus move (for example a
      // member dialog returning focus to the button that opened it). The
      // delayed pass exists only for engines that rejected the first focus
      // while the sidebar transition was still settling.
      if (document.querySelector('[aria-modal="true"], [data-modal-focus-scope="true"]')) {
        return;
      }
      const activeElement = document.activeElement;
      const settledRegion = document.querySelector<HTMLElement>(
        mobileSidebarOpen ? ".patient-sidebar" : ".patient-main"
      );
      if (activeElement instanceof HTMLElement && settledRegion?.contains(activeElement)) {
        return;
      }
      focusCurrentTarget();
    }, 200);
    return () => {
      window.cancelAnimationFrame(frame);
      if (secondFrame !== null) window.cancelAnimationFrame(secondFrame);
      if (settledFocusTimer !== null) window.clearTimeout(settledFocusTimer);
    };
  }, [mobileSidebarOpen]);

  return (
    <main
      className="patient-shell main-page"
      data-mobile-sidebar-open={mobileSidebarOpen ? "true" : "false"}
      data-sidebar-collapsed={sidebarCollapsed ? "true" : "false"}
    >
      <div
        aria-hidden="true"
        className="mobile-sidebar-backdrop"
        data-hover="none"
        onClick={onCollapseMobileSidebar}
      />
      <Sidebar
        healthNavigation={healthNavigation}
        activeScenario={activeScenario}
        conversations={conversations}
        currentSession={currentSession}
        currentSessionId={currentSessionId}
        mobileCollapseButtonRef={mobileSidebarCollapseRef}
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
      <section
        className="patient-main"
        inert={mobileSidebarOpen ? true : undefined}
        onFocusCapture={(event) => {
          if (!mobileSidebarOpen) {
            lastMainFocusRef.current = event.target as HTMLElement;
          }
        }}
      >
        {children}
      </section>
    </main>
  );
}
