import {memoryStepTitle} from './memoryStepNames';
import type {MemoryChangeDetail} from "../../api/memory/memoryApi";
import {GroupedList,ReadonlyField} from '../../components/GroupedList';
import {ChevronRightIcon} from '../../components/icons';
import {ControlRowContent} from '../../components/ControlRowContent';
import {memoryTimestamp, object, objects, text} from './memoryPresentation';
import {modelRetryMessage} from '../../utils/modelRetry';

type ModelInput = MemoryChangeDetail['model_inputs'][number];
const stages:Record<string,[string,string]>={
  sag_extract:[memoryStepTitle('sag_extract'),'从变更内容中提取事件，识别其中的人物、药品等实体，保留实体在事件中的作用。'],
  episode_search:[memoryStepTitle('episode_search'),'根据当前事件和固定事项范围，筛选一个待核对事项，暂不保存归属。'],
  event_organization:[memoryStepTitle('event_organization'),'读取所选事项全部事件，联合判断归属与连接关系；不合适时直接创建独立事项。'],
  revisions:[memoryStepTitle('revisions'),'根据事件和依据形成事项的状态。'],
};
function presentation(input:ModelInput) {
  const blocks=typeof input.content==='string'?[input.content]:objects(input.content).filter(block=>block.type==='text').map(block=>text(block.text));
  let data:Record<string,unknown>={};
  try{data=object(JSON.parse(blocks[0]||''));}catch{/* Unstructured content remains available verbatim. */}
  if(Array.isArray(data.messages)){
    const content=objects(data.messages).filter(message=>message.role==='user').at(-1)?.content;
    const stageText=typeof content==='string'?content:text(objects(content).find(block=>block.type==='text')?.text);
    try{data=object(JSON.parse(stageText));}catch{data={};}
  }
  const nested=object(data.data),meta=object(nested.meta);
  const stage=text(data.pipeline_stage)||text(meta.pipeline_stage)||input.processing_step?.split(':')[0]||'';
  const chunkPhase=['sag_extract','sag_facts'].includes(stage)?text(meta.extraction_phase):'';
  let [title,purpose]=stages[stage]||['查看模型输入',stage?`处理阶段：${memoryStepTitle(stage)}。`:'该请求没有处理阶段标识，可查看实际发送的内容。'];
  if(input.kind==='embedding')[title,purpose]=[memoryStepTitle('embed_content'),'查看向量模型实际收到的内容和返回结果。'];
  if(chunkPhase==='facts')[title,purpose]=[memoryStepTitle('sag_fact_extract'),'从完整结构单元选择重要信息，并保留对应的原文摘录。'];
  if(chunkPhase==='direct')[title,purpose]=[memoryStepTitle('sag_extract_direct'),'结合完整资料选择重要信息，生成事件正文与摘要。'];
  if(chunkPhase==='organization')[title,purpose]=[memoryStepTitle('sag_event_synthesis'),'结合各分块的重要信息与实际依据，统一组织事件正文与摘要。'];
  if(!stage){
    if(typeof data.query==='string'&&Array.isArray(data.candidates)&&Array.isArray(data.groups))
      [title,purpose]=['选择参考资料','从检索结果中选择相关事件及完整证据组。'];
    else if(typeof data.question==='string'&&typeof data.relations==='string'&&typeof data.top_k==='number')
      [title,purpose]=['排列相关事件','按与变更内容的相关程度选择并排列已有事件。'];
    else if(typeof data.query==='string'&&Object.keys(data).length===1)
      [title,purpose]=['准备搜索线索','从查询文字中提取实体名称，用于检索已有记忆。'];
  }
  const repair=Array.isArray(data.validation_errors)||Array.isArray(meta.validation_errors);
  if(repair){title+=' · 修正输出';purpose+='上一次输出未通过校验，此次输入包含错误说明。';}
  return {title,purpose,data,stage};
}
export const modelInputStep=(input:ModelInput)=>input.processing_step||presentation(input).stage;
export const modelInputTitle=(input:ModelInput)=>presentation(input).title;

export function MemoryModelInputs({inputs,onOpen,title='模型请求'}:{inputs:ModelInput[];onOpen:(input:ModelInput)=>void;title?:string}) {
  return <section className="memory-model-inputs" aria-label={title}><h5>{title}</h5>
    {!inputs.length?<p className="memory-metadata">尚无可读取的模型输入记录。</p>:<>
      <GroupedList density="standard" aria-label="模型请求列表">{inputs.map(input=>{
        const view=presentation(input);
        return <button key={input.entry_id} type="button" className="control control--row memory-model-input-row" onClick={()=>onOpen(input)}>
          <ControlRowContent title={view.title} description={<>{view.purpose}{input.status==='failed'?` 请求失败：${input.error_code||'原因未记录'}`:input.status==='running'?' 正在请求模型。':''}{input.output?.retry||input.retry?<span role="status">{modelRetryMessage((input.output?.retry||input.retry)!)}</span>:null}<time dateTime={input.submitted_at}>{memoryTimestamp(input.submitted_at)}</time></>}/><ChevronRightIcon/>
        </button>;
      })}</GroupedList>
    </>}
  </section>;
}
export function MemoryModelInputDetail({input}:{input:ModelInput}) {
  const title=`第 ${input.call_number} 次调用`;
  const raw=typeof input.content==='string'?input.content:JSON.stringify(input.content,null,2);
  return <section className="memory-model-input-detail" aria-label="模型输入与输出">
    <section aria-label="调用信息">
    <h3 className="memory-call-title">{title}</h3>
    <GroupedList layout="fields" density="standard" aria-label="模型请求信息">
      <ReadonlyField label="模型" value={input.model_id}/>
      {input.output?.retry||input.retry?<ReadonlyField label="尝试状态" value={modelRetryMessage((input.output?.retry||input.retry)!)}/>:null}
      <ReadonlyField label="请求开始" value={<time dateTime={input.submitted_at}>{input.submitted_at}</time>}/>
      {text(input.output?.finished_at)?<ReadonlyField label="请求结束" value={<time dateTime={text(input.output?.finished_at)}>{text(input.output?.finished_at)}</time>}/>:null}
      {typeof input.output?.elapsed_seconds==='number'?<ReadonlyField label="实际耗时" value={`${input.output.elapsed_seconds.toFixed(3)} 秒`}/>:null}
      <ReadonlyField label="处理标识" value={input.attempt_id}/>
      <ReadonlyField label="请求标识" value={input.entry_id}/>
      {input.output?.stream_status?<>
        <ReadonlyField label="流式输出" value={input.status==='running'?'正在接收':input.status==='failed'?'已停止，已收到的内容保留':'接收完成'}/>
        {input.output.first_chunk_at?<ReadonlyField label="首个片段" value={text(input.output.first_chunk_at)}/>:null}
      </>:null}
      {input.status==='failed'?<ReadonlyField label="请求失败" value={input.error_code||'原因未记录'}/>:null}
    </GroupedList>
    </section>
    <section aria-label="模型输入"><h3>模型输入</h3><div className="text-input-surface memory-change-markdown"><pre className="memory-model-code">{raw}</pre></div></section>
    <section aria-label="模型输出"><h3>模型输出</h3>{input.output!=null?<div className="text-input-surface memory-change-markdown"><pre className="memory-model-code">{JSON.stringify(input.output,null,2)}</pre></div>:<p className="memory-metadata">{input.status==='running'?'等待模型输出。':input.status==='unavailable'?'模型输出当前不可读取。':input.status==='failed'?`模型请求失败：${input.error_code||'原因未记录'}。`:'未记录模型输出。'}</p>}</section>
  </section>;
}
