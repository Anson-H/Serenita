import { useEffect, useRef, type ReactNode } from "react";
import { useDeployment } from "../../app/DeploymentContext";
import { navigationLabels } from "../../components/navigationLabels";
import { interactionReturnTarget } from "../../utils/interactionFocus";
import { SettingsNavigation, type SettingsNavigationTarget } from "./SettingsNavigation";
import { useSettingsNavigation } from "./SettingsNavigationContext";

/** Settings page shell owns navigation, responsive panes and return focus only. */
export function SettingsView({ children, onSignOut }: { children: ReactNode; onSignOut: () => void }) {
  const { actions, mobileSidebarToggle } = useSettingsNavigation();
  const { activeSection, accountPanel, detailOpen, mobileLayer, selectMemoryRoot, selectAccountPanel, selectProvidersRoot, selectDefaultsRoot, selectConversationRoot, selectThemeRoot, selectMembersRoot, selectWebRoot } = actions;
  const settingsTitle = useDeployment().mode === "self_hosted" ? navigationLabels.localSettings : navigationLabels.accountSettings;
  const settingsShellRef = useRef<HTMLElement | null>(null);
  const settingsReturnFocusRef = useRef<HTMLElement | null>(null);
  const previousDetailOpenRef = useRef(detailOpen);
  useEffect(() => {
    const wasOpen = previousDetailOpenRef.current;
    previousDetailOpenRef.current = detailOpen;
    if (wasOpen === detailOpen || !window.matchMedia("(max-width: 650px)").matches) {
      return;
    }

    if (detailOpen) {
      settingsReturnFocusRef.current = interactionReturnTarget();
    }

    const frame = window.requestAnimationFrame(() => {
      if (detailOpen) {
        settingsShellRef.current
          ?.querySelector<HTMLElement>(".settings-detail-panel-back-button")
          ?.focus({ preventScroll: true });
        return;
      }
      if (settingsReturnFocusRef.current?.isConnected) {
        settingsReturnFocusRef.current.focus({ preventScroll: true });
      }
      settingsReturnFocusRef.current = null;
    });

    return () => window.cancelAnimationFrame(frame);
  }, [detailOpen]);

  function selectNavigationTarget(target: SettingsNavigationTarget) {
    if (target === "memory") { selectMemoryRoot(); return; }
    if (target === "account-profile") {
      selectAccountPanel("profile");
      return;
    }
    if (target === "account-password") {
      selectAccountPanel("password");
      return;
    }
    if (target === "account-notifications") { selectAccountPanel("notifications"); return; }
    if (target === "account-grants") {
      selectAccountPanel("grants");
      return;
    }
    if (target === "providers") {
      selectProvidersRoot();
      return;
    }
    if (target === "defaults") {
      selectDefaultsRoot();
      return;
    }
    if (target === "conversation") {
      selectConversationRoot();
      return;
    }
    if (target === "theme") {
      selectThemeRoot();
      return;
    }
    if (target === "members") {
      selectMembersRoot();
      return;
    }
    if (target === "web") {
      selectWebRoot();
      return;
    }
  }

  return <section className="settings-shell settings-two-column" aria-label={settingsTitle}
    data-active-section={activeSection} data-detail-open={detailOpen ? "true" : "false"}
    data-mobile-layer={mobileLayer} ref={settingsShellRef}>
    <div className="settings-primary-pane">
      <header className="settings-primary-toolbar">{mobileSidebarToggle}<strong className="settings-primary-title">{settingsTitle}</strong></header>
      <SettingsNavigation accountPanel={accountPanel} activeSection={activeSection} onSelect={selectNavigationTarget} onSignOut={onSignOut} />
    </div>
    <div className="settings-content-pane">{children}</div>
  </section>;
}
