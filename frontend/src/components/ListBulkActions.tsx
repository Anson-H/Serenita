import type { ReactNode } from "react";

export function ListBulkActions({ label, inset = false, children }: {
  label: string; inset?: boolean; children: ReactNode;
}) {
  return <div className="list-bulk-actions" role="group" aria-label={label} data-inset={inset || undefined}>{children}</div>;
}
