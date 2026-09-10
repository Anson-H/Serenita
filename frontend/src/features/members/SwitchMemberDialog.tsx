import { NavigationTitle } from "../../components/NavigationTitle";
import { navigationLabels } from "../../components/navigationLabels";
import { useRef, useState, type RefObject } from "react";
import { createPortal } from "react-dom";
import { type Member } from "../../api/memberApi";
import { GroupedList } from "../../components/GroupedList";
import { PlusIcon, XIcon } from "../../components/icons";
import { useModalDialog } from "../../components/useModalDialog";
import { useActiveScope } from "../../utils/useActiveScope";
import { MemberAvatar } from "./MemberAvatar";
import { memberDisplayName, memberLabel } from "./memberPresentation";

export function SwitchMemberDialog({ currentMemberId, members, onClose, onCreate, onSelect, restoreFocusRef }: {
  currentMemberId: string;
  members: Member[];
  onClose: () => void;
  onCreate: () => void;
  onSelect: (memberId: string) => void | Promise<void>;
  restoreFocusRef: RefObject<HTMLElement | null>;
}) {
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const isCurrent = useActiveScope("switch-member");
  const [pendingId, setPendingId] = useState<string | undefined>(undefined);
  const [error, setError] = useState("");
  const busy = pendingId !== undefined;
  useModalDialog({ active: true, dialogRef, escapeDisabled: busy, onEscape: onClose, restoreFocusRef });

  async function select(id: string) {
    if (busy) return;
    setPendingId(id); setError("");
    try {
      await onSelect(id);
      if (isCurrent()) onClose();
    } catch (cause) {
      if (isCurrent()) setError(cause instanceof Error ? cause.message : "成员切换失败。");
    } finally { if (isCurrent()) setPendingId(undefined); }
  }

  return createPortal(<div className="content-dialog-backdrop dialog-viewport-backdrop" onMouseDown={event => {
    if (event.target === event.currentTarget && !busy) onClose();
  }}>
    <div className="content-dialog dialog-viewport-surface dialog-title-ellipsis" role="dialog" aria-modal="true" aria-labelledby="switch-member-title" ref={dialogRef}>
      <header className="dialog-titlebar">
        <NavigationTitle id="switch-member-title" data-modal-initial-focus tabIndex={-1} title={navigationLabels.switchMember} />
        <button aria-label="关闭切换成员" className="control control--titlebar control--icon control--ghost titlebar-icon-control" disabled={busy} onClick={onClose} type="button"><XIcon /></button>
      </header>
      <div className="dialog-body member-dialog-body scroll-content">
        <GroupedList density="standard" selectionMode="single" aria-label="可切换的成员">
          <button className="control control--row grouped-list-create-button member-add-action" type="button" disabled={busy} onClick={onCreate}><PlusIcon /><span>{navigationLabels.createMember}</span></button>
          {members.map(member => <button key={member.member_id} type="button"
            className="control control--row member-switch-entry" aria-label={memberLabel(member)}
            aria-current={member.member_id === currentMemberId ? "page" : undefined}
            disabled={busy} onClick={() => void select(member.member_id)}>
            <MemberAvatar />
            <span className="health-member-identity-copy">
              <strong>{memberDisplayName(member)}</strong>
              {!member.is_owned ? <span>来自 {member.owner_account} · {member.can_edit ? "编辑" : "只读"}</span>
                : null}
            </span>
            {pendingId === member.member_id ? <span className="member-switch-trailing-label" role="status">切换中…</span>
              : member.is_default ? <span className="member-switch-trailing-label">默认成员</span> : null}
          </button>)}
        </GroupedList>
        {error ? <p role="alert">{error}</p> : null}
      </div>
    </div>
  </div>, document.body);
}
