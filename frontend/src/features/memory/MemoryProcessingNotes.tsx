import type {MemoryObject} from "../../api/memory/memoryApi";
import {memoryTimestamp,objects,processingError,statusLabels,strings,text} from './memoryPresentation';

export function MemoryProcessingNotes({group}:{group:MemoryObject}) {
  const attempts=objects(group.records).filter(row=>row.object_type==='processing_attempt');
  const replaced=new Set(attempts.map(row=>text(row.previous_attempt_id)).filter(Boolean));
  const notes=attempts.flatMap(row=>{
    const status=row,error=text(status.error_message)||processingError(status),code=text(status.error_code);
    const gaps=strings(status.gaps),reason=text(status.outcome_reason);
    if(!error&&!code&&!gaps.length&&!(reason&&['failed','cancelled'].includes(text(row.processing_status))))return [];
    return [{row,error,code,gaps,reason}];
  });
  return notes.length?<section aria-label="处理说明">{notes.map(({row,error,code,gaps,reason})=><div key={text(row.attempt_id)}>
    <p className="memory-metadata">{replaced.has(text(row.attempt_id))?'此前处理':'当前处理'} · {statusLabels[text(row.processing_status)]||'状态不可读取'}{text(row.updated_at)||text(row.submitted_at)?` · ${memoryTimestamp(row.updated_at||row.submitted_at)}`:''}</p>
    {error?<p className="memory-error">{error}</p>:null}
    {code?<p className="memory-metadata">原因代码：{code}</p>:null}
    {reason?<p className="memory-prose">{reason}</p>:null}
    {gaps.length?<ul>{gaps.map((gap,index)=><li key={index}>{gap}</li>)}</ul>:null}
  </div>)}</section>:null;
}
