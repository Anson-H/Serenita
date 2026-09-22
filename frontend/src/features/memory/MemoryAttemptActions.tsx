import type {MemoryObject} from "../../api/memory/memoryApi";
import {memoryTimestamp, object, text} from './memoryPresentation';
import {memoryStepTitle} from './memoryStepNames';
import {MemoryRecoveryRecords} from './MemoryRecoveryRecords';

export type MemoryAttemptControls = {
  row: MemoryObject; busy?: boolean;
  onResume?: (attempt: string) => void;
  onRetry?: (attempt: string) => void;
  onCancel?: (attempt: string) => void;
};

export function MemoryAttemptActions({row,busy,onResume,onRetry,onCancel,showRecoveryRecords=true}:MemoryAttemptControls & {showRecoveryRecords?:boolean}) {
  const actions=object(row.available_actions);
  const checkpoint=object(row.checkpoint);
  const recovery=({unavailable:'没有可用检查点',available:'检查点可用',conflict:'处理依据已变化',
    published:'已发布',invalid:'检查点不可用'} as Record<string,string>)[text(row.recovery_status)];
  const stopped=['failed','cancelled'].includes(text(row.processing_status));
  return <>
    {recovery&&(stopped||text(checkpoint.step_id))?<p className="memory-metadata">恢复状态：{recovery}</p>:null}
    {text(checkpoint.step_id)?<p className="memory-metadata">当前检查点：{memoryStepTitle(text(checkpoint.step_id))}{text(checkpoint.updated_at)?` · 保存于 ${memoryTimestamp(checkpoint.updated_at)}`:''}</p>:null}
    {stopped&&text(row.recovery_reason)?<p className="memory-metadata">{text(row.recovery_reason)}</p>:null}
    {actions.resume===true||actions.retry===true||actions.cancel===true?<div className="memory-reference-list">
      {actions.resume===true&&onResume?<button className="control control--secondary" disabled={busy} type="button" onClick={()=>onResume(text(row.attempt_id))}>继续处理</button>:null}
      {actions.retry===true&&onRetry?<button className="control control--secondary" disabled={busy} type="button" onClick={()=>onRetry(text(row.attempt_id))}>{row.task_kind==='vector_index'?'重试检索准备':'从头重新处理'}</button>:null}
      {actions.cancel===true&&onCancel?<button className="control control--secondary" disabled={busy} type="button" onClick={()=>onCancel(text(row.attempt_id))}>取消这次处理</button>:null}
    </div>:null}
    {showRecoveryRecords?<MemoryRecoveryRecords records={row.recovery_records}/>:null}
  </>;
}
