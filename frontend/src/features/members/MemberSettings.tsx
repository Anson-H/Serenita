import { useEffect, useState } from "react";
import { fetchMemberGrants, revokeMemberGrant, saveMemberPreferences, setMemberGrants, type MemberGrant } from "../../api/memberApi";
import { GroupedList } from "../../components/GroupedList";
import { SelectPopover } from "../../components/SelectPopover";
import { CheckIcon, TrashIcon } from "../../components/icons";
import { useMembers } from "./MemberProvider";
import { memberLabel } from "./memberPresentation";

export function MembersPanel() {
  const { collection, refresh } = useMembers();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  return (
    <section className="settings-section">
      <GroupedList layout="fields" density="standard">
        <div className="field-row">
          <span>首次打开</span>
          <SelectPopover
            ariaLabel="首次打开的成员"
            disabled={busy}
            menuWidth="content" menuAlign="end" interactionOwner="row"
            value={collection.startup_mode}
            options={[
              { value: "last_used", label: "记住上次选择" },
              { value: "default", label: "每次打开选择默认成员" }
            ]}
            onChange={async startup_mode => {
              setBusy(true);
              setError("");
              try {
                await saveMemberPreferences({ startup_mode });
                await refresh();
              } catch (cause) {
                setError(cause instanceof Error ? cause.message : "设置未保存。");
              } finally {
                setBusy(false);
              }
            }}
          />
        </div>
      </GroupedList>
      {error ? <p className="content-description" role="alert">{error}</p> : null}
    </section>
  );
}

export function MemberGrantsPanel() {
  const { collection, refresh } = useMembers();
  const owned = collection.members.filter(member => member.is_owned);
  const [grants, setGrants] = useState<MemberGrant[]>([]);
  const [recipient, setRecipient] = useState("");
  const [selection, setSelection] = useState<Record<string, "read" | "edit">>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [feedback, setFeedback] = useState("");
  useEffect(() => { let disposed = false;
    void fetchMemberGrants().then(result => { if (!disposed) setGrants(result.grants); }).catch(cause => { if (!disposed) setError(cause.message); });
    return () => { disposed = true; };
  }, [collection.access_revision]);
  async function mutate(action: () => Promise<{ grants: MemberGrant[] }>, message: string) {
    if (busy) return;
    setBusy(true); setError(""); setFeedback("");
    try { setGrants((await action()).grants); await refresh(); setFeedback(message); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "授权未保存。"); }
    finally { setBusy(false); }
  }
  return <section className="settings-section member-grants-section">
    <p className="content-description">仅共享选中成员的健康档案，不共享聊天、附件、收藏或账号设置。以后新增的成员不会自动共享。</p>
    <form onSubmit={event => { event.preventDefault(); void mutate(() => setMemberGrants(recipient.trim(), Object.entries(selection).map(([member_id, permission]) => ({ member_id, permission }))), "授权已生效。"); }}>
      <GroupedList layout="fields" density="standard"><label className="field-row"><span>接收方用户标识</span><input autoCapitalize="none" autoComplete="off" spellCheck={false} required maxLength={20} disabled={busy} value={recipient} onChange={event => setRecipient(event.target.value)} placeholder="准确的用户标识" /></label></GroupedList>
      <div className="member-settings-group">
      <div className="group-heading"><h2>成员选择与健康档案权限</h2></div>
      <GroupedList density="standard" selectionMode="multiple" className="member-grant-list">
        {owned.map(member => <div className="field-row member-grant-row" key={member.member_id}>
          <button className="member-grant-toggle" data-interaction-owner="row" type="button" role="checkbox" aria-checked={Boolean(selection[member.member_id])} disabled={busy} onClick={() => setSelection(current => { const next = { ...current }; if (next[member.member_id]) delete next[member.member_id]; else next[member.member_id] = "read"; return next; })}>
            <span aria-hidden="true" className="selection-check-control" data-selected={selection[member.member_id] ? "true" : undefined}>{selection[member.member_id] ? <CheckIcon className="selection-check-icon" /> : null}</span>
            <span>{memberLabel(member)}</span>
          </button>
          <SelectPopover ariaLabel={`${member.member_name}的授权权限`} disabled={busy || !selection[member.member_id]} menuWidth="content" menuAlign="end" interactionOwner="self" value={selection[member.member_id] ?? "read"} options={[{ value: "read", label: "只读" }, { value: "edit", label: "编辑" }]} onChange={permission => setSelection({ ...selection, [member.member_id]: permission })} />
        </div>)}
      </GroupedList>
      </div>
      <p className="content-description">编辑权限可修改基础资料、导入和删除报告、保存解读结果；接收方不能再次授权。</p>
      <button className="control control--primary" type="submit" disabled={busy || !recipient.trim() || !Object.keys(selection).length}><CheckIcon /><span>授予权限</span></button>
    </form>
    {error ? <p role="alert">{error}</p> : null}{feedback ? <p role="status">{feedback}</p> : null}
    <div className="member-settings-group">
    <div className="group-heading"><h2>已授权</h2></div>
    {grants.length ? <GroupedList density="standard" className="member-grant-list">{grants.map(grant => <div className="field-row member-grant-row" data-hover="none" key={`${grant.member_id}:${grant.account_id}`}>
      <div className="member-grant-identity"><span>{owned.find(member => member.member_id === grant.member_id)?.member_name}</span><span>{grant.grantee_account}</span></div>
      <SelectPopover ariaLabel={`${grant.grantee_account}的健康档案权限`} disabled={busy} menuWidth="content" menuAlign="end" interactionOwner="self" value={grant.permission} options={[{ value: "read", label: "只读" }, { value: "edit", label: "编辑" }]} onChange={permission => mutate(() => setMemberGrants(grant.grantee_account, [{ member_id: grant.member_id, permission }]), "权限已更新。")} />
      <button className="control control--inline control--icon control--danger" data-interaction-owner="self" aria-label="撤销" title="撤销授权" type="button" disabled={busy} onClick={() => void mutate(() => revokeMemberGrant(grant.member_id, grant.account_id), "授权已撤销。")}><TrashIcon /></button>
    </div>)}</GroupedList> : <p className="member-grants-empty">尚未向其他账号共享健康档案。</p>}
    </div>
  </section>;
}
