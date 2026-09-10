import { hasNavigationSaves, saveBeforeNavigation } from "../../utils/pendingNavigation";
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { deleteMember, fetchMembers, saveMemberPreferences, subscribeMemberAccess, type Member, type MemberCollection, type MemberDeletion } from "../../api/memberApi";
import { ApiRequestError } from "../../api/request";
import { showStatusNotification } from "../../components/StatusNotificationCenter";
import { useActiveScope } from "../../utils/useActiveScope";

export type MemberDestination = { type: "chat" } | { type: "health" } | { type: "reports"; reportId?: string };

type MemberState = {
  collection: MemberCollection;
  activeMember: Member | null;
  activeMemberId: string | null;
  selectionVersion: number;
  selectMember: (id: string | null, destination?: MemberDestination) => Promise<void>;
  adoptConversationMember: (id: string | null) => void;
  refresh: () => Promise<void>;
  removeMember: (id: string) => Promise<MemberDeletion>;
};

const MemberContext = createContext<MemberState | null>(null);

export function MemberProvider({ children, onStartMember }: { children: ReactNode; onStartMember: (destination: MemberDestination, memberId: string | null) => void }) {
  const [collection, setCollection] = useState<MemberCollection | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [selectionVersion, setSelectionVersion] = useState(0);
  const [error, setError] = useState("");
  const activeIdRef = useRef<string | null>(null);
  const collectionRevision = useRef(-1);
  const deleting = useRef<{ id: string; selection: number } | null>(null);
  const requestSequence = useRef(0);
  const selectionSequence = useRef(0);
  const selectionWrites = useRef<Promise<unknown>>(Promise.resolve());
  const isMounted = useActiveScope("members");
  const startRef = useRef(onStartMember);
  startRef.current = onStartMember;

  const applyCollection = useCallback((next: MemberCollection) => {
    if (next.access_revision < collectionRevision.current) return;
    const initialized = collectionRevision.current >= 0;
    collectionRevision.current = next.access_revision;
    const prior = activeIdRef.current;
    const valid = prior === null || next.members.some(member => member.member_id === prior);
    const id = initialized ? valid ? prior : next.default_member_id : next.initial_member_id;
    setCollection(next);
    activeIdRef.current = id;
    setActiveId(id);
    setError("");
    if (prior !== null && !valid) {
      const destination: MemberDestination = deleting.current?.id === prior && deleting.current.selection === selectionSequence.current
        ? id === null ? { type: "chat" } : { type: "health" }
        : { type: "chat" };
      selectionSequence.current += 1;
      startRef.current(destination, id);
      setSelectionVersion(value => value + 1);
    }
  }, []);

  const refresh = useCallback(async () => {
    const sequence = ++requestSequence.current;
    const next = await fetchMembers();
    if (sequence === requestSequence.current) applyCollection(next);
  }, [applyCollection]);

  async function removeMember(id: string) {
    deleting.current = { id, selection: selectionSequence.current };
    try {
      const result = await deleteMember(id);
      if (isMounted()) {
        requestSequence.current += 1;
        applyCollection(result.collection);
        if (result.pending_file_cleanup) showStatusNotification({ tone: "warning", message: "成员已删除，部分原件尚未清理完成，将在后续访问时重试。" });
      }
      return result;
    } finally { deleting.current = null; }
  }

  useEffect(() => {
    let disposed = false;
    const reload = () => { void refresh().catch(cause => { if (!disposed) setError(cause instanceof Error ? cause.message : "成员加载失败。"); }); };
    const onVisible = () => { if (document.visibilityState === "visible") reload(); };
    reload();
    const unsubscribeAccess = subscribeMemberAccess(reload);
    window.addEventListener("focus", reload);
    window.addEventListener("serenita:member-access-changed", reload);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      disposed = true;
      requestSequence.current += 1;
      selectionSequence.current += 1;
      unsubscribeAccess();
      window.removeEventListener("focus", reload);
      window.removeEventListener("serenita:member-access-changed", reload);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [refresh]);

  function persistSelection(id: string | null) {
    const write = selectionWrites.current.catch(() => undefined).then(() => {
      if (!isMounted()) return;
      return saveMemberPreferences({ last_member_id: id });
    });
    selectionWrites.current = write;
    return write;
  }

  async function selectMember(id: string | null, destination: MemberDestination = { type: "chat" }) {
    if (hasNavigationSaves() && !await saveBeforeNavigation()) return;
    const sequence = ++selectionSequence.current;
    try {
      await persistSelection(id);
      if (!isMounted() || sequence !== selectionSequence.current) return;
      activeIdRef.current = id;
      setActiveId(id);
      startRef.current(destination, id);
      setSelectionVersion(value => value + 1);
    } catch (cause) {
      if (!isMounted() || sequence !== selectionSequence.current) return;
      if (cause instanceof ApiRequestError && cause.detail?.code === "MEMBER_ACCESS_UNAVAILABLE") {
        await refresh();
      } else {
        setError(cause instanceof Error ? cause.message : "成员选择未保存。");
      }
    }
  }

  function adoptConversationMember(id: string | null) {
    if (id === activeIdRef.current || (id !== null && !collection?.members.some(member => member.member_id === id))) return;
    activeIdRef.current = id;
    setActiveId(id);
    selectionSequence.current += 1;
    void persistSelection(id).catch(() => isMounted() ? refresh().catch(() => undefined) : undefined);
  }

  const activeMember = collection?.members.find(member => member.member_id === activeId) ?? null;
  if (!collection) {
    return <main className="login-page"><section className="auth-panel"><div className="brand-name">Serenita</div>
      <p role={error ? "alert" : "status"}>{error || "正在读取成员…"}</p>
      {error ? <button className="control control--secondary" onClick={() => void refresh().catch(() => undefined)}>重新加载</button> : null}
    </section></main>;
  }
  return <MemberContext.Provider value={{ collection, activeMember, activeMemberId: activeId, selectionVersion, selectMember, adoptConversationMember, refresh, removeMember }}>
    {error ? <div className="member-load-error" role="alert">{error}<button className="control control--compact" onClick={() => setError("")}>关闭</button></div> : null}
    {children}
  </MemberContext.Provider>;
}

export function useMembers() {
  const value = useContext(MemberContext);
  if (!value) throw new Error("Member context is required.");
  return value;
}
