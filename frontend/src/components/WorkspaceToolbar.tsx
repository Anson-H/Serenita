import type { ReactNode } from "react";

import { ChevronLeftIcon } from "./icons";

export function WorkspaceToolbar({
  className = "",
  leading,
  onBack,
  showBack = true,
  title,
  trailing
}: {
  className?: string;
  leading?: ReactNode;
  onBack?: () => void;
  showBack?: boolean;
  title: string;
  trailing?: ReactNode;
}) {
  return (
    <header
      className={["workspace-navigation-toolbar", className].filter(Boolean).join(" ")}
    >
      <div className="workspace-navigation-leading">
        {leading ? <div className="workspace-navigation-sidebar">{leading}</div> : null}
        {showBack ? (
          <button
            aria-label="返回上一级"
            className="control control--titlebar control--icon control--ghost workspace-back-control titlebar-icon-control"
            disabled={!onBack}
            onClick={onBack}
            title="返回上一级"
            type="button"
          >
            <ChevronLeftIcon />
          </button>
        ) : null}
      </div>
      <h1 className="workspace-navigation-title">{title}</h1>
      <div className="workspace-navigation-trailing">{trailing}</div>
    </header>
  );
}
