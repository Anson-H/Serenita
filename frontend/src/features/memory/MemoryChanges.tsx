import {MemoryContentCache,MemoryContentStore} from './MemoryStepContent';
import {readMemoryChangeStatus,readMemoryChangeSummaries} from "../../api/memory/memoryApi";
import {useMemoryRefresh} from './useMemoryRefresh';
import {useCallback, useEffect, useLayoutEffect, useRef, useState} from 'react';
import {readMemory, retryMemoryProcessing, resumeMemoryProcessing, cancelMemoryProcessing, readMemoryChange, readMemoryChanges, type MemoryObject, type MemoryReference, type MemoryChange, type MemoryChangeDetail, type MemoryChangePage} from "../../api/memory/memoryApi";
import {modelInputTitle} from './MemoryModelInputs';
import {MemoryModelContent} from './MemoryModelContent';
import {ApiRequestError} from "../../api/transport/request";
import {ControlRowContent} from '../../components/ControlRowContent';
import {ChevronRightIcon} from '../../components/icons';
import {GroupedList, ReadonlyField} from '../../components/GroupedList';
import {memoryTimestamp, memoryStatusLabels, objects, objectTitle} from './memoryPresentation';
import {MemoryProcessingDetail, MemoryProcessingResults, processingTitle, processingStatusSummary} from './MemoryProcessing';
import {MemoryObjectView} from './MemoryObjectView';
import {MemoryProgress} from './MemoryProgress';
import {randomUuid} from '../../utils/randomUuid';
import type {MemoryCitation} from './memoryChangePresentation';
import {MarkdownContent} from '../../components/MarkdownContent';
import type {RoutePath} from '../../app/routes';
import {memoryChangeTargetPath,memoryResourceLabels} from './memoryChangePresentation';

