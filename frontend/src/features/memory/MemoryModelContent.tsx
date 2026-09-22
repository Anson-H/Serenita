import {useEffect,useRef,useState} from 'react';
import {readMemoryModel,readMemoryModelFragments,type MemoryChangeDetail,type MemoryModelInput} from "../../api/memory/memoryApi";
import {MemoryModelInputDetail} from './MemoryModelInputs';
import {appendMemoryFragments} from './memoryModelStream';
import {ApiRequestError} from "../../api/transport/request";

export function MemoryModelContent({memberId,change,input}:{memberId:string;change:MemoryChangeDetail;input:MemoryModelInput}){
  const key=JSON.stringify([memberId,change.source_database,change.change_id,change.access_revision,input.entry_id]);
  const latest=useRef({change,input});
  latest.current={change,input};
  const run=useRef<()=>void>(()=>{});
  const [view,setView]=useState<{key:string;input:MemoryModelInput|null;error:string}|null>(null);
  useEffect(()=>{
    let active=true,pending=false,dirty=false,controller:AbortController|null=null;
    let saved:MemoryModelInput|null=null;
    const publish=(value:MemoryModelInput|null,error='')=>{if(active)setView({key,input:value,error});};
    const accessible=(available:boolean,revision:string)=>available&&latest.current.change.content_available&&latest.current.input.status!=='unavailable'&&revision===latest.current.change.access_revision;
    async function pump(){
      if(!active||document.visibilityState!=='visible')return;
      if(pending){dirty=true;return;}
      const {change:current,input:target}=latest.current;
      if(!current.content_available||target.status==='unavailable'){saved=null;publish(null);return;}
      pending=true;dirty=false;controller=new AbortController();
      const signal=controller.signal;
      const live=()=>active&&!signal.aborted;
      const snapshot=async()=>{
        const result=await readMemoryModel(memberId,current,target.entry_id,signal);
        if(!live())return false;
        if(!accessible(result.content_available,result.access_revision)){saved=null;publish(null);return false;}
        saved=result.model_inputs.find(value=>value.entry_id===target.entry_id)??null;
        publish(saved);
        return !!saved;
      };
      try{
        if(!saved){await snapshot();return;}
        // A status response can be older than a completed pagination request.
        if((target.output_entry_sequence??0)<(saved.output_entry_sequence??0))return;
        if(target.output_revision===saved.output_revision&&target.status===saved.status)return;
        if(target.status!=='running'){await snapshot();return;}
        let more=true;
        while(more&&live()&&saved){
          const result=await readMemoryModelFragments(memberId,current,target.entry_id,saved.output_entry_sequence??0,signal);
          if(!live())return;
          if(!accessible(result.content_available,result.access_revision)){saved=null;publish(null);return;}
          saved=appendMemoryFragments(saved,result.fragments);
          publish(saved);
          more=result.has_more;
          if(!more&&result.status!=='running'){await snapshot();return;}
          if(more&&!result.fragments.length)throw new Error('模型片段分页未前进，请重新读取。');
        }
      }catch(cause){
        if(cause instanceof ApiRequestError&&[401,403,404].includes(cause.status))saved=null;
        if(live())publish(saved,cause instanceof Error?cause.message:'模型内容读取失败。');
      }finally{
        pending=false;controller=null;
        if(dirty&&active&&document.visibilityState==='visible'){dirty=false;void pump();}
      }
    }
    run.current=()=>{void pump();};
    const visibility=()=>{if(document.visibilityState!=='visible')controller?.abort();else void pump();};
    document.addEventListener('visibilitychange',visibility);
    void pump();
    return()=>{active=false;controller?.abort();run.current=()=>{};document.removeEventListener('visibilitychange',visibility);};
  },[key,memberId]);
  useEffect(()=>{run.current();},[input,change.content_available]);
  if(!change.content_available||input.status==='unavailable')return <p className="memory-metadata">当前模型内容不可读取。</p>;
  if(view?.key!==key)return <p role="status">正在读取模型内容…</p>;
  return <>{view.error?<p role="alert" className="memory-error">{view.error}</p>:null}
    {view.input?<MemoryModelInputDetail input={view.input}/>:!view.error?<p className="memory-metadata">当前模型内容不可读取。</p>:null}</>;
}
