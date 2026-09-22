import type {ComponentProps} from 'react';
import type {MemoryChangeDetail,MemoryObject} from "../../api/memory/memoryApi";
import {GroupedList} from '../../components/GroupedList';
import {ChevronRightIcon} from '../../components/icons';
import {ControlRowContent} from '../../components/ControlRowContent';
import {MemoryObjectView} from './MemoryObjectView';
import {MemoryProgress,currentProcessingAttempts} from './MemoryProgress';
import {MemoryProcessingNotes} from './MemoryProcessingNotes';
import {MemoryAttemptActions} from './MemoryAttemptActions';
import {MemoryRecoveryRecords} from './MemoryRecoveryRecords';
import {memoryResourceLabels} from './memoryChangePresentation';
import {object, objects, objectTitle, statusLabels, text} from './memoryPresentation';

type Controls=ComponentProps<typeof MemoryObjectView>;
export function processingTitle(row:MemoryObject) {
  const change = object(row.change);
  if (!text(change.change_id)) return objectTitle(row);
  const operation = ({create:'创建',update:'更新',delete:'删除'} as Record<string,string>)[text(change.operation_kind)] || text(change.operation_kind);
  const resource = memoryResourceLabels[text(change.resource_type)] || text(change.resource_type);
  return [operation, resource, text(change.title)].filter(Boolean).join(' · ');
}

export function processingStatusSummary(row:MemoryObject) {
  const state = text(row.processing_status);
  const events = Number(row.event_count);
  return `${statusLabels[state] || '尚无处理记录'} · ${events ? `已生成 ${events} 个事件` : '尚未生成事件'}`;
}

export function MemoryProcessingDetail({row,onOpen,processingSteps,modelInputs,onOpenModelInput,...controls}:Controls&{
  onOpen:(row:MemoryObject)=>void;processingSteps:MemoryChangeDetail['processing_steps'];modelInputs:MemoryChangeDetail['model_inputs'];
  onOpenModelInput:(input:MemoryChangeDetail['model_inputs'][number])=>void;
}) {
  return <section className="memory-processing-detail" aria-label="处理步骤总览">
    <p className="memory-metadata">{processingStatusSummary(row)}</p>
    <MemoryProcessingNotes group={row}/>
    <MemoryProgress group={row} steps={processingSteps} inputs={modelInputs} onOpen={onOpen} onOpenModelInput={onOpenModelInput}/>
    {currentProcessingAttempts(row).map(item=><MemoryProcessingActions key={text(item.attempt_id)} row={item} {...controls} showRecoveryRecords={false}/>)}
    <MemoryRecoveryRecords records={objects(row.records).filter(item=>item.object_type==='processing_attempt')
      .flatMap(item=>objects(item.recovery_records)).sort((a,b)=>text(a.recorded_at).localeCompare(text(b.recorded_at))||text(a.recovery_id).localeCompare(text(b.recovery_id)))}/>
  </section>;
}

export const MemoryProcessingActions = MemoryAttemptActions;

export function MemoryProcessingResults({row,onRead}:Controls) {
  const events=objects(row.events);
  return <section className="memory-processing-results" aria-label="处理结果详情">
    <MemoryProcessingNotes group={row}/>
    {events.length?<GroupedList density="standard" aria-label="处理生成的事件">{events.map(event=><button key={text(event.event_id)} type="button" className="control control--row memory-processing-item" onClick={()=>onRead({object_type:'event',object_id:text(event.event_id)})}>
      <ControlRowContent title={objectTitle(event as MemoryObject)}/><ChevronRightIcon/>
    </button>)}</GroupedList>:<p className="memory-empty">尚未生成事件。</p>}
  </section>;
}
