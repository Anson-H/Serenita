import {useEffect,useState} from 'react';
import {readMemory,type MemoryObject,type MemoryReference,type MemoryChangeReference} from "../../api/memory/memoryApi";
import {GroupedList,ReadonlyField} from '../../components/GroupedList';
import {formatDateOnly,formatLocalDate} from '../../utils/localTime';
import {object,objects,text} from './memoryPresentation';

import type {MemoryCitation} from './memoryChangePresentation';
import {MarkdownContent} from '../../components/MarkdownContent';
import {MemoryEventEntities} from './MemoryEventEntities';

type SourceExcerpt={id:string;content:string;time:string};

function timePoint(value:unknown){
  const point=object(value),valueText=text(point.value);
  if(!valueText)return '';
  if(/^\d{4}$/.test(valueText))return `${valueText}年`;
  if(/^\d{4}-\d{2}(?:-\d{2})?$/.test(valueText))return formatDateOnly(valueText);
  const date=new Date(valueText);
  if(Number.isNaN(date.getTime()))return '';
  if(point.precision==='hour')return `${formatLocalDate(date)} ${date.getHours()}时`;
  return formatLocalDate(date,true);
}

function occurrence(value:unknown){
  const time=object(value),start=timePoint(time.start),end=timePoint(time.end);
  if(start&&end)return start===end?start:`${start} 至 ${end}`;
  return start?start:end?`截至 ${end}`:'';
}

function EventSources({row,memberId}:{row:MemoryObject;memberId:string}){
  const [state,setState]=useState<{sources:SourceExcerpt[];loading:boolean;missing:boolean;error:boolean}>({sources:[],loading:true,missing:false,error:false});
  const evidence=JSON.stringify(objects(row.evidence));
  useEffect(()=>{
    const controller=new AbortController();
    async function load(){
      try{
        const excerpts:SourceExcerpt[]=[];
        const direct=JSON.parse(evidence) as MemoryChangeReference[];
        let missing=!direct.length;
        for(let offset=0;offset<direct.length;offset+=50){
          const result=await readMemory(memberId,{business_changes:direct.slice(offset,offset+50)},controller.signal);
          missing ||= (result.business_changes||[]).length<direct.slice(offset,offset+50).length;
          for(const change of result.business_changes||[]){
            excerpts.push({id:JSON.stringify([change.source_database,change.change_id,change.field_path]),
              content:change.content_text,time:change.recorded_at});
          }
        }
        if(!controller.signal.aborted)setState({sources:excerpts,loading:false,missing,error:false});
      }catch{
        if(!controller.signal.aborted)setState({sources:[],loading:false,missing:false,error:true});
      }
    }
    void load();
    return ()=>controller.abort();
  },[evidence,memberId]);
  return <section className="memory-evidence memory-event-changes" aria-label="变更内容">
    <h4>变更内容</h4>
    {state.loading?<p role="status">正在读取变更内容…</p>:null}
    {state.error?<p role="alert">变更内容读取失败。</p>:null}
    {state.sources.map(source=><div key={source.id} className="memory-source-link">
      {source.time?<time className="memory-metadata" dateTime={source.time}>变更时间：{formatLocalDate(source.time,true)}</time>:null}
      <div className="text-input-surface memory-change-markdown"><MarkdownContent content={source.content}/></div>
    </div>)}
    {state.missing?<p className="memory-metadata">部分变更内容暂不可用。</p>:null}
  </section>;
}

export function MemoryEventView({row,memberId,recordCutoff,onRead,nested}:{row:MemoryObject;memberId?:string;recordCutoff?:number;onRead:(reference:MemoryReference,citation?:MemoryCitation)=>void;nested:boolean}){
  const occurred=occurrence(row.occurrence_time),saved=new Date(text(row.submitted_at));
  const savedTime=Number.isNaN(saved.getTime())?'':formatLocalDate(saved,true);
  return <article className={`memory-entry memory-event-detail${nested?' memory-entry--nested':''}`}>
    <GroupedList density="standard" layout="fields" className="memory-facts">
      <ReadonlyField className="long-text-field-row" label="标题" value={text(row.title)||'未记录'}/>
      <ReadonlyField className="long-text-field-row" label="摘要" value={text(row.summary)||'未记录'}/>
      <ReadonlyField className="long-text-field-row" label="内容" value={text(row.content)||'未记录'}/>
      <ReadonlyField label="分类" value={text(row.category)}/>
      <ReadonlyField label="重要程度" value={({HIGH:'高',MEDIUM:'中',LOW:'低'} as Record<string,string>)[text(row.priority)]}/>
      <ReadonlyField label="发生时间" value={occurred||'未记录'}/>
      <ReadonlyField label="保存时间" value={savedTime||'未记录'}/>
    </GroupedList>
    {memberId?<MemoryEventEntities key={JSON.stringify([memberId,recordCutoff,row.event_id])} row={row} memberId={memberId} recordCutoff={recordCutoff} onRead={onRead}/>:null}
    {memberId?<EventSources key={JSON.stringify([memberId,recordCutoff,row.event_id,row.evidence])} row={row} memberId={memberId}/>:null}
  </article>;
}
