import {useMemoryRefresh} from './useMemoryRefresh';
import {useCallback,useEffect,useRef,useState} from 'react';
import {readMemoryGraph,type MemoryGraphQuery,type MemoryGraphRead} from "../../api/memory/memoryGraphApi";
import type {MemoryReadQuery,MemoryReference} from "../../api/memory/memoryApi";
import {EventGraphCanvas} from './EventGraphCanvas';

const key=(ref:MemoryReference)=>JSON.stringify([ref.object_type,ref.object_id,ref.version??null,ref.item_id??null]);

function mergeGraph(current: MemoryGraphRead, next: MemoryGraphRead): MemoryGraphRead {
 return {...next, nodes:[...new Map([...current.nodes,...next.nodes].map(ref=>[key(ref),ref])).values()],
  objects:[...new Map([...current.objects,...next.objects].map(row=>[JSON.stringify(row),row])).values()],
  edges:[...new Map([...current.edges,...next.edges].map(edge=>[JSON.stringify(edge),edge])).values()],
  boundary_references:[...new Map([...current.boundary_references,...next.boundary_references].map(ref=>[key(ref),ref])).values()].filter(ref=>![...current.nodes,...next.nodes].some(node=>key(node)===key(ref))),
  gaps:[...current.gaps,...next.gaps],unread:[...current.unread.filter(item=>!(item&&typeof item==='object'&&'reason'in item&&item.reason==='graph_edge_budget')),...next.unread]};
}

export function MemoryGraph({memberId,accessRevision,episodeId,query,onRead,onMemberGraph,refresh,paused}:{memberId:string;accessRevision:number;episodeId?:string;query:MemoryReadQuery;
 refresh:number;paused:boolean;onRead:(reference:MemoryReference,related:MemoryReference[],scope:MemoryReadQuery)=>void;onMemberGraph:()=>void}){
 const [value,setValue]=useState<MemoryGraphRead|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[retry,setRetry]=useState(0);
 const loadedSteps=useRef<boolean[]>([]);
 const generation=useRef(0),active=useRef<AbortController|null>(null);
 const scope:MemoryGraphQuery={view:query.view,record_cutoff:query.record_cutoff,target_time:query.target_time,query:query.query,object_types:['event'],limit:24,edge_limit:100,
  ...(episodeId?{episode_id:episodeId}:{})};
 const scopeKey=JSON.stringify(scope);
 useEffect(()=>{const controller=new AbortController();active.current?.abort();active.current=controller;const version=++generation.current;loadedSteps.current=[];setValue(null);setError('');setBusy(true);
  void readMemoryGraph(memberId,JSON.parse(scopeKey) as MemoryGraphQuery,controller.signal).then(value=>{if(!controller.signal.aborted&&version===generation.current)setValue(value);})
   .catch(cause=>{if(!controller.signal.aborted&&version===generation.current)setError(cause instanceof Error?cause.message:'暂时无法查看这些关系。');})
   .finally(()=>{if(!controller.signal.aborted&&version===generation.current)setBusy(false);});return()=>controller.abort();
 },[memberId,accessRevision,scopeKey,refresh,retry]);
 const refreshGraph=useCallback(async(signal:AbortSignal)=>{
  const version=generation.current;
  const scope=JSON.parse(scopeKey) as MemoryGraphQuery;
  try {
   let next=await readMemoryGraph(memberId,scope,signal);
   for(const edges of loadedSteps.current){
    const continued=edges?next.edge_continuation:next.next_cursor?{...scope,record_cutoff:next.record_cutoff,cursor:next.next_cursor}:null;
    if(!continued||signal.aborted)break;
    next=mergeGraph(next,await readMemoryGraph(memberId,continued,signal));
   }
   if(!signal.aborted&&version===generation.current){setValue(next);setError('');}
  }catch(cause){if(!signal.aborted&&version===generation.current)setError(cause instanceof Error?cause.message:'暂时无法查看这些关系。');}
 },[memberId,scopeKey]);
 useMemoryRefresh(refreshGraph,!busy&&!paused);
 function showDetails(reference:MemoryReference){
  const matches=value?.edges.filter(edge=>[edge.from,edge.to,edge.relation].some(ref=>ref&&key(ref)===key(reference)))||[];
  const related=matches.flatMap(edge=>[edge.from,edge.to,edge.relation])
   .filter((ref):ref is MemoryReference=>Boolean(ref)&&key(ref!)!==key(reference));
  if(value)onRead(reference,related,{...query,record_cutoff:value.record_cutoff});
 }
 async function more(edges=false){if(!value||busy)return;const continued=edges?value.edge_continuation:value.next_cursor?{...scope,record_cutoff:value.record_cutoff,cursor:value.next_cursor}:null;if(!continued)return;
  const controller=new AbortController();active.current?.abort();active.current=controller;const version=generation.current;setBusy(true);setError('');
  try{const next=await readMemoryGraph(memberId,continued,controller.signal);
   if(version===generation.current&&!controller.signal.aborted){loadedSteps.current.push(edges);setValue(current=>current?mergeGraph(current,next):next);}
  }catch(cause){if(!controller.signal.aborted&&version===generation.current){setValue(null);setError(cause instanceof Error?cause.message:'暂时无法查看这些关系。');}}
  finally{if(!controller.signal.aborted&&version===generation.current)setBusy(false);}
 }
 return <section className="memory-graph" aria-label={episodeId?'事项记忆图谱':'成员记忆图谱'}>
  {value?<EventGraphCanvas key={scopeKey+refresh+retry} value={value} onRead={showDetails}/>:<div className="event-graph-frame"/>}
  <div className="memory-graph-status">
   {episodeId?<button type="button" className="control control--secondary" onClick={onMemberGraph}>全部事件</button>:null}
   {busy?<p role="status">正在加载…</p>:null}
   {error?<><p role="alert" className="memory-error">{error}</p><button type="button" className="control control--secondary" onClick={()=>setRetry(value=>value+1)}>重试</button></>:null}
   {value?<>
    {value.edge_continuation?<button className="control control--secondary" type="button" disabled={busy} onClick={()=>void more(true)}>加载更多关系</button>:null}
    {value.next_cursor?<button className="control control--secondary" type="button" disabled={busy||Boolean(value.edge_continuation)} onClick={()=>void more()}>加载更多事件</button>:null}
   </>:null}
  </div>
 </section>;
}
