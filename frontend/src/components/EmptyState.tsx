import type { ReactNode } from "react";

/** The parent allocates the available area; inline states keep their natural height. */
export function EmptyState({ title, description, icon, layout = "pane", className = "", role }: {
  title: ReactNode;
  description?: ReactNode;
  icon?: ReactNode;
  layout?: "pane" | "inline";
  className?: string;
  role?: "status" | "alert";
}) {
  return <div className={`empty-state-content ${layout === "pane" ? "workspace-empty-state" : "inline-empty-state"} ${className}`.trim()} role={role}>
    {icon ? <div className="empty-state-icon" aria-hidden="true">{icon}</div> : null}
    <strong className="empty-state-title">{title}</strong>
    {description ? <p className="empty-state-description">{description}</p> : null}
  </div>;
}
