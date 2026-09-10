import { navigationLabels } from "../../components/navigationLabels";
import { useRef, useState } from "react";
import { type Member } from "../../api/memberApi";
import { PlusIcon, SwapHorizontalIcon } from "../../components/icons";
import { MemberAvatar } from "./MemberAvatar";
import { IdentityRowCopy } from "../../components/IdentityRowCopy";
import { memberDisplayName, memberLabel } from "./memberPresentation";
import { SwitchMemberDialog } from "./SwitchMemberDialog";

export function HealthMemberNav({ members, activeMemberId, current = false, onSelect, onCreate }: {
  members: Member[];
  activeMemberId?: string;
  current?: boolean;
  onSelect: (id: string) => void | Promise<void>;
  onCreate: (onBack?: () => void) => void;
}) {
  const currentMember = members.find(member => member.member_id === activeMemberId)
    ?? members.find(member => member.is_default)
    ?? members[0]
    ?? null;
  const [switchOpen, setSwitchOpen] = useState(false);
  const switchButtonRef = useRef<HTMLButtonElement | null>(null);
  return <>
    <section className="health-member-nav" aria-label="当前成员">
      {currentMember ? <div className="identity-row health-member-nav-current"
        data-current={current ? "true" : undefined} data-row-surface>
        <button aria-current={current ? "page" : undefined} aria-label={`打开健康档案：${memberLabel(currentMember)}`}
          className="control control--ghost health-member-nav-open" data-interaction-owner="row" data-row-trigger
          onClick={() => void onSelect(currentMember.member_id)} type="button" />
        <MemberAvatar />
        <IdentityRowCopy className="health-member-nav-name" title={memberDisplayName(currentMember)} tooltip={memberLabel(currentMember)}/>
        <span className="health-member-nav-actions">
          <button aria-haspopup="dialog" aria-label={navigationLabels.switchMember} className="control control--titlebar control--icon control--ghost health-member-nav-action"
            data-interaction-owner="self" onClick={() => setSwitchOpen(true)} ref={switchButtonRef} type="button">
            <SwapHorizontalIcon />
          </button>
          <button aria-label={navigationLabels.createMember} className="control control--titlebar control--icon control--ghost health-member-nav-action"
            data-interaction-owner="self" onClick={() => onCreate()} type="button">
            <PlusIcon />
          </button>
        </span>
      </div> : <button className="control control--secondary member-add-action" onClick={() => onCreate()} type="button">
        <PlusIcon /><span>{navigationLabels.createMember}</span>
      </button>}
    </section>
    {switchOpen && currentMember ? <SwitchMemberDialog currentMemberId={currentMember.member_id}
      members={members} restoreFocusRef={switchButtonRef} onClose={() => setSwitchOpen(false)}
      onSelect={async id => { await onSelect(id); setSwitchOpen(false); }}
      onCreate={() => { setSwitchOpen(false); onCreate(() => setSwitchOpen(true)); }} /> : null}
  </>;
}
