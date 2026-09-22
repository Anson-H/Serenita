import {MemoryEpisodeView} from './MemoryEpisodeView';
import {GroupedList,ReadonlyField} from "../../components/GroupedList";
import {MemoryEventRelationView} from "./MemoryEventRelationView";
import {MemoryEventView} from "./MemoryEventView";
import {MemoryReferences} from "./MemoryReferences";
import type { MemoryObject, MemoryReference } from "../../api/memory/memoryApi";
import { processingTaskDescription, processingError, evidenceReferences, kindLabels, memoryTime, memoryTimestamp, object, objects, roleLabels, statusLabels, strings, text } from "./memoryPresentation";
import type {MemoryCitation} from './memoryChangePresentation';
import {changeFieldLabel} from './memoryChangePresentation';
import {MemoryGaps} from './MemoryGaps';
import {MemoryAttemptActions, type MemoryAttemptControls} from './MemoryAttemptActions';

function Fields({items}:{items:[string,string][]}){return <GroupedList density="standard" layout="fields" className="memory-facts">{items.map(([label,value])=><ReadonlyField key={label} label={label} value={value}/>)}</GroupedList>;}

function Notes({label, values}: {label: string; values: unknown}) {
  const items = strings(values);
  return items.length ? <section className="memory-notes"><h4>{label}</h4><ul>{items.map((item, index) => <li key={index}>{item}</li>)}</ul></section> : null;
}

