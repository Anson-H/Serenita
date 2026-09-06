import type { Member } from "../../api/memberApi";

export function memberDisplayName(member: Member) {
  return !member.is_owned && member.member_name === "本人" ? `${member.owner_account} 本人` : member.member_name;
}

export function memberLabel(member: Member) {
  const name = memberDisplayName(member);
  const access = member.is_owned ? name : `${name} · 来自 ${member.owner_account} · ${member.can_edit ? "编辑" : "只读"}`;
  return member.is_default ? `${access} · 默认成员` : access;
}
