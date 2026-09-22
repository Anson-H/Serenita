import { GroupedList } from "../../../components/GroupedList";
import { SelectPopover } from "../../../components/SelectPopover";
import { useMembers } from "../../members/MemberProvider";
import { memberLabel, memberDisplayName } from "../../members/memberPresentation";
import { ModelCapabilityNavigationRow } from "../../modelConfiguration/models/ModelCapabilityNavigationRow";
import { MemoryFormationSettings } from './MemoryFormationSettings';
import "../../../styles/memory.css";

export type MemorySettingsPage = 'root' | 'formation';
export const memorySettingsTitles: Record<MemorySettingsPage, string> = { root: '长期记忆', formation: '记忆控制' };
const pages: MemorySettingsPage[] = ['formation'];

export function MemorySettings({ page, memberId, onNavigate }: { page: MemorySettingsPage; memberId?: string; onNavigate: (page: MemorySettingsPage, memberId: string) => void }) {
  const { collection, activeMemberId } = useMembers();
  const member = memberId ? collection.members.find(item => item.member_id === memberId)
    : collection.members.find(item => item.member_id === activeMemberId) ?? collection.members.find(item => item.member_id === collection.default_member_id) ?? collection.members[0];
  if (!member) return <p>{memberId ? '此成员不存在或暂无访问权限。' : '暂无可访问的成员。'}</p>;
  return <section className="memory-settings-page" aria-label="长期记忆设置">
    <GroupedList density="standard" layout="fields"><label className="field-row"><span>成员</span><SelectPopover ariaLabel="选择成员" density="compact" interactionOwner="self" menuWidth="content" menuAlign="end" value={member.member_id}
      options={collection.members.map(item => ({ value: item.member_id, label: memberLabel(item), triggerLabel: memberDisplayName(item) }))}
      onChange={id => onNavigate(page, id)} /></label></GroupedList>
    {page === 'root' ? <GroupedList density="standard" layout="navigation" aria-label="长期记忆设置项目">{pages.map(key => <ModelCapabilityNavigationRow key={key} label={memorySettingsTitles[key]} onClick={() => onNavigate(key, member.member_id)} />)}</GroupedList>
      : <MemoryFormationSettings key={member.member_id} memberId={member.member_id} accessRevision={collection.access_revision} />}
  </section>;
}
