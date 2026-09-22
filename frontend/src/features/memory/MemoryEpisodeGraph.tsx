import {useCallback, useEffect, useRef, useState} from 'react';
import {readMemory, type MemoryObject, type MemoryReadQuery, type MemoryReference} from "../../api/memory/memoryApi";
import {MemoryGraph} from './MemoryGraph';
import {asReference, memoryTimestamp, object, text} from './memoryPresentation';
import {useMemoryRefresh} from './useMemoryRefresh';

type Revision = MemoryObject & {version:number; record_sequence:number; submitted_at:string};
function isRevision(row:MemoryObject):row is Revision {
  return row.object_type==='episode_revision' && Number.isInteger(row.version) && Number(row.version)>0
    && Number.isInteger(row.record_sequence) && Number(row.record_sequence)>0 && Boolean(text(row.submitted_at));
}

export function MemoryEpisodeGraph({memberId, accessRevision, episodeId, initialVersion, refresh, paused, onRead, onScopeChange, onMemberGraph}:{
  memberId:string; accessRevision:number; episodeId:string; initialVersion?:number; refresh:number; paused:boolean;
  onRead:(reference:MemoryReference, related:MemoryReference[], scope:MemoryReadQuery)=>void;
  onScopeChange:()=>void; onMemberGraph:()=>void;
}) {
  const [revisions,setRevisions]=useState<Revision[]>([]);
  const [latestVersion,setLatestVersion]=useState<number>();
  const [version,setVersion]=useState(initialVersion);
  const [loading,setLoading]=useState(true),[error,setError]=useState(''),[retry,setRetry]=useState(0);
  const cache=useRef(new Map<number,Revision>());
  const timeline=useRef<HTMLDivElement>(null);
  const readVersions=useCallback(async(signal:AbortSignal)=>{
    try {
      const result=await readMemory(memberId,{references:[{object_type:'episode',object_id:episodeId}]},signal);
      const episode=result.objects.find(row=>row.object_type==='episode' && row.episode_id===episodeId);
      if(!episode)throw new Error('该事项当前不可读取。');
      const refs=(Array.isArray(episode.revisions)?episode.revisions:[]).map(asReference)
        .filter((ref):ref is MemoryReference=>Boolean(ref && ref.object_type==='episode_revision' && ref.object_id===episodeId));
      const current=object(episode.current_revision) as MemoryObject;
      const available=new Map(cache.current);
      if(isRevision(current))available.set(current.version,current);
      const missing=refs.filter(ref=>!available.has(Number(ref.version)));
      for(let start=0;start<missing.length;start+=100) {
        const page=await readMemory(memberId,{references:missing.slice(start,start+100),record_cutoff:result.record_cutoff,limit:100},signal);
        for(const row of page.objects)if(isRevision(row) && row.episode_id===episodeId)available.set(row.version,row);
      }
      if(signal.aborted)return;
      const values=refs.map(ref=>available.get(Number(ref.version))).filter((row):row is Revision=>Boolean(row)).sort((a,b)=>a.version-b.version);
      if(values.length!==refs.length)throw new Error('部分事项版本暂时不可读取，请重试。');
      cache.current=new Map(values.map(row=>[row.version,row]));
      setRevisions(values);setLatestVersion(isRevision(current)?current.version:undefined);setError('');
    } catch(cause) {
      if(!signal.aborted){setRevisions([]);cache.current.clear();setError(cause instanceof Error?cause.message:'事项版本读取失败，请重试。');}
    } finally {if(!signal.aborted)setLoading(false);}
  },[memberId,episodeId]);
  useEffect(()=>{const controller=new AbortController();setLoading(true);void readVersions(controller.signal);return()=>controller.abort();},[readVersions,refresh,retry]);
  useMemoryRefresh(readVersions,!loading&&!paused&&!error);
  const selected=revisions.find(row=>row.version===(version??latestVersion));
  const cutoff=selected?.record_sequence;
  useEffect(onScopeChange,[cutoff,onScopeChange]);
  useEffect(()=>{timeline.current?.querySelector('button[aria-pressed="true"]')?.scrollIntoView({block:'nearest',inline:'nearest'});},[selected?.version,loading]);

  return <div className="memory-graph-pane memory-episode-graph">
    {selected&&!loading&&!error?<MemoryGraph key={selected.record_sequence} memberId={memberId} accessRevision={accessRevision} episodeId={episodeId}
      query={{view:'historical_saved',record_cutoff:selected.record_sequence}} refresh={refresh} paused={paused}
      onRead={onRead} onMemberGraph={onMemberGraph}/>:<div className="event-graph-frame"/>}
    <section className="memory-version-timeline" aria-label="事项版本时间条">
      {loading?<p role="status">正在加载事项版本…</p>:error?<><p role="alert">{error}</p><button type="button" className="control control--secondary" onClick={()=>setRetry(value=>value+1)}>重试</button></>:
        revisions.length?<>
          <p>{selected?`第 ${selected.version} 版 · ${memoryTimestamp(selected.submitted_at)}`:'所选版本当前不可读取。'}</p>
          <div className="memory-version-stops" ref={timeline}>{revisions.map(row=><button key={row.version} type="button" className="control memory-version-stop"
            aria-pressed={row.version===selected?.version} onClick={()=>{onScopeChange();setVersion(row.version===latestVersion?undefined:row.version);}}>
            <strong>第 {row.version} 版{row.version===latestVersion?'（最新）':''}</strong><span>{memoryTimestamp(row.submitted_at)}</span>
          </button>)}</div>
        </>:<p role="status">事项版本尚未生成。</p>}
    </section>
  </div>;
}
