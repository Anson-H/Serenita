import type {MemoryRecoveryRecord} from "../../api/memory/memoryApi";
import {memoryTimestamp, object, objects, text} from './memoryPresentation';
import {memoryStepTitle} from './memoryStepNames';

export function MemoryRecoveryRecords({records}:{records:unknown}) {
  const entries=objects(records) as MemoryRecoveryRecord[];
  if(!entries.length)return null;
  return <section className="memory-processing-detail" aria-label="恢复执行记录">
    <h4>恢复执行记录</h4>
    {entries.map(record=>{
      const checkpoint=object(record.checkpoint);
      const reused=checkpoint.reused===true;
      return <article key={record.recovery_id} className="memory-entry memory-entry--nested">
        <p>{reused?'复用已完成步骤':({auto:'自动恢复',explicit:'手动继续处理'} as Record<string,string>)[record.kind]||record.kind}</p>
        <p className="memory-metadata">{reused?'复用时间':'恢复时间'}：<time dateTime={record.recorded_at}>{record.recorded_at}</time></p>
        <p className="memory-metadata">{reused?'复用检查点':'恢复检查点'}：{text(checkpoint.step_id)?memoryStepTitle(text(checkpoint.step_id)):record.checkpoint==null?'未记录检查点':'已保存检查点'}{text(checkpoint.updated_at)?` · ${reused?'原检查点保存于':'保存于'} ${memoryTimestamp(checkpoint.updated_at)}`:''}</p>
        {record.checkpoint!=null?<details><summary>查看检查点记录</summary><pre className="memory-source">{JSON.stringify(record.checkpoint,null,2)}</pre></details>:null}
        <p className="memory-metadata">重试轮次：{record.retry_epoch}</p>
      </article>;
    })}
  </section>;
}