const operationLabels: Record<string, string> = {create: '创建', update: '更新', delete: '删除'};
const changeTitle = (change: MemoryChange) => change.processing ? processingTitle(change.processing) : `${operationLabels[change.operation_kind] ?? change.operation_kind} · ${memoryResourceLabels[change.resource_type] ?? change.resource_type}`;
export function MemoryChanges({memberId, onNavigate, onNavigationChange}: {memberId: string; onNavigate: (path: RoutePath) => void; onNavigationChange:(navigation:{title:string;onBack:()=>void}|null)=>void}) {
  const contentCache=useRef(new MemoryContentStore());
  const [page, setPage] = useState<MemoryChangePage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState<MemoryChange | null>(null);
  const [detail, setDetail] = useState<MemoryChangeDetail | null>(null);
  const [detailError, setDetailError] = useState('');
  const [stack, setStack] = useState<{row:MemoryObject;citation?:MemoryCitation;recordCutoff?:number}[]>([]);
  const [modelView,setModelView]=useState<{entryId:string}|null>(null);
  const [busy, setBusy] = useState(false);
  const scrollPositions=useRef<Record<string,number>>({});
  const viewKey=modelView?`model:${modelView.entryId}`:`detail:${stack.length}`;
  const saveScroll=()=>{scrollPositions.current[viewKey]=(contentRoot.current?.closest('.memory-reading') as HTMLElement|null)?.scrollTop||0;};
  const contentRoot=useRef<HTMLElement|null>(null);
  const listScroll=useRef(0);
  const operation = useRef({command:'', id:''});
  const listAbort = useRef<AbortController | null>(null);
  const detailAbort = useRef<AbortController | null>(null);
  const closeDetail = useCallback(() => {
    contentCache.current.clear(); detailAbort.current?.abort(); setSelected(null); setDetail(null); setDetailError(''); setStack([]); setModelView(null); setBusy(false);
  }, []);
  const load = useCallback(async (cursor?: string) => {
    listAbort.current?.abort(); const controller = new AbortController(); listAbort.current = controller;
    setLoading(true); setError('');
    if (!cursor) {setPage(null); closeDetail();}
    try {
      const result = await readMemoryChanges(memberId, cursor, controller.signal);
      if (!controller.signal.aborted) setPage(current => cursor && current ? {...result, changes: [...current.changes, ...result.changes]} : result);
    } catch (cause) {
      if (!controller.signal.aborted) {setPage(null); closeDetail(); setError(cause instanceof Error ? cause.message : '变更记录读取失败，请刷新后重试。');}
    } finally {if (!controller.signal.aborted) setLoading(false);}
  }, [memberId, closeDetail]);
  useEffect(() => {
    const refresh = () => {void load();};
    refresh();
    window.addEventListener('serenita:member-access-changed', refresh);
    return () => {
      listAbort.current?.abort(); detailAbort.current?.abort();
      window.removeEventListener('serenita:member-access-changed', refresh);
    };
  }, [load]);
  const pageRef = useRef(page);
  pageRef.current = page;
  const syncListStatus = useCallback((value: Pick<MemoryChangeDetail, 'change_id' | 'source_database' | 'memory_status' | 'processing'>) => {
    setPage(current => current ? {...current, changes: current.changes.map(row =>
      row.change_id === value.change_id && row.source_database === value.source_database
        ? {...row, memory_status: value.memory_status, processing: value.processing} : row)} : current);
  }, []);
  const refreshChanges = useCallback(async (signal: AbortSignal) => {
    try {
      if (selected) {
        const value = await readMemoryChangeStatus(memberId, selected, signal);
        if (!signal.aborted) {
          syncListStatus({...selected, ...value});
          if(!value.content_available){contentCache.current.clear();setStack([]);setModelView(null);}
          setDetail(previous=>{
            if(previous&&previous.access_revision!==value.access_revision)contentCache.current.clear();
            return previous?{...previous,...value,...(!value.content_available?{content_text:null,fields:[],targets:[],extraction_results:[],relation_results:[]}: {})}:previous;});setDetailError('');
        }
        return;
      }
      const previous = pageRef.current;
      const key = (row:Pick<MemoryChange,'source_database'|'change_id'>) => `${row.source_database}/${row.change_id}`;
      const known = new Set(previous?.changes.map(key));
      let value = await readMemoryChanges(memberId, undefined, signal);
      // Read further only when genuinely new changes fill the first page.
      while (value.next_cursor && known.size && !value.changes.some(row=>known.has(key(row))) && !signal.aborted) {
        const next = await readMemoryChanges(memberId, value.next_cursor, signal);
        value = {...next, changes:[...value.changes, ...next.changes]};
      }
      const received = new Set(value.changes.map(key));
      const remaining = previous?.changes.filter(row=>!received.has(key(row))) ?? [];
      const updated:MemoryChange[] = [];
      for (let offset=0; offset<remaining.length && !signal.aborted; offset+=100) {
        const batch = remaining.slice(offset,offset+100);
        const statuses = await readMemoryChangeSummaries(memberId,batch,signal);
        const byId = new Map(statuses.changes.map(row=>[key(row),row]));
        updated.push(...batch.flatMap(row=>byId.has(key(row))?[{...row,...byId.get(key(row))!}]:[]));
      }
      const overlap = value.changes.some(row=>known.has(key(row)));
      if (!signal.aborted) {
        setPage({changes:[...value.changes,...updated],next_cursor:overlap && previous ? previous.next_cursor : value.next_cursor});
        setError('');
      }
    } catch (cause) {
      if (!signal.aborted) {
        if(selected&&cause instanceof ApiRequestError&&[401,403,404].includes(cause.status)){
          contentCache.current.clear();
          setStack([]);setModelView(null);
          setDetail(previous=>previous?{...previous,content_available:false,content_text:null,fields:[],targets:[],
            processing:null,model_inputs:[],processing_steps:[],extraction_results:[],relation_results:[]}:null);
        }
        (selected?setDetailError:setError)(cause instanceof Error ? cause.message : '变更记录读取失败，请稍后重试。');
      }
    }
  }, [memberId, selected, syncListStatus]);
  const previousSelection = useRef({memberId, selected: false});
  useEffect(() => {
    const returnedToList = previousSelection.current.memberId === memberId && previousSelection.current.selected && !selected;
    previousSelection.current = {memberId, selected: !!selected};
    if (!returnedToList) return;
    const controller = new AbortController();
    void refreshChanges(controller.signal);
    return () => controller.abort();
  }, [memberId, selected, refreshChanges]);
  useMemoryRefresh(refreshChanges, !loading && !busy && stack.every(item=>['processing_group','processing_result','processing_step','processing_progress_record','processing_unassigned_inputs'].includes(item.row.object_type)) && (!selected || !!detail), true);
  async function openDetail(change: MemoryChange) {
    detailAbort.current?.abort(); const controller = new AbortController(); detailAbort.current = controller;
    listScroll.current=(contentRoot.current?.closest('.memory-reading') as HTMLElement|null)?.scrollTop||0;
    setSelected(change); setDetail(null); setDetailError(''); setStack([]); setModelView(null); scrollPositions.current={};
    try {
      const result = await readMemoryChange(memberId, change, controller.signal);
      if (!controller.signal.aborted) {
        setDetail(result);
        syncListStatus(result);
      }
    } catch (cause) {
      if (!controller.signal.aborted) setDetailError(cause instanceof Error ? cause.message : '变更记录读取失败，请重试。');
    }
  }
  async function openEvidence(reference:MemoryReference, citation?:MemoryCitation) {
    detailAbort.current?.abort(); const controller = new AbortController(); detailAbort.current = controller;
    saveScroll();
    scrollPositions.current[`detail:${stack.length+1}`]=0;
    setBusy(true); setDetailError('');
    try {
      const result = await readMemory(memberId, {references:[reference],record_cutoff:stack.at(-1)?.recordCutoff}, controller.signal);
      if (!controller.signal.aborted) {
        if (!result.objects.length) setDetailError('当前依据不可读取。');
        else setStack(current=>[...current,{row:result.objects[0],citation,recordCutoff:result.record_cutoff}]);
      }
    } catch (cause) {if (!controller.signal.aborted) setDetailError(cause instanceof Error?cause.message:'当前依据不可读取。');}
    finally {if (!controller.signal.aborted) setBusy(false);}
  }
  async function processingAction(attempt:string, action:'resume'|'retry'|'cancel') {
    if (busy || !selected) return;
    const controller = new AbortController(); detailAbort.current?.abort(); detailAbort.current = controller;
    setBusy(true); setDetailError('');
    try {
      if (action !== 'cancel') {
        const command=JSON.stringify([action,attempt]);
        if (operation.current.command !== command) operation.current = {command,id:randomUuid()};
        await (action==='resume'?resumeMemoryProcessing:retryMemoryProcessing)(memberId,attempt,operation.current.id);
      } else await cancelMemoryProcessing(memberId,attempt);
      operation.current = {command:'',id:''};
      const result = await readMemoryChange(memberId,selected,controller.signal);
      if (!controller.signal.aborted) {
        setDetail(result);
        syncListStatus(result);
      }
    } catch (cause) {if (!controller.signal.aborted) setDetailError(cause instanceof Error?cause.message:'处理操作未完成。');}
    finally {if (!controller.signal.aborted) setBusy(false);}
  }
  const controls = {memberId,busy,recordCutoff:stack.at(-1)?.recordCutoff,onRead:(reference:MemoryReference,citation?:MemoryCitation)=>void openEvidence(reference,citation),
    onResume:(attempt:string)=>void processingAction(attempt,'resume'),
    onRetry:(attempt:string)=>void processingAction(attempt,'retry'),onCancel:(attempt:string)=>void processingAction(attempt,'cancel')};
  const back=useCallback(()=>{scrollPositions.current[viewKey]=(contentRoot.current?.closest('.memory-reading') as HTMLElement|null)?.scrollTop||0;detailAbort.current?.abort();setBusy(false);setDetailError('');if(modelView)setModelView(null);else if(stack.length)setStack(current=>current.slice(0,-1));else closeDetail();},[stack.length,modelView,closeDetail,viewKey]);
  const openModelInput=(input:MemoryChangeDetail['model_inputs'][number])=>{
    saveScroll();
    scrollPositions.current[`model:${input.entry_id}`]=0;
    setModelView({entryId:input.entry_id});
  };
  const openProcessing=(row:MemoryObject)=>{saveScroll();scrollPositions.current[`detail:${stack.length+1}`]=0;setStack(current=>[...current,{row,recordCutoff:typeof row.record_cutoff==='number'?row.record_cutoff:current.at(-1)?.recordCutoff}]);};
  const entry = stack[stack.length-1];
  const latest=entry&&['processing_group','processing_result'].includes(entry.row.object_type)&&detail?.processing?{...detail.processing,object_type:entry.row.object_type}
    :entry?.row.object_type==='processing_attempt'?detail?.processing?.records.find(row=>row.object_type==='processing_attempt'&&row.attempt_id===entry.row.attempt_id):null;
  const current=entry?{...entry,row:(latest as MemoryObject)||entry.row}:null;
  const modelInput=detail?.model_inputs?.find(input=>input.entry_id===modelView?.entryId);
  const title=modelView?(modelInput?modelInputTitle(modelInput):'模型输入详情'):current?current.row.object_type==='processing_group'?'处理步骤':current.row.object_type==='processing_result'?'处理结果':objectTitle(current.row):'变更记录详情';
  useLayoutEffect(()=>{onNavigationChange(selected?{title,onBack:back}:null);return()=>onNavigationChange(null);},[selected,title,back,onNavigationChange]);
  useEffect(()=>{const root=contentRoot.current?.closest('.memory-reading') as HTMLElement|null;if(root)root.scrollTop=selected?(scrollPositions.current[viewKey]||0):listScroll.current;},[selected?.change_id,viewKey]);
  const targets = detail?.content_available ? detail.targets : [];
  return <MemoryContentCache.Provider value={contentCache.current}><section ref={contentRoot} className="memory-content memory-changes" aria-label="变更记录">
    {!selected?<>
    {error ? <p role="alert" className="memory-error">{error}{error.includes("模型")?<a href="/setting/providers">配置模型</a>:null}</p> : null}
    {page?.changes.length ? <GroupedList density="standard" aria-label="变更记录列表">
      {page.changes.map(change => <button key={`${change.source_database}:${change.change_id}`} type="button" className="control control--row memory-change-row memory-processing-row" onClick={() => void openDetail(change)}>
        <span className="memory-processing-row-content"><span className="memory-processing-title">{changeTitle(change)}</span>
          <span className="memory-processing-summary" data-state={change.memory_status}>{memoryStatusLabels[change.memory_status]}</span>
          <time className="memory-metadata" dateTime={change.recorded_at}>变更于 {memoryTimestamp(change.recorded_at)}</time></span>
      </button>)}
    </GroupedList> : !loading && !error ? <p className="memory-empty">暂无变更记录。</p> : null}
    {loading ? <p role="status">正在读取变更记录…</p> : null}
    {page?.next_cursor ? <button type="button" className="control control--secondary" disabled={loading} onClick={() => void load(page.next_cursor!)}>加载更多变更记录</button> : null}
    </>:null}
    {selected ? <section className="memory-change-detail" aria-label="变更记录详情">
      {modelView ? modelInput&&detail?<MemoryModelContent memberId={memberId} change={detail} input={modelInput}/>:detailError?<p role="alert">{detailError}</p>:<p className="memory-empty">该模型输入当前不可读取。</p> : !current ? <>
      <GroupedList density="standard" layout="fields">
        <ReadonlyField label="变更" value={changeTitle(selected)}/>
        <ReadonlyField label="变更时间" value={memoryTimestamp(selected.recorded_at)}/>
        {detail ? <ReadonlyField label="记忆状态" value={memoryStatusLabels[detail.memory_status]}/> : null}
      </GroupedList>
      {targets.length===1?<button type="button" className="control control--secondary" onClick={()=>{closeDetail();onNavigate(memoryChangeTargetPath(memberId,targets[0]));}}>查看条目</button>:null}
      {targets.length > 1 ? <GroupedList density="standard" aria-label="关联医疗报告">
        {targets.map((target, index) => <button key={`${target.resource_type}:${target.resource_id}`} type="button" className="control control--row" onClick={() => {closeDetail(); onNavigate(memoryChangeTargetPath(memberId, target));}}>查看关联医疗报告 {index + 1}</button>)}
      </GroupedList> : null}
      {detailError ? <><p role="alert" className="memory-error">{detailError}</p><button type="button" className="control control--secondary" onClick={() => void openDetail(selected)}>重试读取</button></> : !detail ? <p role="status">正在读取变更记录…</p> : null}
      {detail && !detail.content_available ? <p className="memory-empty">来源已删除或当前无权查看内容，保留变更类型和时间。</p> : null}
      {detail?.content_available && !targets.length ? <p className="memory-empty">该来源当前没有关联条目。</p> : null}
      {detail?.content_available ? <section aria-label="变更内容"><h3>变更内容</h3><div className="text-input-surface memory-change-markdown"><MarkdownContent content={detail.content_text || ''}/></div></section> : null}
      {detail?.processing ? <section aria-label="处理详情"><GroupedList density="standard" aria-label="处理详情入口">
        <button type="button" className="control control--row memory-processing-item" onClick={()=>openProcessing(detail.processing!)}><ControlRowContent title="处理步骤" description={processingStatusSummary(detail.processing)}/><ChevronRightIcon/></button>
        <button type="button" className="control control--row memory-processing-item" onClick={()=>openProcessing({...detail.processing!,object_type:'processing_result'})}><ControlRowContent title="处理结果" description={`已生成 ${objects(detail.processing.events).length} 个事件`}/><ChevronRightIcon/></button>
      </GroupedList></section> : null}
      </> : <>{current.row.object_type==='processing_group'?<MemoryProcessingDetail row={current.row} onOpen={openProcessing} processingSteps={detail?.processing_steps||[]} modelInputs={detail?.model_inputs||[]} onOpenModelInput={openModelInput} {...controls}/>:current.row.object_type==='processing_result'?<MemoryProcessingResults row={current.row} {...controls}/>:['processing_step','processing_progress_record','processing_unassigned_inputs'].includes(current.row.object_type)&&detail?.processing?<MemoryProgress group={detail.processing} change={detail} memberId={memberId} view={current.row} steps={detail.processing_steps||[]} inputs={detail.model_inputs||[]} onOpen={openProcessing} onOpenModelInput={openModelInput}/>:<MemoryObjectView row={current.row} citation={current.citation} {...controls}/>}{detailError?<p role="alert" className="memory-error">{detailError}</p>:null}</>}
      {busy?<p role="status">正在处理…</p>:null}
    </section> : null}
  </section></MemoryContentCache.Provider>;
}
