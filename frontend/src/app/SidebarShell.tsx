import { type ReactNode, useLayoutEffect, useRef } from "react";

export function SidebarShell({ children, sidebar, mobileSidebarOpen, sidebarCollapsed, onCollapseMobileSidebar, className = "" }: {
  children: ReactNode; sidebar: ReactNode; mobileSidebarOpen: boolean; sidebarCollapsed: boolean; onCollapseMobileSidebar: () => void; className?: string;
}) {
  const lastMainFocusRef = useRef<HTMLElement | null>(null);
  const previousMobileSidebarOpenRef = useRef(mobileSidebarOpen);

  useLayoutEffect(() => {
    const wasOpen = previousMobileSidebarOpenRef.current;
    previousMobileSidebarOpenRef.current = mobileSidebarOpen;
    if (wasOpen === mobileSidebarOpen) return;

    let secondFrame: number | null = null;
    let settledFocusTimer: number | null = null;
    const focusCurrentTarget = () => {
      if (mobileSidebarOpen) {
        const collapseControl = document.querySelector<HTMLElement>(
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
      className={`patient-shell main-page ${className}`}
      data-mobile-sidebar-open={mobileSidebarOpen ? "true" : "false"}
      data-sidebar-collapsed={sidebarCollapsed ? "true" : "false"}
    >
      <div
        aria-hidden="true"
        className="mobile-sidebar-backdrop"
        data-hover="none"
        onClick={onCollapseMobileSidebar}
      />
      {sidebar}
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
