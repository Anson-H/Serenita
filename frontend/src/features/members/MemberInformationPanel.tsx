import { useEffect, useRef, useState, type FormEvent, type RefObject, type SetStateAction } from "react";
import { saveMemberPreferences, updateMember, type Member, type MemberFields } from "../../api/memberApi";
import { GroupedList, ReadonlyField } from "../../components/GroupedList";
import { TrashIcon } from "../../components/icons";
import { WorkspaceToolbar } from "../../components/WorkspaceToolbar";
import { useActiveScope } from "../../utils/useActiveScope";
import { DefaultMemberField } from "./DefaultMemberField";
import { MemberFieldsEditor } from "./MemberFieldsEditor";
import { useMembers } from "./MemberProvider";

const memberAutoSaveDelayMs = 400;

type MemberSnapshot = {
  draft: MemberFields;
  setAsDefault: boolean;
};

function snapshotKey(snapshot: MemberSnapshot) {
  return JSON.stringify(snapshot);
}

export function MemberInformationPanel({ member, onClose, panelRef }: {
  member: Member;
  onClose: () => void;
  panelRef?: RefObject<HTMLElement | null>;
}) {
  const members = useMembers();
  const isCurrent = useActiveScope(member.member_id);
  const initialDraft: MemberFields = {
    member_name: member.member_name, sex: member.sex, birth_date: member.birth_date,
    blood_type: member.blood_type
  };
  const [draft, setDraft] = useState<MemberFields>(initialDraft);
  const [setAsDefault, setSetAsDefault] = useState(false);
  const isDefault = members.collection.default_member_id === member.member_id;
  const canDelete = member.is_owned;
  const [closing, setClosing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");
  const latestSnapshotRef = useRef<MemberSnapshot>({ draft: initialDraft, setAsDefault: false });
  const savedKeyRef = useRef(snapshotKey(latestSnapshotRef.current));
  const requestedKeyRef = useRef(savedKeyRef.current);
  const saveChainRef = useRef<Promise<boolean>>(Promise.resolve(true));
  const autoSaveHandleRef = useRef<number | null>(null);
  const deletingRef = useRef(false);
  const persistOnUnmountRef = useRef<() => void>(() => undefined);
  const busy = closing || deleting;

  function canPersist(snapshot: MemberSnapshot) {
    return member.can_edit ? Boolean(snapshot.draft.member_name.trim()) : snapshot.setAsDefault && !isDefault;
  }

  function queueSave(snapshot: MemberSnapshot) {
    const key = snapshotKey(snapshot);
    if (key === requestedKeyRef.current) return saveChainRef.current;
    if (!canPersist(snapshot)) return Promise.resolve(false);
    requestedKeyRef.current = key;
    const task = saveChainRef.current.then(async () => {
      try {
        if (member.can_edit) {
          await updateMember(member.member_id, {
            ...snapshot.draft,
            set_as_default: snapshot.setAsDefault && !isDefault
          });
        } else {
          await saveMemberPreferences({ default_member_id: member.member_id });
        }
        await members.refresh();
        savedKeyRef.current = key;
        if (isCurrent()) setError("");
        return true;
      } catch (cause) {
        if (requestedKeyRef.current === key) requestedKeyRef.current = "";
        if (isCurrent()) setError(cause instanceof Error ? cause.message : "成员信息未保存。");
        return false;
      }
    });
    saveChainRef.current = task;
    return task;
  }

  async function flushLatest() {
    if (autoSaveHandleRef.current !== null) {
      window.clearTimeout(autoSaveHandleRef.current);
      autoSaveHandleRef.current = null;
    }
    const snapshot = latestSnapshotRef.current;
    if (snapshotKey(snapshot) === savedKeyRef.current && requestedKeyRef.current === savedKeyRef.current) {
      return true;
    }
    if (!canPersist(snapshot)) {
      if (isCurrent() && member.can_edit) setError("成员名称不能为空。");
      return false;
    }
    return queueSave(snapshot);
  }

  async function requestClose() {
    if (busy) return;
    setClosing(true);
    const saved = await flushLatest();
    if (!isCurrent()) return;
    if (saved) onClose();
    else setClosing(false);
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void flushLatest();
  }

  function changeDraft(update: SetStateAction<MemberFields>) {
    const current = latestSnapshotRef.current.draft;
    const next = typeof update === "function" ? update(current) : update;
    latestSnapshotRef.current = { ...latestSnapshotRef.current, draft: next };
    setError("");
    setDraft(next);
  }

  function changeDefault(value: boolean) {
    latestSnapshotRef.current = {
      ...latestSnapshotRef.current,
      setAsDefault: value,
    };
    setError("");
    setSetAsDefault(value);
  }

  async function remove() {
    if (busy || !canDelete) return;
    deletingRef.current = true;
    setDeleting(true); setError("");
    if (autoSaveHandleRef.current !== null) {
      window.clearTimeout(autoSaveHandleRef.current);
      autoSaveHandleRef.current = null;
    }
    try {
      await saveChainRef.current;
      await members.removeMember(member.member_id);
      if (isCurrent()) onClose();
    } catch (cause) {
      deletingRef.current = false;
      if (isCurrent()) setError(cause instanceof Error ? cause.message : "成员未删除。");
    } finally { if (isCurrent()) setDeleting(false); }
  }

  useEffect(() => {
    if (busy) return;
    const snapshot = latestSnapshotRef.current;
    const key = snapshotKey(snapshot);
    if (key === requestedKeyRef.current || !canPersist(snapshot)) return;
    autoSaveHandleRef.current = window.setTimeout(() => {
      autoSaveHandleRef.current = null;
      void queueSave(snapshot);
    }, memberAutoSaveDelayMs);
    return () => {
      if (autoSaveHandleRef.current !== null) {
        window.clearTimeout(autoSaveHandleRef.current);
        autoSaveHandleRef.current = null;
      }
    };
  }, [draft, setAsDefault, busy]);

  persistOnUnmountRef.current = () => {
    if (autoSaveHandleRef.current !== null) {
      window.clearTimeout(autoSaveHandleRef.current);
      autoSaveHandleRef.current = null;
    }
    const snapshot = latestSnapshotRef.current;
    if (!deletingRef.current && snapshotKey(snapshot) !== savedKeyRef.current && canPersist(snapshot)) {
      void queueSave(snapshot);
    }
  };
  useEffect(() => () => persistOnUnmountRef.current(), []);

  return <section aria-label="个人信息" className="member-information-detail" id="member-information-detail" ref={(node) => {
    if (panelRef) panelRef.current = node;
  }} tabIndex={-1}>
    <WorkspaceToolbar className="member-information-toolbar" onBack={() => void requestClose()} title="个人信息" />
    <form className="member-information-pane" onSubmit={submit}>
      <div className="member-information-scroll scroll-content">
        <GroupedList layout="fields" density="standard">
          {member.can_edit ? <MemberFieldsEditor value={draft} disabled={busy} onChange={changeDraft} /> : <>
            <ReadonlyField label="成员名称" value={member.member_name} />
            <ReadonlyField label="性别" value={member.sex ? { male: "男", female: "女", other: "其他" }[member.sex] : "未设置"} />
            <ReadonlyField label="出生日期" value={member.birth_date || "未设置"} />
            <ReadonlyField label="血型" value={member.blood_type ? { a: "A 型", b: "B 型", ab: "AB 型", o: "O 型", other: "其他" }[member.blood_type] : "未设置"} />
          </>}
          <DefaultMemberField isDefault={isDefault} value={setAsDefault} disabled={busy} onChange={changeDefault} />
        </GroupedList>
        {!member.is_owned ? <p className="content-description">来自 {member.owner_account} 的共享健康档案 · {member.can_edit ? "可编辑" : "只读"}</p> : null}
        {member.is_owned ? <div className="member-settings-group">
          <button className="control control--danger" type="button" disabled={busy || !canDelete} onClick={() => void remove()}><TrashIcon /><span>删除成员</span></button>
        </div> : null}
        {error ? <p role="alert">{error}</p> : null}
      </div>
    </form>
  </section>;
}
