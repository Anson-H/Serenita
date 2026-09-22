import {useEffect,useState} from 'react';
import {stepTimingLabel} from './memoryStepTiming';
import {memoryStepNames,memoryStepTitle} from './memoryStepNames';
import type {MemoryChangeDetail,MemoryObject,MemoryProcessingStep} from "../../api/memory/memoryApi";
import {GroupedList} from '../../components/GroupedList';
import {ControlRowContent} from '../../components/ControlRowContent';
import {ChevronRightIcon} from '../../components/icons';
import {MemoryStepIO} from './MemoryStepIO';
import {MemoryStepContent} from './MemoryStepContent';
import {MemoryModelInputs,modelInputStep} from './MemoryModelInputs';
import {memoryTimestamp,objects,text} from './memoryPresentation';
import {modelRetryMessage} from '../../utils/modelRetry';

const roots = memoryStepNames.roots;
const labels:Record<string,string> = memoryStepNames.labels;
const statuses:Record<string,string> = {continued:'查找出了问题，已继续处理',reused:'已复用',pending:'等待处理',running:'正在处理',retrying:'正在重试',completed:'已完成',failed:'已失败',skipped:'无需处理',cancelled:'已取消',unrecorded:'未记录步骤进度',not_started:'未执行'};
type Node={id:string;parent:string|null;title:string;history:MemoryProcessingStep[]};
type Props={group:MemoryObject;steps:MemoryProcessingStep[];inputs:MemoryChangeDetail['model_inputs'];view?:MemoryObject;change?:MemoryChangeDetail;
  memberId?:string;onOpen:(row:MemoryObject)=>void;onOpenModelInput:(input:MemoryChangeDetail['model_inputs'][number])=>void};

export function currentProcessingAttempts(group:MemoryObject) {
  const attempts=objects(group.records).filter(row=>row.object_type==='processing_attempt') as MemoryObject[];
  const replaced=new Set(attempts.map(row=>text(row.previous_attempt_id)).filter(Boolean));
  return attempts.filter(row=>!replaced.has(text(row.attempt_id)));
}

