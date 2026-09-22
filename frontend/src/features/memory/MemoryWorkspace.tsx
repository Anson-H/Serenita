import {useMemoryFilters} from './useMemoryFilters';
import {MemoryFilters} from './MemoryFilters';
import {useMemoryRefresh} from './useMemoryRefresh';
import type {MemoryCitation} from './memoryChangePresentation';
import { randomUuid } from "../../utils/randomUuid";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { Member } from "../../api/accounts/memberApi";
import { readMemory, retryMemoryProcessing, resumeMemoryProcessing, cancelMemoryProcessing, type MemoryObject, type MemoryRead, type MemoryReadQuery, type MemoryReference, type MemorySettings } from "../../api/memory/memoryApi";
import {SelectPopover} from "../../components/SelectPopover";
import {memberLabel,memberDisplayName} from "../members/memberPresentation";
import {ControlRowContent} from "../../components/ControlRowContent";
import {ContentDialog} from "../../components/ContentDialog";
import { WorkspaceToolbar } from "../../components/WorkspaceToolbar";
import { MemoryObjectView } from "./MemoryObjectView";
import {MemoryGaps} from './MemoryGaps';
import {MemoryGraphPane} from './MemoryGraphPane';
import {MemoryChanges} from './MemoryChanges';
import type {RoutePath} from '../../app/routes';
import {GroupedList} from '../../components/GroupedList';
import {ChevronRightIcon} from '../../components/icons';
import {captureAuthContext} from "../../api/auth/authLifecycle";
import { memoryTime, objectTitle, object, text } from "./memoryPresentation";
import "../../styles/memory.css";

export const memorySections = {
  episodes: {label:"事项", kinds:["episode"]}
};
export type MemorySection = keyof typeof memorySections;
export function MemoryWorkspace({member, accessRevision, members, onSelectMember, sidebarToggle, onNavigate}: {
  member: Member; accessRevision: number; members: Member[]; onSelectMember: (id:string)=>Promise<void>; sidebarToggle: ReactNode;
  onNavigate: (path: RoutePath) => void;
}) {
  const [section, setSection] = useState<MemorySection | 'changes' | null>(null);
  const [contentNavigation,setContentNavigation] = useState<{title:string;onBack:()=>void}|null>(null);
  const accountId = captureAuthContext().accountId;
  const scopeKey = `${accountId}:${member.member_id}:${member.permission}:${accessRevision}`;
  const closeSection = useCallback(() => {setSection(null);setContentNavigation(null);}, []);
  return <section className="memory-workspace memory-workspace--graph" aria-label={`${member.member_name}的长期记忆`}>
    <WorkspaceToolbar className="workspace-titlebar" title="记忆图谱" showBack={false}
      leading={<>{sidebarToggle}<div className="chat-member-control"><SelectPopover ariaLabel="选择成员" density="compact" interactionOwner="self" menuWidth="content" menuAlign="end" value={member.member_id}
        options={members.map(item=>({value:item.member_id,label:memberLabel(item),triggerLabel:memberDisplayName(item)}))} onChange={onSelectMember}/></div></>}/>
    <main className="memory-reading memory-graph-reading" aria-label="记忆图谱">
      <MemoryContent key={scopeKey} member={member} accessRevision={accessRevision} selectedSection="graph" paused={section !== null}/>
      <nav className="memory-floating-navigation" aria-label="长期记忆栏目">
        <button type="button" className="control control--secondary" aria-haspopup="dialog" onClick={()=>setSection('changes')}>变更记录</button>
        <button type="button" className="control control--secondary" aria-haspopup="dialog" onClick={()=>setSection('episodes')}>事项</button>
      </nav>
    </main>
    {section ? <ContentDialog title={contentNavigation?.title ?? (section === 'changes' ? '变更记录' : '事项')}
      onClose={closeSection} onBack={contentNavigation?.onBack} bodyClassName="memory-reading memory-section-dialog-body">
      <div key={`${scopeKey}:${section}`}>
        {section === 'changes' ? <MemoryChanges memberId={member.member_id} onNavigate={onNavigate} onNavigationChange={setContentNavigation}/> :
          <MemoryContent member={member} accessRevision={accessRevision} selectedSection={section} onNavigationChange={setContentNavigation}/>}
      </div>
    </ContentDialog> : null}
  </section>;
}

