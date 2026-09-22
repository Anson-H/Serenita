import {useEffect,useState} from 'react';
import {readMemory,type MemoryObject,type MemoryReference} from "../../api/memory/memoryApi";
import {GroupedList} from '../../components/GroupedList';
import {ChevronRightIcon} from '../../components/icons';
import {changeFieldLabel} from './memoryChangePresentation';
import {objects,strings,text} from './memoryPresentation';

export function MemoryEventEntities({row,memberId,recordCutoff,onRead}:{row:MemoryObject;memberId:string;recordCutoff?:number;onRead:(reference:MemoryReference)=>void}){
  const associations=objects(row.event_associations);
  const ids=JSON.stringify(strings(row.entity_ids));
  const [state,setState]=useState<{items:MemoryObject[];loading:boolean;error:boolean;missing:boolean}>({items:[],loading:true,error:false,missing:false});
  useEffect(()=>{
    const controller=new AbortController();
    setState({items:[],loading:true,error:false,missing:false});
    async function load(){
      try{
        const identities=[...new Set(JSON.parse(ids) as string[])],items:MemoryObject[]=[];
        for(let offset=0;offset<identities.length;offset+=100){
          const result=await readMemory(memberId,{record_cutoff:recordCutoff,limit:100,references:identities.slice(offset,offset+100).map(id=>({object_type:'entity',object_id:id}))},controller.signal);
          items.push(...result.objects.filter(item=>item.object_type==='entity'));
        }
        if(!controller.signal.aborted)setState({items,loading:false,error:false,missing:items.length<identities.length});
      }catch{
        if(!controller.signal.aborted)setState({items:[],loading:false,error:true,missing:false});
      }
    }
    void load();return ()=>controller.abort();
  },[ids,memberId,recordCutoff]);
  return <section className="memory-evidence" aria-label="事件实体"><h4>实体</h4>
    {state.loading?<p role="status">正在读取实体…</p>:state.error?<p role="alert">实体读取失败。</p>:<>
      {state.items.length?<GroupedList density="standard">{state.items.map(item=><button type="button" className="control control--row memory-navigation-row" key={text(item.entity_id)} onClick={()=>onRead({object_type:'entity',object_id:text(item.entity_id)})}>
        <span>{item.entity_type==='administrative_field'?changeFieldLabel(text(item.canonical_name)):text(item.canonical_name)}
        {[...new Set(associations.filter(value=>value.entity_id===item.entity_id).map(value=>text(value.description)).filter(Boolean))].map(description=><span className="memory-entity-description memory-metadata" key={description}>{description}</span>)}</span>
        <ChevronRightIcon/>
      </button>)}</GroupedList>:null}
      {!state.items.length&&!state.missing?<p className="memory-metadata">暂无关联实体。</p>:null}
      {state.missing?<p className="memory-metadata">部分实体暂不可用。</p>:null}
    </>}
  </section>;
}
