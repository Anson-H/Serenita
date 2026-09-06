import { useRef, useState, type FormEvent, type RefObject } from "react";
import { createPortal } from "react-dom";
import { createMember, type Member } from "../../api/memberApi";
import { GroupedList } from "../../components/GroupedList";
import { CheckIcon, XIcon } from "../../components/icons";
import { useModalDialog } from "../../components/useModalDialog";
import { useActiveScope } from "../../utils/useActiveScope";
import { DefaultMemberField } from "./DefaultMemberField";
import { MemberFieldsEditor, emptyMemberFields } from "./MemberFieldsEditor";
import { useMembers } from "./MemberProvider";

// Mount only while open so cancelling discards this form, not the workspace draft.
export function CreateMemberDialog({ onClose, onCreated, restoreFocusRef }: {
  onClose: () => void;
  onCreated: (member: Member) => void | Promise<void>;
  restoreFocusRef?: RefObject<HTMLElement | null>;
}) {
  const members = useMembers();
  const dialogRef = useRef<HTMLFormElement | null>(null);
  const isCurrent = useActiveScope("create-member");
  const createsFirstAccessibleMember = members.collection.members.length === 0;
  const [draft, setDraft] = useState(emptyMemberFields);
  const [setAsDefault, setSetAsDefault] = useState(createsFirstAccessibleMember);
  const [created, setCreated] = useState<Member | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useModalDialog({ active: true, dialogRef, escapeDisabled: busy, onEscape: onClose, restoreFocusRef });
  async function save(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true); setError("");
    try {
      const member = created ?? await createMember({ ...draft, set_as_default: setAsDefault });
      if (!isCurrent()) return;
      setCreated(member);
      await members.refresh();
      if (isCurrent()) await onCreated(member);
    } catch (cause) {
      if (isCurrent()) setError(cause instanceof Error ? cause.message : "成员未保存。");
    } finally { if (isCurrent()) setBusy(false); }
  }
  return createPortal(<div className="content-dialog-backdrop dialog-viewport-backdrop" onMouseDown={event => {
    if (event.target === event.currentTarget && !busy) onClose();
  }}>
    <form className="content-dialog dialog-viewport-surface dialog-title-ellipsis" aria-labelledby="create-member-title" aria-modal="true" role="dialog" ref={dialogRef} onSubmit={save}>
      <header className="dialog-titlebar">
        <h2 id="create-member-title" data-modal-initial-focus tabIndex={-1}>添加成员</h2>
        <button aria-label="关闭添加成员" className="control control--titlebar control--icon control--ghost titlebar-icon-control" disabled={busy} onClick={onClose} type="button"><XIcon /></button>
      </header>
      <div className="dialog-body member-dialog-body scroll-content">
        <GroupedList layout="fields" density="standard">
          <MemberFieldsEditor value={draft} disabled={busy || Boolean(created)} onChange={setDraft} />
          <DefaultMemberField value={setAsDefault} disabled={createsFirstAccessibleMember || busy || Boolean(created)} onChange={setSetAsDefault} />
        </GroupedList>
        {error ? <p role="alert">{error}</p> : null}
      </div>
      <footer className="dialog-action-bar">
        <button className="control control--secondary" disabled={busy} onClick={onClose} type="button"><XIcon /><span>取消</span></button>
        <button className="control control--primary" disabled={busy || !draft.member_name.trim()} type="submit">
          <CheckIcon /><span>{busy ? "保存中…" : created ? "继续打开成员" : "保存成员"}</span>
        </button>
      </footer>
    </form>
  </div>, document.body);
}