export function MemoryObjectView({row, onRead, nested = false, busy = false, onResume, onRetry, onCancel,onGraph,memberId,recordCutoff}: MemoryAttemptControls & {onRead: (reference: MemoryReference, citation?:MemoryCitation) => void; citation?:MemoryCitation; nested?: boolean;
  onGraph?:(episode:string,version?:number)=>void;memberId?:string;recordCutoff?:number}) {
  if(row.object_type === "episode" || row.object_type === "episode_revision")return <MemoryEpisodeView row={row} onRead={onRead} onGraph={onGraph}/>;
  if(row.object_type === "event")return <MemoryEventView row={row} onRead={onRead} memberId={memberId} recordCutoff={recordCutoff} nested={nested}/>;
  if(row.object_type === "event_relation")return <MemoryEventRelationView row={row} onRead={onRead} memberId={memberId} recordCutoff={recordCutoff} nested={nested}/>;
  const processing = row.object_type === "processing_attempt" ? row : object(row.processing);
  const status = processing;
  const details = object(row.details);
  const medication = object(details.medication);
  const role = text(row.content_role);
  const parts = ["summary", "canonical_name", "content", "statement_text", "problem_text", "reason", "purpose", "change_reason", "outcome_reason"];
  const paragraphs = [...new Set(parts.map(field => field==='purpose'&&row.object_type==='processing_attempt'?processingTaskDescription(row):field==='canonical_name'&&row.entity_type==='administrative_field'?changeFieldLabel(text(row[field])):text(row[field])).filter(Boolean))];
  const children = [...["items"].flatMap(field => objects(row[field])),object(row.current_version)].filter(item => typeof item.object_type === "string") as MemoryObject[];
  const references = evidenceReferences(row);
  const metadata:[string,string][]=[];
  if(row.target_time||row.occurrence_time||row.time_requirement)metadata.push(['目标时期',memoryTime(row.target_time||row.occurrence_time||row.time_requirement)]);
  if(typeof row.input_sequence==='number')metadata.push(['采用记录截点',String(row.input_sequence)]);
  if(text(row.submitted_at))metadata.push(['保存时间',memoryTimestamp(row.submitted_at)]);

  return <article className={nested ? "memory-entry memory-entry--nested" : "memory-entry"}>
    <div className="memory-entry-heading"><strong>{kindLabels[row.object_type] || row.object_type}</strong>
      {role ? <span className="memory-badge">{roleLabels[role] || role}</span> : null}
      {text(row.historical_identity) === "historical_saved" ? <span className="memory-badge">当时已保存</span> : null}
      {text(row.historical_identity) === "historical_reconstruction" ? <span className="memory-badge">现在重建过去</span> : null}
    </div>
    {text(row.title) || text(row.name) ? <h3>{text(row.title) || text(row.name)}</h3> : null}
    {paragraphs.map((paragraph, index) => <p className="memory-prose" key={index}>{paragraph}</p>)}
    {metadata.length?<Fields items={metadata}/>:null}
    <MemoryGaps label="未读范围" values={row.unread} onRead={onRead}/><MemoryGaps label="资料缺口" values={row.gaps} onRead={onRead}/>
    {row.object_type==='episode_membership'?<p className="memory-status">固定事项归属</p>:
      null}
    {text(processing.processing_status) ? <div className={`memory-status memory-status--${text(processing.processing_status)}`} role="status">
      处理进度：{statusLabels[text(processing.processing_status)] || text(processing.processing_status)}
      {processingError(status) ? <p>{processingError(status)}</p> : null}
      {text(status.error_code) ? <p>原因代码：{text(status.error_code)}</p> : null}
      <Notes label="处理缺口" values={status.gaps}/>
      {text(status.outcome_reason)?<p>{text(status.outcome_reason)}</p>:null}
    </div> : null}
    {row.object_type==='processing_attempt'&&!row.processing_status?<p className="memory-status">当前处理状态不可读取。请刷新并核对权限后继续。</p>:null}
    {row.object_type === "processing_attempt" ? <MemoryAttemptActions row={row} busy={busy} onResume={onResume} onRetry={onRetry} onCancel={onCancel}/> : null}
    <Notes label="未知与限制" values={row.unknown}/>
    <Notes label="涉及对象" values={row.key_objects}/><Notes label="纳入条件" values={row.inclusion_conditions}/><Notes label="排除条件" values={row.exclusion_conditions}/>
    {text(medication.name)?<Fields items={[["药品",text(medication.name)],["剂量",[text(medication.dose_value),text(medication.dose_unit)].filter(Boolean).join(" ")||"未知"],["频次",text(medication.frequency_text)||"未知"],["执行身份",text(medication.execution_role)]]}/>:null}
    {text(details.polarity) ? <p>事件表达：{({affirmed:"明确肯定",negated:"明确否定",uncertain:"尚不确定"} as Record<string,string>)[text(details.polarity)] || text(details.polarity)}</p>:null}
    {objects(details.attributes).map((attribute,index)=><p key={index}>{text(attribute.name)}：{text(attribute.value)} {text(attribute.unit)}{text(attribute.basis)?`（依据：${text(attribute.basis)}）`:""}</p>)}
    {text(object(details.duration).value)?<p>持续时间：{text(object(details.duration).value)} {text(object(details.duration).unit)}</p>:null}
    {row.locator?<Fields items={Object.entries(object(row.locator)).filter(([,value])=>value!==null).map(([name,value])=>[({field_path:"字段位置",page_number:"页码",event_id:"来源事件",segment_id:"片段",character_start:"字符起点",character_end:"字符终点",line_start:"起始行",line_end:"结束行"} as Record<string,string>)[name]||name,String(value)])}/>:null}
    {row.object_type==="processing_attempt" && row.model_id?<Fields items={[["执行模型",text(row.model_id)]]}/>:null}
    {row.object_type === "processing_attempt" && Number(row.restricted_entries)>0?<p className="memory-status">部分执行记录的来源权限已受限，当前不能展开。</p>:null}
    {['vector_binding','vector_status'].includes(row.object_type)?<div className="memory-status"><p>检索准备：{({pending:'等待处理',confirmed:'可以检索',failed:'准备失败',unavailable:'当前不可用'} as Record<string,string>)[text(row.state)||text(object(row.status).state)]||'当前状态不可读取'}</p>
      <p>{text(row.error_message)||text(object(row.status).error_message)}</p><p>{text(row.error_code)||text(object(row.status).error_code)}</p></div>:null}
    {row.object_type==='vector_space'?<Fields items={[["向量模型",text(row.model_id)],["向量维度",String(row.dimensions??'未知')]]}/>:null}
    {row.object_type === "memory_execution_entry" ? <details><summary>实际执行内容 · {text(row.entry_kind)}</summary><pre className="memory-source">{JSON.stringify(row.payload,null,2)}</pre></details>:null}
    {objects(row.evidence).filter(entry => entry.reference).map((entry,index)=><section className="memory-notes" key={index}><h4>{({support:"支持依据",counterevidence:"反证",same_experience:"同次经历依据",different_experience:"不同经历依据",causal_statement:"来源中的因果陈述"} as Record<string,string>)[text(entry.role)] || "关系判断依据"}</h4><p>{text(entry.basis)}</p>{text(entry.quoted_text)?<blockquote className="memory-quote">{text(entry.quoted_text)}</blockquote>:null}</section>)}
    {children.map((child, index) => <MemoryObjectView row={child} onRead={onRead} memberId={memberId} recordCutoff={recordCutoff} nested key={index}/>)}
    <MemoryReferences references={references} onRead={onRead}/>
    {objects(row.coverage).length ? <details className="memory-coverage"><summary>资料范围与缺失内容</summary>{objects(row.coverage).map((scope, index) => <div key={index}>
      <p>{text(scope.source_category)} · {memoryTime(scope.target_time)} · {scope.complete === true ? "所选范围已读完整" : "范围未完整读取"}</p>
      <MemoryGaps label="未读内容" values={scope.unread} onRead={onRead}/>
    </div>)}</details> : null}
  </article>;
}