export function MemoryContent({member, accessRevision, selectedSection, onNavigationChange, paused = false}: {
  member: Member; accessRevision: number; selectedSection: MemorySection | 'graph'; paused?: boolean; onNavigationChange?:(value:{title:string;onBack:()=>void}|null)=>void;
}) {
  const accountId = captureAuthContext().accountId;
  const graphScope = useRef<MemoryReadQuery>({view:"current"});
  const [graphEpisode,setGraphEpisode]=useState<{id:string;version?:number}|undefined>();
  const section = graphEpisode ? "graph" : selectedSection;
  useEffect(()=>setGraphEpisode(undefined),[member.member_id,selectedSection]);
  const filters = useMemoryFilters(`serenita:memory-filters:${accountId}:${member.member_id}:${selectedSection}`);
  const {query} = filters;
  const [result, setResult] = useState<MemoryRead | null>(null);
  const [settings, setSettings] = useState<MemorySettings | null>(null);
  const [stack, setStack] = useState<{object:MemoryObject;citation?:MemoryCitation}[]>([]);
  const [graphDialog,setGraphDialog]=useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refresh, setRefresh] = useState(0);
  const sequence = useRef(0);
  const detailAbort = useRef<AbortController | null>(null);
  const pendingOperation = useRef({command:'',id:''});
  function operationId(command:unknown){const key=JSON.stringify([member.member_id,command]);if(pendingOperation.current.command!==key)pendingOperation.current={command:key,id:randomUuid()};return pendingOperation.current.id;}
  const baseQuery = useMemo(() => ({...query, object_types:section==='graph'?['event']:memorySections[section].kinds, limit:24}), [query, section]);

  const readCatalog = readMemory;

  useEffect(() => {
    const refreshRead = () => { detailAbort.current?.abort(); setStack([]); setGraphDialog(false); setResult(null); setRefresh(value => value + 1); };
    const visible = () => { if (document.visibilityState === "visible") refreshRead(); };
    window.addEventListener("focus", refreshRead);
    window.addEventListener("serenita:member-access-changed", refreshRead);
    document.addEventListener("visibilitychange", visible);
    return () => { window.removeEventListener("focus", refreshRead); window.removeEventListener("serenita:member-access-changed", refreshRead); document.removeEventListener("visibilitychange", visible); detailAbort.current?.abort(); };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const token = ++sequence.current;
    detailAbort.current?.abort(); setStack([]); setGraphDialog(false); setResult(null); setLoading(true); setError(""); setBusy(false);
    if(section==='graph'){setLoading(false);return()=>controller.abort();}
    void readCatalog(member.member_id, baseQuery, controller.signal).then(value => {
      if (token !== sequence.current) return;
      setResult(value); setSettings(value.settings);
    }).catch(cause => { if (!controller.signal.aborted && token === sequence.current) {setResult(null); setSettings(null); setError(cause instanceof Error && cause.message ? cause.message : "当前内容不可查看，请刷新后重试。");} })
      .finally(() => {if (token === sequence.current && !controller.signal.aborted) setLoading(false);});
    return () => controller.abort();
  }, [member.member_id, member.permission, accessRevision, baseQuery, refresh]);

  const loadedCount = result?.objects.length ?? 0;
  const refreshCatalog = useCallback(async (signal: AbortSignal) => {
    const token = sequence.current;
    try {
      let value = await readCatalog(member.member_id, baseQuery, signal);
      while (value.next_cursor && value.objects.length < loadedCount && !signal.aborted) {
        const next = await readCatalog(member.member_id, {...baseQuery, record_cutoff:value.record_cutoff, cursor:value.next_cursor}, signal);
        value = {...next, objects:[...value.objects, ...next.objects]};
      }
      if (!signal.aborted && token === sequence.current) {
        setResult(value); setSettings(value.settings); setError('');
      }
    } catch (cause) {
      if (!signal.aborted && token === sequence.current) setError(cause instanceof Error ? cause.message : '记忆读取失败，请稍后重试。');
    }
  }, [member.member_id, baseQuery, readCatalog, loadedCount]);
  useMemoryRefresh(refreshCatalog, section !== 'graph' && !loading && !busy && !stack.length && !filters.invalid);

  const closeGraphDialog = useCallback(()=>{detailAbort.current?.abort();setGraphDialog(false);setStack([]);setBusy(false);setError("");},[]);
  async function openEvidence(reference: MemoryReference, related: MemoryReference[] = [], citation?:MemoryCitation) {
    if(section==='graph')setGraphDialog(true);
    detailAbort.current?.abort(); const controller = new AbortController(); detailAbort.current=controller;
    const token = sequence.current; setError(""); setBusy(true);
    try {
      const value = await readMemory(member.member_id, {...(section==='graph'?graphScope.current:{...query,record_cutoff:result?.record_cutoff}), references:[reference]}, controller.signal);
      if (!controller.signal.aborted && token === sequence.current) {
        if (!value.objects.length) {setStack([]);setError("该依据不在所选截点或当前权限内。请刷新后读取。");}
        else setStack(current => [...current, {citation,object:{...value.objects[0], related_references:[...(Array.isArray(value.objects[0].related_references)?value.objects[0].related_references:[]),...related]}}]);
      }
    } catch (cause) {if(!controller.signal.aborted && token === sequence.current) {setStack([]);setResult(null);setError(cause instanceof Error && cause.message ? cause.message : "当前依据不可读取。");}}
    finally {if(!controller.signal.aborted)setBusy(false);}
  }
  async function loadMore() {
    if (!result?.next_cursor || busy) return;
    const token=sequence.current;setBusy(true);
    try {const value=await readCatalog(member.member_id,{...baseQuery,record_cutoff:result.record_cutoff,cursor:result.next_cursor});
      if(token===sequence.current)setResult(current=>current?{...value,objects:[...current.objects,...value.objects]}:null);
    } catch(cause){if(token===sequence.current){setResult(null);setStack([]);setError(cause instanceof Error?cause.message:"读取失败。");}}
    finally{setBusy(false);}
  }
  async function processingAction(attempt: string, action: 'resume'|'retry'|'cancel') {
    if(busy || !member.can_edit)return;
    const token=sequence.current;setBusy(true);setError("");
    try{if(action==='cancel')await cancelMemoryProcessing(member.member_id,attempt);
      else await (action==='resume'?resumeMemoryProcessing:retryMemoryProcessing)(member.member_id,attempt,operationId([action,attempt]));pendingOperation.current={command:'',id:''};
      if(token===sequence.current){setStack([]);setRefresh(value=>value+1);}
    }catch(cause){if(token===sequence.current)setError(cause instanceof Error?cause.message:"处理操作未完成。");}finally{setBusy(false);}
  }
  useEffect(() => {
    if (selectedSection === 'graph') return;
    const current = stack[stack.length - 1];
    onNavigationChange?.(graphEpisode ? {title:'事项图谱',onBack:()=>setGraphEpisode(undefined)} : current ? {
      title:objectTitle(current.object),onBack:()=>{detailAbort.current?.abort();setBusy(false);setError('');setStack(value=>value.slice(0,-1));}
    } : null);
    return ()=>onNavigationChange?.(null);
  }, [stack,graphEpisode,selectedSection,onNavigationChange]);
  const currentActions = member.can_edit && settings?.can_append;
  const processingControls = {busy, onRetry:currentActions?(attempt:string)=>void processingAction(attempt,'retry'):undefined,
    onResume:currentActions?(attempt:string)=>void processingAction(attempt,'resume'):undefined,
    onCancel:currentActions?(attempt:string)=>void processingAction(attempt,'cancel'):undefined,
    onGraph:(episode:string,version?:number)=>{detailAbort.current?.abort();setGraphDialog(false);setGraphEpisode({id:episode,version});setStack([]);}};

  return <div className={`memory-content${section==='graph'?' memory-content--graph':''}`}>
      {!member.can_edit&&section!=='graph'?<p className="memory-metadata">只读权限</p>:null}
      {section!=='graph'?<>{!stack.length?<MemoryFilters state={filters}/>:null}
      {result&&query.target_time?<p className="memory-reading-scope" role="status">{memoryTime(query.target_time)}</p>:null}
      {error?<p role="alert" className="memory-error">{error}{error.includes("模型")?<a href="/setting/providers">配置模型</a>:null}</p>:null}{loading?<p role="status">正在加载记忆…</p>:null}</>:null}
      {stack.length&&section!=='graph'?<section className="memory-evidence-panel" aria-label="展开的依据"><MemoryObjectView memberId={member.member_id} recordCutoff={result?.record_cutoff} row={stack[stack.length-1].object} citation={stack[stack.length-1].citation} onRead={(reference,citation)=>void openEvidence(reference,[],citation)} {...processingControls}/></section>:null}
      {section==='graph'&&graphDialog?<ContentDialog title={stack.length&&stack[stack.length-1].object.object_type!=='event'?objectTitle(stack[stack.length-1].object):'事件详情'} onClose={closeGraphDialog} onBack={stack.length>1?()=>{detailAbort.current?.abort();setBusy(false);setStack(value=>value.slice(0,-1));}:undefined} bodyClassName="memory-graph-dialog-body">
        {busy?<p role="status">正在加载详情…</p>:null}{error?<p role="alert" className="memory-error">{error}</p>:null}
        {stack.length?<MemoryObjectView memberId={member.member_id} recordCutoff={graphScope.current.record_cutoff} row={stack[stack.length-1].object} citation={stack[stack.length-1].citation} onRead={(reference,citation)=>void openEvidence(reference,[],citation)} onGraph={processingControls.onGraph}/>:null}
      </ContentDialog>:null}
      {section==='graph'?<MemoryGraphPane key={`${accountId}:${member.member_id}:${member.permission}`} accountId={accountId} memberId={member.member_id} accessRevision={accessRevision} episodeId={graphEpisode?.id} initialVersion={graphEpisode?.version} refresh={refresh} paused={paused || graphDialog} onScopeChange={closeGraphDialog} onRead={(reference,related,scope)=>{graphScope.current=scope;void openEvidence(reference,related);}} onMemberGraph={()=>setGraphEpisode(undefined)}/>:null}
      {!stack.length && result && section!=='graph' ? <>{result.objects.length ? <GroupedList density="standard" className="memory-episode-list">{result.objects.map(row=><button type="button" className="control control--row memory-navigation-row" key={text(row.episode_id)} onClick={()=>setStack([{object:row}])}><ControlRowContent title={objectTitle(row)} description={text(object(row.current_revision).summary)} singleLineDescription/><ChevronRightIcon/></button>)}</GroupedList>:
        <p className="memory-empty">所选范围尚无可读取内容。</p>}
        <p className="memory-metadata">已读取 {result.objects.length} / {result.coverage.matching_objects} 项{result.next_cursor?" · 还有未读内容":" · 本次匹配范围已读取"}</p>
        {result.next_cursor?<button className="control control--secondary" type="button" disabled={busy} onClick={()=>void loadMore()}>加载更多</button>:null}
        <MemoryGaps label="本次读取缺口" values={result.gaps} onRead={reference=>void openEvidence(reference)}/><MemoryGaps label="本次未读内容" values={result.unread} onRead={reference=>void openEvidence(reference)}/>
      </>:null}
  </div>;
}
