import { useEffect, useLayoutEffect, useRef, useState, type Dispatch, type SetStateAction } from "react";
import type { MemberFields } from "../../api/memberApi";
import { DateTimePicker } from "../../components/DateTimePicker";
import { SelectPopover } from "../../components/SelectPopover";
import { focusWithoutScroll } from "../../utils/inputMethod";

export const emptyMemberFields: MemberFields = { member_name: "", sex: null, birth_date: null, blood_type: null };

const BIRTH_DATE_FORMATTER = new Intl.DateTimeFormat("zh-CN", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric"
});

function localDateValue(date: Date) {
  const pad = (part: number) => String(part).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function displayBirthDate(value: string | null) {
  if (!value) return "未设置";
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return value;
  return BIRTH_DATE_FORMATTER.format(new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]), 12));
}

function BirthDateField({ disabled, onChange, value }: {
  disabled: boolean;
  onChange: (value: string | null) => void;
  value: string | null;
}) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(value ?? "");
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const restoreTriggerFocusRef = useRef(false);

  useEffect(() => {
    if (!open) setDraft(value ?? "");
  }, [open, value]);

  useLayoutEffect(() => {
    if (open || !restoreTriggerFocusRef.current) return;
    restoreTriggerFocusRef.current = false;
    const frame = window.requestAnimationFrame(() => focusWithoutScroll(triggerRef.current));
    return () => window.cancelAnimationFrame(frame);
  }, [open]);

  function close(restoreFocus: boolean) {
    restoreTriggerFocusRef.current = restoreFocus;
    setOpen(false);
  }

  return <div className="field-row">
    <span>出生日期</span>
    {open ? <DateTimePicker
      ariaLabel="出生日期"
      disabled={disabled}
      mode="date"
      onCancel={() => { setDraft(value ?? ""); close(true); }}
      onChange={setDraft}
      onCommit={(nextValue, reason) => { onChange(nextValue || null); close(reason === "done"); }}
      value={draft}
    /> : <button
      aria-expanded="false"
      aria-haspopup="dialog"
      aria-label="出生日期"
      className="member-birth-date-trigger"
      data-interaction-owner="row"
      disabled={disabled}
      onClick={() => { setDraft(value ?? localDateValue(new Date())); setOpen(true); }}
      ref={triggerRef}
      type="button"
    >{displayBirthDate(value)}</button>}
  </div>;
}

// Field rows share the enclosing grouped list's columns and interaction states.
export function MemberFieldsEditor({ value, disabled, onChange }: {
  value: MemberFields;
  disabled: boolean;
  onChange: Dispatch<SetStateAction<MemberFields>>;
}) {
  return <>
    <label className="field-row"><span>成员名称</span><input required maxLength={80} disabled={disabled} value={value.member_name} onChange={event => onChange(current => ({ ...current, member_name: event.target.value }))} /></label>
    <div className="field-row"><span>性别</span><SelectPopover ariaLabel="性别" disabled={disabled} menuWidth="content" menuAlign="end" interactionOwner="row" value={value.sex ?? ""} onChange={sex => onChange(current => ({ ...current, sex: sex || null }))} options={[{ value: "", label: "未设置" }, { value: "male", label: "男" }, { value: "female", label: "女" }, { value: "other", label: "其他" }]} /></div>
    <BirthDateField disabled={disabled} value={value.birth_date} onChange={birthDate => onChange(current => ({ ...current, birth_date: birthDate }))} />
    <div className="field-row"><span>血型</span><SelectPopover ariaLabel="血型" disabled={disabled} menuWidth="content" menuAlign="end" interactionOwner="row" value={value.blood_type ?? ""} onChange={bloodType => onChange(current => ({ ...current, blood_type: bloodType || null }))} options={[{ value: "", label: "未设置" }, { value: "a", label: "A 型" }, { value: "b", label: "B 型" }, { value: "ab", label: "AB 型" }, { value: "o", label: "O 型" }, { value: "other", label: "其他" }]} /></div>
  </>;
}
