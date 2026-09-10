import { useRef, useState } from "react";
import { DateTimePicker } from "./DateTimePicker";
import { XIcon } from "./icons";
import { focusWithoutScroll } from "../utils/inputMethod";
import { formatDateOnly } from "../utils/localTime";

export function DateField({ label, value, disabled = false, emptyLabel = "未知", emptyOptionLabel = "未知", allowLongTerm = false, required = false, compact = false, onChange }: {
  label: string; value: string | null; disabled?: boolean; emptyLabel?: string; emptyOptionLabel?: string; allowLongTerm?: boolean; required?: boolean; compact?: boolean; onChange: (value: string | null) => void;
}) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const trigger = useRef<HTMLButtonElement>(null);
  function close(restoreFocus: boolean) {
    setOpen(false);
    if (restoreFocus) window.requestAnimationFrame(() => focusWithoutScroll(trigger.current));
  }
  return <div className={compact ? "compact-date-field" : "field-row"}>
    {compact ? null : <span className="field-label">{label}</span>}
    <span className={compact ? "date-field-value" : "field-value date-field-value"}>
      {open ? <DateTimePicker ariaLabel={label} disabled={disabled} mode="date" value={draft}
        emptyOptionLabel={required ? undefined : emptyOptionLabel}
        allowLongTerm={!required && allowLongTerm}
        onChange={setDraft} onCancel={() => close(true)} onCommit={(next, reason) => {
          if (required && !next) return;
          onChange(next || null); close(reason === "done");
        }} /> : <button ref={trigger} type="button" className="report-inline-edit-trigger" data-interaction-owner="row"
          aria-label={label} aria-haspopup="dialog" aria-expanded="false" disabled={disabled}
          onClick={() => { setDraft(value ?? ""); setOpen(true); }}><span>{value === "long_term" ? "长期" : value ? formatDateOnly(value) : emptyLabel}</span></button>}
      {value && !disabled && !required && emptyOptionLabel === "不限" ? <button type="button" className={`control control--inline control--icon control--ghost${compact ? " control--inline-compact" : ""}`}
        data-interaction-owner="self" aria-label={`清空${label}`} title={`清空${label}`} onClick={() => onChange(null)}><XIcon /></button> : null}
    </span>
  </div>;
}
