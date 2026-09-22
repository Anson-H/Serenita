import { NavigationTitle } from "../../components/NavigationTitle";
import type { ReactNode } from "react";

import { ChevronLeftIcon } from "../../components/icons";

export function SettingsDetailPanel({
  children,
  mobileOpen = true,
  onBack,
  title,
  wide = false
}: {
  children: ReactNode;
  mobileOpen?: boolean;
  onBack: () => void;
  title: string;
  wide?: boolean;
}) {
  return (
    <section
      aria-labelledby="settings-detail-panel-title"
      className={wide ? "settings-detail-panel wide" : "settings-detail-panel"}
      data-mobile-open={mobileOpen ? "true" : "false"}
    >
      <header className="settings-detail-panel-header workspace-detail-titlebar">
        <button
          aria-label={`返回${title}的上一级`}
          className="control control--titlebar control--icon control--ghost workspace-back-control settings-detail-panel-back-button titlebar-icon-control"
          onClick={onBack}
          title="返回上一级"
          type="button"
        >
          <ChevronLeftIcon />
        </button>
        <NavigationTitle id="settings-detail-panel-title" title={title} />
        <span aria-hidden="true" />
      </header>
      <div className="settings-detail-panel-body scroll-content content-column">{children}</div>
    </section>
  );
}
