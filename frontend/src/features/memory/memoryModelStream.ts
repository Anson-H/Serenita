import type {MemoryModelFragment,MemoryModelInput,MemoryToolDelta} from "../../api/memory/memoryApi";

// The record cursor, rather than text equality, identifies duplicates. Repeated
// words are valid output and must never be removed during reconnection.
export function appendMemoryFragments(input:MemoryModelInput, fragments:MemoryModelFragment[]):MemoryModelInput {
  let cursor=input.output_entry_sequence??0;
  const output={...input.output};
  const tools=new Map<number,MemoryToolDelta>(((output.tool_call_deltas??[]) as MemoryToolDelta[]).map(value=>[value.index,{...value}]));
  const seen=new Set<string>();
  for(const fragment of [...fragments].sort((a,b)=>a.entry_sequence-b.entry_sequence)){
    if(fragment.entry_sequence<=cursor||seen.has(fragment.entry_id))continue;
    const expected=Number(output.stream_sequence??0)+1;
    if(fragment.stream_sequence!==expected)throw new Error('模型片段序号不连续，请重新读取。');
    seen.add(fragment.entry_id);
    const delta=fragment.delta;
    output.content=String(output.content??'')+(delta.content_delta??'');
    output.reasoning=String(output.reasoning??'')+(delta.reasoning_delta??'');
    output.raw_content=String(output.raw_content??'')+(delta.raw_content_delta??'');
    output.usage={...(output.usage as Record<string,unknown>??{}),...delta.usage};
    if(delta.stop_reason!=null)output.stop_reason=delta.stop_reason;
    output.first_chunk_at??=fragment.received_at;
    if(delta.content_delta)output.first_content_at??=fragment.received_at;
    for(const part of delta.tool_call_deltas??[]){
      const value=tools.get(part.index)??{index:part.index,id:'',name_delta:'',arguments_delta:''};
      tools.set(part.index,{index:part.index,id:value.id+(part.id??''),name_delta:value.name_delta+(part.name_delta??''),arguments_delta:value.arguments_delta+(part.arguments_delta??'')});
    }
    output.stream_sequence=fragment.stream_sequence;
    output.received_at=fragment.received_at;
    output.delta=delta;
    output.stream_status='streaming';
    cursor=fragment.entry_sequence;
  }
  const values=[...tools.values()].sort((a,b)=>a.index-b.index);
  output.tool_call_deltas=values;
  output.tool_calls=values.map(value=>({id:value.id,type:'function',function:{name:value.name_delta,arguments:value.arguments_delta}}));
  const last=fragments.filter(fragment=>fragment.entry_sequence===cursor).at(-1);
  return {...input,output,output_entry_sequence:cursor,output_revision:last?.entry_id??input.output_revision};
}
