import {createContext,useContext,useEffect,useState} from 'react';
import {readMemoryStep,type MemoryChangeDetail,type MemoryProcessingStep,type MemoryStepContent as StepContent} from "../../api/memory/memoryApi";
import {MemoryStepIO} from './MemoryStepIO';
import {MemoryModelContent} from './MemoryModelContent';

export class MemoryContentStore {
  private entries=new Map<string,{controller:AbortController;promise:Promise<StepContent>;settled:boolean}>();
  clear(){for(const value of this.entries.values())value.controller.abort();this.entries.clear();}
  cancel(key:string){const saved=this.entries.get(key);if(saved&&!saved.settled){saved.controller.abort();this.entries.delete(key);}}
  read(key:string,fetch:(signal:AbortSignal)=>Promise<StepContent>){
    const saved=this.entries.get(key);
    if(saved)return saved.promise;
    while(this.entries.size>=32){const oldest=this.entries.keys().next().value!;this.entries.get(oldest)!.controller.abort();this.entries.delete(oldest);}
    const controller=new AbortController();
    const promise=fetch(controller.signal).then(result=>{const current=this.entries.get(key);if(current?.controller===controller)current.settled=true;return result;})
      .catch(error=>{if(this.entries.get(key)?.controller===controller)this.entries.delete(key);throw error;});
    this.entries.set(key,{controller,promise,settled:false});
    return promise;
  }
}
export const MemoryContentCache=createContext<MemoryContentStore|null>(null);

export function MemoryStepContent({memberId,change,step,parent,title,steps,attemptIds,requestStamp,leaf}:{
  memberId:string;change:MemoryChangeDetail;step:string;parent:string|null;title:string;
  steps:MemoryProcessingStep[];attemptIds:string[];requestStamp:string;leaf:boolean;
}){
  const cache=useContext(MemoryContentCache)!;
  const stamp=steps.map(row=>`${row.progress_id}:${row.status}:${row.submitted_at}`).join(',');
  const key=[memberId,change.source_database,change.change_id,change.access_revision,step,parent,attemptIds.join(','),stamp,requestStamp].join('/');
  const [value,setValue]=useState<{key:string;data:StepContent}|null>(null);
  const [error,setError]=useState('');
  useEffect(()=>{
    let active=true;
    let generation=0;
    const read=()=>{
      if(document.visibilityState!=='visible')return;
      const own=++generation;
      setError('');
      void cache.read(key,signal=>readMemoryStep(memberId,change,step,parent,signal)).then(data=>{
        if(active&&own===generation)setValue({key,data});
      }).catch(cause=>{if(active&&own===generation)setError(cause instanceof Error?cause.message:'处理内容读取失败。');});
    };
    const visibility=()=>{if(document.visibilityState!=='visible'){generation++;cache.cancel(key);}else read();};
    read();
    document.addEventListener('visibilitychange',visibility);
    return()=>{active=false;generation++;cache.cancel(key);document.removeEventListener('visibilitychange',visibility);};
  },[key,cache,memberId,change.source_database,change.change_id,step,parent]);
  if(error)return <p role="alert" className="memory-error">{error}</p>;
  if(value?.key!==key)return <p role="status">正在读取处理内容…</p>;
  if(!change.content_available||!value.data.content_available||value.data.access_revision!==change.access_revision)return <p className="memory-metadata">当前处理内容不可读取。</p>;
  const identities=new Set(steps.map(row=>row.progress_id));
  const attempts=new Set(attemptIds);
  const records=value.data.processing_steps.filter(row=>identities.has(row.progress_id));
  const inputs=change.model_inputs.filter(row=>attempts.has(row.attempt_id)&&row.processing_step===step);
  return <><MemoryStepIO steps={records} title={title} leaf={leaf&&!inputs.length}/>
    {inputs.map(input=><MemoryModelContent key={input.entry_id} memberId={memberId} change={change} input={input}/>)}</>;
}
