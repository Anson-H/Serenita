import { useEffect, useState } from "react";

const SIDEBAR_COMPACT_MEDIA = "(max-width: 1000px)";

function matchesViewportMedia(query: string) {
  return typeof window !== "undefined" && window.matchMedia(query).matches;
}

function isCompactSidebarViewport() {
  return matchesViewportMedia(SIDEBAR_COMPACT_MEDIA);
}

export function useResponsiveSidebar() {
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [compactSidebarMode, setCompactSidebarMode] = useState(isCompactSidebarViewport);

  useEffect(() => {
    if (!mobileSidebarOpen) {
      return;
    }

    function collapseMobileSidebarOnEscape(event: KeyboardEvent) {
      // A dialog or its menu owns Escape until that overlay has closed.
      if (event.key === "Escape" && !event.defaultPrevented &&
        !document.querySelector('[aria-modal="true"], [data-modal-focus-scope="true"]')) {
        setMobileSidebarOpen(false);
      }
    }

    document.addEventListener("keydown", collapseMobileSidebarOnEscape);
    return () => document.removeEventListener("keydown", collapseMobileSidebarOnEscape);
  }, [mobileSidebarOpen]);

  useEffect(() => {
    const mediaQuery = window.matchMedia(SIDEBAR_COMPACT_MEDIA);

    function syncCompactSidebarMode() {
      const compact = mediaQuery.matches;
      setCompactSidebarMode(compact);
      setMobileSidebarOpen(false);
      if (!compact) {
        setSidebarCollapsed(false);
      }
    }

    syncCompactSidebarMode();
    mediaQuery.addEventListener("change", syncCompactSidebarMode);
    return () => mediaQuery.removeEventListener("change", syncCompactSidebarMode);
  }, []);

  function toggleSidebarFromMain() {
    if (compactSidebarMode) {
      setMobileSidebarOpen(true);
      return;
    }
    setSidebarCollapsed(false);
  }

  function collapseSidebarFromSidebar() {
    if (compactSidebarMode) {
      setMobileSidebarOpen(false);
      return;
    }
    setSidebarCollapsed(true);
  }

  return {
    compactSidebarMode,
    mobileSidebarOpen,
    setMobileSidebarOpen,
    sidebarCollapsed,
    setSidebarCollapsed,
    toggleSidebarFromMain,
    collapseSidebarFromSidebar
  };
}
