import { useEffect, useState } from "react";

export const SIDEBAR_COMPACT_MEDIA = "(max-width: 1000px)";

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

    function closeMobileSidebarOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setMobileSidebarOpen(false);
      }
    }

    document.addEventListener("keydown", closeMobileSidebarOnEscape);
    return () => document.removeEventListener("keydown", closeMobileSidebarOnEscape);
  }, [mobileSidebarOpen]);

  useEffect(() => {
    const mediaQuery = window.matchMedia(SIDEBAR_COMPACT_MEDIA);

    function syncCompactSidebarMode() {
      setCompactSidebarMode(mediaQuery.matches);
      setMobileSidebarOpen(false);
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