export function MemoryProgress({group,steps,inputs,view,change,memberId,onOpen,onOpenModelInput}:Props){
  const row=view?.attempt_id?objects(group.records).find(item=>item.attempt_id===view.attempt_id&&item.object_type==='processing_attempt'):currentProcessingAttempts(group).filter(item=>item.task_kind==='event_formation').at(-1);
  const state=text(row?.processing_status)||text(group.processing_status),terminal=['completed','failed','cancelled'].includes(state);
  const [now,setNow]=useState(Date.now);
  const hasRunningSteps=!terminal&&steps.some(step=>['running','retrying'].includes(step.status)&&step.details.timing);
  useEffect(()=>{
    if(!hasRunningSteps)return;
    setNow(Date.now());
    const timer=window.setInterval(()=>setNow(Date.now()),1000);
    return()=>window.clearInterval(timer);
  },[hasRunningSteps]);
  const own=steps.filter(step=>step.receipt_id||step.attempt_id===row?.attempt_id);
  const allRequests=inputs.filter(input=>input.attempt_id===row?.attempt_id);
  const extractionResults=(change?.extraction_results||[]).filter(result=>result.attempt_id===row?.attempt_id);
  const nodes:Node[]=roots.map(([id,title])=>({id,title,parent:null,history:[]}));
  for(const id of ['permission_check','registration_check','registration_save'])nodes.push({id,parent:'registered',title:labels[id],history:[]});
  for(const id of ['read_registered_task','read_change_record','read_content'])nodes.push({id,parent:'prepare',title:labels[id],history:[]});
  for(const id of ['sag_extract_save'])nodes.push({id,parent:'sag_extract',title:labels[id],history:[]});
  for(const step of own){
    let node=nodes.find(value=>value.id===step.step_id&&value.parent===step.parent_step_id);
    if(!node){
      node={id:step.step_id,parent:step.parent_step_id,title:memoryStepTitle(step.step_id),history:[]};
      nodes.push(node);
    }
    node.history.push(step);
  }
  const eventIds=[...new Set(nodes.filter(node=>node.id.startsWith('organize_event:')).map(node=>node.id.slice('organize_event:'.length)))];
  const events=[...objects(group.events),...extractionResults.flatMap(result=>result.events)];
  for(const node of nodes){
    if(!node.id.startsWith('organize_event:'))continue;
    const eventId=node.id.slice('organize_event:'.length);
    const event=events.find(event=>event.event_id===eventId);
    node.title=`事件 ${eventIds.indexOf(eventId)+1}${text(event?.title)?` · ${text(event?.title)}`:''}`;
  }
  // Requests remain reachable even when their latest step record is missing.
  for(const input of allRequests){
    const id=modelInputStep(input);
    if(id&&!nodes.some(node=>node.id===id))nodes.push({id,parent:null,title:memoryStepTitle(id),history:[]});
  }
  const children=(node:Node)=>nodes.filter(value=>value.parent===node.id);
  // Keep storage ancestry for status and record lookup; navigation shows operations on one level.
  function flatChildren(node:Node,seen=new Set<Node>()):Node[]{
    if(seen.has(node))return [];
    seen.add(node);
    return children(node).flatMap(child=>{
      const descendants=flatChildren(child,seen);
      return [child,...descendants];
    });
  }
  function status(node:Node,seen=new Set<string>()):string{
    if(seen.has(node.id))return 'unrecorded';
    seen.add(node.id);
    if(node.id==='received'&&!node.history.length)return 'unrecorded';
    if(node.id==='registered'&&!node.history.length)return 'unrecorded';
    const last=node.history.at(-1);
    const requests=allRequests.filter(input=>modelInputStep(input)===node.id);
    const requestStatus=requests.at(-1)?.status;
    let value=last?.status||(requestStatus==='completed'?'unrecorded':requestStatus)||(terminal?(own.length?'not_started':'unrecorded'):'pending');
    if(value==='skipped')return value;
    const nested=children(node).map(child=>status(child,new Set(seen)));
    if(node.id==='sag_extract'&&value==='completed'&&nested.some(state=>!['completed','skipped'].includes(state)))value=terminal?'unrecorded':'running';
    for(const active of ['failed','retrying','running'])if(nested.includes(active)){value=active;break;}
    if(terminal&&['running','retrying'].includes(value))return state==='cancelled'?'cancelled':'failed';
    return value;
  }
  function error(node:Node):string{
    const value=status(node);
    if(!['failed','retrying'].includes(value))return '';
    return node.history.at(-1)?.error_message||children(node).map(child=>error(child)).find(Boolean)||'';
  }
  const statusLabel=(node:Node)=>{
    const retry=node.history.at(-1)?.details.retry;
    if(retry&&terminal&&['waiting','running'].includes(retry.status))
      return `第 ${retry.attempt}/${retry.max_attempts} 次尝试 · ${statuses[status(node)]||status(node)}`;
    return retry?modelRetryMessage(retry):statuses[status(node)]||status(node);
  };
  function list(values:Node[],label:string){
    return <GroupedList density="standard" aria-label={label}>{values.map(node=><button key={`${node.parent||''}/${node.id}`} type="button" className="control control--row memory-processing-item" onClick={()=>onOpen({object_type:'processing_step',attempt_id:row?.attempt_id,title:node.title,step_id:node.id,parent_step_id:node.parent})}>
      <ControlRowContent title={node.title} description={[statusLabel(node),error(node),stepTimingLabel(node.history.at(-1),now,terminal),node.history.at(-1)?.submitted_at?`最新记录：${memoryTimestamp(node.history.at(-1)?.submitted_at)}`:null,node.id==='sag_extract_save'&&extractionResults.length?`${extractionResults.flatMap(result=>result.events).length} 个事件 · ${extractionResults.flatMap(result=>result.entities).length} 个实体`:null].filter(Boolean).join(' · ')}/><ChevronRightIcon/>
    </button>)}</GroupedList>;
  }
  const requestsFor=(node:Node)=>allRequests.filter(input=>modelInputStep(input)===node.id);
  if(!view){
    const groups=nodes.filter(node=>node.parent===null&&
      (row?.task_kind==='intake_review'?['received','registered'].includes(node.id):row?.task_kind==='vector_index'?node.id==='index':true));
    const unmatched=allRequests.filter(input=>!modelInputStep(input));
    return <section aria-label="处理步骤列表" className="memory-processing-detail">
      {groups.map(group=>{
        const eventGroup=group.id.startsWith('organize_event:');
        const records=flatChildren(group).filter(node=>node.id!=='sag_extract'&&(node.history.length||requestsFor(node).length));
        const recordedAt=(node:Node)=>node.history.at(-1)?.submitted_at||requestsFor(node)[0]?.submitted_at||'';
        if(eventGroup){
          const order=['episode_search_context','episode_search','event_organization_context','event_organization','event_organization_save','revisions_context','revisions','revisions_save'];
          const rank=(node:Node):number=>{
            const index=order.indexOf(node.id.split(':')[0]);
            if(index>=0)return index;
            const parent=nodes.find(value=>value.id===node.parent);
            return parent&&parent!==group?rank(parent):order.length;
          };
          records.sort((a,b)=>rank(a)-rank(b));
        }else records.sort((a,b)=>recordedAt(a).localeCompare(recordedAt(b)));
        return <section key={group.id} aria-label={`${group.title}分组`} className="memory-processing-detail memory-step-group">
          <h3><button type="button" className="control control--row memory-processing-item" onClick={()=>onOpen({object_type:'processing_step',attempt_id:row?.attempt_id,title:group.title,step_id:group.id,parent_step_id:group.parent})}>
            <ControlRowContent title={group.title} description={[statusLabel(group),stepTimingLabel(group.history.at(-1),now,terminal)].filter(Boolean).join(' · ')}/><ChevronRightIcon/>
          </button></h3>
          {records.length?list(records,`${group.title}记录`):null}
        </section>;
      })}
      {unmatched.length?<MemoryModelInputs inputs={unmatched} title="未标明环节的模型请求" onOpen={onOpenModelInput}/>:null}
    </section>;
  }
  const node=nodes.find(item=>item.id===view.step_id&&item.parent===view.parent_step_id);
  if(!node)return <p className="memory-metadata">此环节当前没有可读取的记录。</p>;
  const sourceId=node.id;
  const matching=requestsFor(node).filter(input=>view.object_type!=='processing_progress_record'||input.attempt_id===view.attempt_id);
  const content=change&&memberId?<MemoryStepContent memberId={memberId} change={change} step={sourceId}
    parent={node.parent} title={node.title} steps={node.history}
    attemptIds={[...new Set([text(row?.attempt_id),...node.history.map(step=>step.attempt_id).filter((id):id is string=>!!id),...matching.map(input=>input.attempt_id)])]}
    requestStamp={matching.map(input=>input.entry_id).join(',')} leaf/>
    :<MemoryStepIO steps={node.history} title={node.title} leaf={!matching.length}/>;
  return <section className="memory-processing-detail" aria-label="处理步骤详情">
    <p className="memory-metadata">{statusLabel(node)} · {node.title}</p>
    {node.history.at(-1)?.submitted_at?<p className="memory-metadata">最新记录时间：{memoryTimestamp(node.history.at(-1)?.submitted_at)}</p>:null}
    <p className="memory-metadata">{stepTimingLabel(node.history.at(-1),now,terminal)}</p>
    {node.history.at(-1)?.details.timing?<p className="memory-metadata">开始：{memoryTimestamp(node.history.at(-1)!.details.timing!.started_at)}{node.history.at(-1)!.details.timing!.finished_at?` · 结束：${memoryTimestamp(node.history.at(-1)!.details.timing!.finished_at)}`:''}</p>:null}
    {content}
  </section>;
}
