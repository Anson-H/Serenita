import {memoryCategories,type MemoryReference,type MemoryCategory} from "../../api/memory/memoryApi";
import {asReference,kindLabels,object,text} from './memoryPresentation';

export function MemoryGaps({label,values,onRead}:{label:string;values:unknown;onRead?:(reference:MemoryReference)=>void}){
 const rows=Array.isArray(values)?values:[];
 if(!rows.length)return null;
 return <section className="memory-notes"><h4>{label}</h4><ul>{rows.map((value,index)=>{
  const row=object(value),reference=asReference(value)||asReference(row.reference),references=[...(reference?[reference]:[]),...(Array.isArray(row.references)?row.references.map(asReference).filter((ref):ref is MemoryReference=>ref!==null):[])];
  const reasons:Record<string,string>={event_time_unknown:'部分事件的发生时间仍有未知。',graph_reference_unavailable:'部分引用的来源当前不可读取。',graph_edge_budget:'本次关联读取数量已达到上限。'};
  const detail=text(row.message)||text(row.reason)||text(row.detail);
  const content=typeof value==='string'?value:[memoryCategories[text(row.source_category) as MemoryCategory],reasons[detail]||detail,text(row.error_code)||text(row.code),text(row.source_ref)].filter(Boolean).join(' · ');
  return <li key={index}>{content||'此范围尚未完整读取。'}{onRead?references.map((ref,index)=><button key={index} className="control control--secondary" type="button" onClick={()=>onRead(ref)}>查看{kindLabels[ref.object_type]||'详情'}</button>):null}</li>;
 })}</ul></section>;
}
