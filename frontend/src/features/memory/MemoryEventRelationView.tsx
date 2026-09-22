import {useEffect,useState} from 'react';
import {readMemory,type MemoryObject,type MemoryReference} from "../../api/memory/memoryApi";
import {SettingsListForwardIcon} from '../settings/SettingsPrimitives';
import {MemoryGaps} from './MemoryGaps';
import {eventRelationLabel,memoryTimestamp,text} from './memoryPresentation';

function EventPair({row,memberId,recordCutoff,onRead}:{row:MemoryObject;memberId?:string;recordCutoff?:number;onRead:(reference:MemoryReference)=>void}){
  const from=text(row.from_event_id),to=text(row.to_event_id);
  const [state,setState]=useState<{rows:MemoryObject[];loading:boolean;error:boolean}>({rows:[],loading:true,error:false});
  useEffect(()=>{
    const controller=new AbortController();
    const identities=[...new Set([from,to].filter(Boolean))];
    if(!memberId||!identities.length){setState({rows:[],loading:false,error:false});return;}
    setState({rows:[],loading:true,error:false});
    void readMemory(memberId,{record_cutoff:recordCutoff,limit:100,references:identities.map(object_id=>({object_type:'event',object_id}))},controller.signal)
      .then(result=>{if(!controller.signal.aborted)setState({rows:result.objects.filter(item=>item.object_type==='event'),loading:false,error:false});})
      .catch(()=>{if(!controller.signal.aborted)setState({rows:[],loading:false,error:true});});
    return ()=>controller.abort();
  },[from,to,memberId,recordCutoff]);
  const directional=row.relation_type!=='ConflictsWith';
  return <section className="memory-relation-events" aria-label="关联的两个事件">
    {[from,to].map((id,index)=>{
      const event=state.rows.find(item=>item.event_id===id);
      const label=directional?(index?'指向事件':'起始事件'):`事件${index?'二':'一'}`;
      return <div key={index}>
        {index?<div className="memory-relation-connector" aria-label={directional?'关系从上方事件指向下方事件':'两个事件之间的双向关系'}><span aria-hidden="true">{directional?'↓':'↕'}</span></div>:null}
        <button type="button" className="control memory-relation-event" disabled={!event} aria-label={`查看${label}${event?`：${text(event.content)}`:''}`} onClick={()=>onRead({object_type:'event',object_id:id})}>
          <span><span className="memory-metadata">{label}</span><span className="memory-relation-event-text">{event?text(event.content):state.loading?'正在读取事件…':state.error?'事件读取失败':'事件当前不可读取'}</span></span>
          <SettingsListForwardIcon/>
        </button>
      </div>;
    })}
  </section>;
}

export function MemoryEventRelationView({row,memberId,recordCutoff,onRead,nested}:{row:MemoryObject;memberId?:string;recordCutoff?:number;onRead:(reference:MemoryReference)=>void;nested:boolean}){
  return <article className={`memory-entry memory-relation-detail${nested?' memory-entry--nested':''}`}>
    <div className="memory-relation-heading"><h3>{eventRelationLabel(row.relation_type)}</h3></div>
    <p className="memory-prose">{text(row.reason)}</p>
    <EventPair key={JSON.stringify([memberId,recordCutoff,row.relation_id])} row={row} memberId={memberId} recordCutoff={recordCutoff} onRead={onRead}/>
    <MemoryGaps label="未读内容" values={row.unread} onRead={onRead}/><MemoryGaps label="资料缺口" values={row.gaps} onRead={onRead}/>
    {text(row.submitted_at)?<p className="memory-metadata">保存于 {memoryTimestamp(row.submitted_at)}</p>:null}
  </article>;
}
