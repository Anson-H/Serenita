import type { ReactNode, Ref } from "react";
import { XIcon } from "./icons";

export function ListSelectionBar({ summary, label, cancelLabel, busy = false, onCancel, children, ref }: {
  summary: string; label: string; cancelLabel: string; busy?: boolean;
  onCancel: () => void; children: ReactNode; ref?: Ref<HTMLDivElement>;
}) {
  return <div ref={ref} className="list-selection-heading" aria-label={label}>
    <strong role="status" aria-live="polite">{summary}</strong>
    <div className="compact-control-actions">
      {children}
      <button className="control control--icon control--ghost" type="button" aria-label={cancelLabel} title="退出多选" disabled={busy} onClick={onCancel}><XIcon /></button>
    </div>
  </div>;
}
